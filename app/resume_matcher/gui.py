"""A small desktop window for running the matcher without a terminal.

Two tabs:
  * Match - drop a single job posting file (or click to browse) to score it
    against every resume in the resumes folder, or press "Run all jobs" to
    score every posting in the jobs folder, the same as `python -m
    resume_matcher`.
  * Server - where the model runs: a local server (Unsloth Desktop) or a
    hosted API, with base URL, key, model, and concurrency. Saved to
    app/settings.json (gitignored, since it may hold a key).

Real drag-and-drop needs the optional ``tkinterdnd2`` package; without it the
drop zone still works as a click-to-browse button.

Heavy imports (the LLM client, document parsing) are deliberately deferred to
worker threads so the window appears instantly.
"""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import webbrowser
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import urlparse


def ensure_tcl_env() -> None:
    """Point Tcl/Tk at the base Python's script libraries on Windows.

    Inside a venv on some Windows builds (Python 3.13 among them) the
    interpreter does not work out where Tcl's init.tcl lives, and creating a
    window fails with 'Can't find a usable init.tcl'. The base installation
    has them under <base_prefix>\\tcl\\tcl8.6 and \\tk8.6; setting the
    environment variables Tcl honours fixes it. Existing values are kept.
    """
    if sys.platform != "win32":
        return
    tcl_root = Path(sys.base_prefix) / "tcl"
    if not tcl_root.is_dir():
        return
    for var, prefix in (("TCL_LIBRARY", "tcl"), ("TK_LIBRARY", "tk")):
        if os.environ.get(var):
            continue
        candidates = sorted(
            p for p in tcl_root.iterdir()
            if p.is_dir() and p.name.startswith(prefix) and p.name[len(prefix):len(prefix) + 1].isdigit()
            and (p / ("init.tcl" if prefix == "tcl" else "tk.tcl")).exists()
        )
        if candidates:
            os.environ[var] = str(candidates[-1])


ensure_tcl_env()

import tkinter as tk  # noqa: E402  (after the Tcl environment is settled)
from tkinter import filedialog, font as tkfont, ttk  # noqa: E402

from .config import SETTINGS_PATH, Config
from .providers import HOSTED, LOCAL, find, pick_default_model, provider_names

try:  # optional: enables real drag-and-drop
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND = True
except ImportError:  # pragma: no cover - depends on optional install
    _DND = False

try:  # optional: the Windows 11 look for ttk widgets; the stock look otherwise
    import sv_ttk
except ImportError:  # pragma: no cover - depends on optional install
    sv_ttk = None

ICON_DIR = Path(__file__).resolve().parent

_PROGRESS_RE = re.compile(r"\[(\d+)/(\d+) total")
# Point size for all UI text. Tk's Windows default is 9pt (12px), which reads
# small next to current Windows apps; 11pt is about 15px at 100% scaling.
BODY_PT = 11
_WARN = "#b45309"
_ERR = "#b42318"
_OK = "#1a7f37"

# Colours for the plain-tk widgets a ttk theme does not cover (the canvas drop
# zone and the log), one set per theme.
PALETTES = {
    "light": {
        "zone": "#fafafa", "zone_hover": "#e6f0fb", "dash": "#a3adba",
        "title": "#1b1b1b", "muted": "#6b7280",
        "log_bg": "#f6f8fa", "log_fg": "#24292f",
    },
    "dark": {
        "zone": "#2b2b2b", "zone_hover": "#1e3a5f", "dash": "#5c6470",
        "title": "#f0f0f0", "muted": "#9ca3af",
        "log_bg": "#1a1a1a", "log_fg": "#d4d4d4",
    },
}


def enable_dpi_awareness() -> None:
    """Tell Windows this process handles DPI itself, so text renders crisp on
    scaled displays instead of being bitmap-stretched. Must run before the
    first window exists. System-wide awareness (not per-monitor) is chosen
    because Tk does not re-lay-out when a window moves between monitors."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # pragma: no cover - pre-8.1 Windows
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def set_app_id(app_id: str = "DanielBerd.ResumeMatcher") -> None:
    """Give the process its own taskbar identity on Windows.

    Without this, Windows files the window under pythonw.exe and shows the
    Python icon on the taskbar regardless of the window's own icon. Must run
    before the first window exists.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def windows_prefers_dark() -> bool:
    """True when Windows' Settings > Personalization > Colors app mode is Dark."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except OSError:
        return False


def set_title_bar_dark(root: tk.Tk, dark: bool) -> None:
    """Colour the title bar to match a dark theme (Windows 10 1809+); no-op elsewhere."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(int(dark))
        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20 from Windows 10 20H1; 19 before.
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
    except Exception:
        pass


def set_window_icon(root: tk.Tk) -> None:
    """Use the bundled icon instead of Tk's feather; quietly keeps the default if missing."""
    try:
        if sys.platform == "win32":
            root.iconbitmap(default=str(ICON_DIR / "icon.ico"))
        else:
            root.iconphoto(True, tk.PhotoImage(file=str(ICON_DIR / "icon.png")))
    except Exception:
        pass


def host_of(url: str) -> str:
    """'https://api.openai.com/v1' -> 'api.openai.com'; falls back to the raw text."""
    try:
        return urlparse(url).hostname or url
    except ValueError:
        return url


def unreachable_text(url: str) -> str:
    """Summary-line text when the server cannot be reached; clicking it opens the Server tab."""
    return f"Cannot reach the model server at {host_of(url)} - click here to fix it on the Server tab"


def summary_text(config: Config) -> str:
    """One line for the Match tab saying what a run will use."""
    where = "hosted - data leaves this machine" if config.is_hosted else "local"
    model = config.llm_model or "(no model set)"
    return f"Using {model} @ {host_of(config.llm_base_url)} ({where})"


def _make_dot(color: str, size: int = 9) -> tk.PhotoImage:
    """A small filled circle for marking a notebook tab (no image files needed)."""
    img = tk.PhotoImage(width=size + 4, height=size)
    r = size / 2
    for y in range(size):
        for x in range(size):
            if (x - r + 0.5) ** 2 + (y - r + 0.5) ** 2 <= r * r:
                img.put(color, (x + 4, y))
    return img


class _QueueWriter:
    """File-like object that forwards captured stdout lines to the UI queue."""

    def __init__(self, q: queue.Queue):
        self._q = q
        self._buf = ""

    def write(self, text: str) -> int:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._q.put(("log", line))
        return len(text)

    def flush(self) -> None:
        if self._buf:
            self._q.put(("log", self._buf))
            self._buf = ""


class MatcherWindow:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.last_report: Path | None = None

        enable_dpi_awareness()
        set_app_id()
        self.root = TkinterDnD.Tk() if _DND else tk.Tk()
        self.root.title("Resume Matcher")
        set_window_icon(self.root)

        # Theme follows the Windows app mode. With sv_ttk present the ttk
        # widgets take on the Windows 11 look; otherwise they keep the stock
        # look and only the palette for the plain-tk widgets applies.
        self.theme = "dark" if windows_prefers_dark() else "light"
        self.palette = PALETTES[self.theme]
        self.themed = sv_ttk is not None
        if self.themed:
            sv_ttk.set_theme(self.theme)
        self._configure_fonts()
        # Pixel sizes are scaled by the display's DPI (fonts scale on their own).
        self.scale = self.root.winfo_fpixels("1i") / 96.0
        self.root.geometry(f"{self._px(740)}x{self._px(700)}")
        self.root.minsize(self._px(640), self._px(600))

        self._build()
        set_title_bar_dark(self.root, self.theme == "dark")
        self.root.after(100, self._drain)
        # A local server is cheap to ask; a hosted API is only queried on demand.
        if not self.config.is_hosted:
            self._fetch_models()

    # ---------- layout ----------

    def _px(self, n: int) -> int:
        return int(round(n * self.scale))

    def _style(self, name: str) -> str:
        """A theme-specific ttk style name, or the default when the theme is absent."""
        return name if self.themed else ""

    def _configure_fonts(self) -> None:
        """Set every UI font to BODY_PT.

        Tk's defaults cover labels, buttons and tabs. The theme puts its own
        named fonts on entry fields, comboboxes and spinboxes, so those are
        raised too or they would end up smaller than the labels beside them.
        Segoe UI Variable is used when present (Windows 11) so the faces match.
        """
        family = None
        if sys.platform == "win32" and "Segoe UI Variable Text" in tkfont.families():
            family = "Segoe UI Variable Text"
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            f = tkfont.nametofont(name)
            f.configure(size=BODY_PT, **({"family": family} if family else {}))
        for name in ("SunValleyBodyFont", "SunValleyBodyStrongFont", "SunValleyCaptionFont"):
            try:
                tkfont.nametofont(name).configure(size=BODY_PT)
            except tk.TclError:  # theme not loaded
                pass

    def _font(self, size: int, weight: str = "normal") -> tkfont.Font:
        """The platform's UI font at a given size, so headings match the rest."""
        f = tkfont.nametofont("TkDefaultFont").copy()
        f.configure(size=size, weight=weight)
        return f

    def _build(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=self._px(12), pady=(self._px(10), self._px(12)))
        match_tab = ttk.Frame(self.notebook, padding=self._px(6))
        server_tab = ttk.Frame(self.notebook, padding=self._px(6))
        self.notebook.add(match_tab, text="  Match  ")
        self.notebook.add(server_tab, text="  Server  ")
        self._build_match_tab(match_tab)
        self._build_server_tab(server_tab)
        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self._apply_fields())
        self._server_tab_index = 1
        self._dot = _make_dot(_ERR)
        self._server_alert = False
        self._refresh_summary()

    def _build_match_tab(self, tab: ttk.Frame) -> None:
        pad = {"padx": self._px(10), "pady": self._px(6)}
        self.summary = ttk.Label(tab, text="", foreground="gray", wraplength=self._px(600), justify="left")
        self.summary.pack(anchor="w", padx=self._px(10), pady=(self._px(8), 0))
        self.summary.bind("<Button-1>", lambda _e: self._server_alert and self.notebook.select(self._server_tab_index))

        # Drop zone
        self._zone_font = self._font(BODY_PT + 4, "bold")
        self._zone_sub_font = self._font(BODY_PT)
        self.zone = tk.Canvas(tab, height=self._px(130), highlightthickness=0)
        self.zone.pack(fill="x", **pad)
        self.zone.bind("<Configure>", lambda _e: self._draw_zone())
        self.zone.bind("<Button-1>", lambda _e: self._browse_job())
        self.zone.configure(cursor="hand2")
        if _DND:
            self.zone.drop_target_register(DND_FILES)
            self.zone.dnd_bind("<<Drop>>", self._on_drop)
            self.zone.dnd_bind("<<DragEnter>>", lambda _e: self._draw_zone(hover=True))
            self.zone.dnd_bind("<<DragLeave>>", lambda _e: self._draw_zone())

        actions = ttk.Frame(tab)
        actions.pack(fill="x", **pad)
        self.run_all_btn = ttk.Button(actions, text="Run all jobs in jobs/ folder", command=self._run_all,
                                      style=self._style("Accent.TButton"))
        self.run_all_btn.pack(side="left")
        self.open_btn = ttk.Button(actions, text="Open last report", command=self._open_report, state="disabled")
        self.open_btn.pack(side="left", padx=self._px(8))

        self.progress = ttk.Progressbar(tab, mode="determinate")
        self.progress.pack(fill="x", padx=self._px(10))
        self.status = ttk.Label(tab, text="Ready", foreground="gray")
        self.status.pack(anchor="w", padx=self._px(10), pady=(self._px(4), 0))

        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True, padx=self._px(10), pady=(self._px(6), self._px(10)))
        self.log = tk.Text(frame, height=10, wrap="word", state="disabled",
                           bg=self.palette["log_bg"], fg=self.palette["log_fg"],
                           insertbackground=self.palette["log_fg"],
                           relief="flat", borderwidth=0, highlightthickness=0,
                           padx=self._px(8), pady=self._px(6),
                           font=("Consolas" if sys.platform == "win32" else "monospace", BODY_PT - 1))
        bar = ttk.Scrollbar(frame, command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    def _build_server_tab(self, tab: ttk.Frame) -> None:
        c = self.config
        form = ttk.Frame(tab, style=self._style("Card.TFrame"), padding=self._px(16))
        form.pack(fill="x", padx=self._px(10), pady=self._px(10))
        form.columnconfigure(1, weight=1)
        row = 0

        def label(text: str) -> None:
            ttk.Label(form, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(0, self._px(12)))

        label("Preset:")
        self.provider_var = tk.StringVar(value=c.llm_provider if find(c.llm_provider) else provider_names()[0])
        box = ttk.Combobox(form, textvariable=self.provider_var, values=provider_names(), state="readonly")
        box.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        box.bind("<<ComboboxSelected>>", lambda _e: self._on_preset())
        row += 1

        label("Runs on:")
        self.mode_var = tk.StringVar(value=c.llm_mode)
        modes = ttk.Frame(form)
        modes.grid(row=row, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(modes, text="Local server (nothing leaves this machine)", value=LOCAL,
                        variable=self.mode_var, command=self._on_mode).pack(side="left")
        ttk.Radiobutton(modes, text="Hosted API", value=HOSTED,
                        variable=self.mode_var, command=self._on_mode).pack(side="left", padx=(12, 0))
        row += 1

        label("Base URL:")
        self.url_var = tk.StringVar(value=c.llm_base_url)
        ttk.Entry(form, textvariable=self.url_var).grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        row += 1

        label("API key:")
        self.key_var = tk.StringVar(value=c.llm_api_key)
        self.key_entry = ttk.Entry(form, textvariable=self.key_var, show="•")
        self.key_entry.grid(row=row, column=1, sticky="ew", pady=4)
        self.show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Show", variable=self.show_key,
                        command=lambda: self.key_entry.configure(show="" if self.show_key.get() else "•")
                        ).grid(row=row, column=2, padx=(8, 0))
        row += 1

        label("Model:")
        self.model_var = tk.StringVar(value=c.llm_model)
        self.model_box = ttk.Combobox(form, textvariable=self.model_var, state="normal")
        self.model_box.grid(row=row, column=1, sticky="ew", pady=4)
        self.model_box.bind("<<ComboboxSelected>>", lambda _e: self._on_model_selected())
        ttk.Button(form, text="Fetch models", command=self._fetch_models).grid(row=row, column=2, padx=(8, 0))
        row += 1

        label("Concurrency:")
        self.conc_var = tk.IntVar(value=c.concurrency)
        conc = ttk.Frame(form)
        conc.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Spinbox(conc, from_=1, to=16, width=5, textvariable=self.conc_var).pack(side="left")
        ttk.Label(conc, text="in flight at once - match the server's slots",
                  foreground="gray").pack(side="left", padx=(self._px(8), 0))
        row += 1

        self.privacy = ttk.Label(form, text="", foreground=_WARN, wraplength=self._px(560), justify="left")
        self.privacy.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 2))
        row += 1

        buttons = ttk.Frame(form)
        buttons.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(buttons, text="Test connection", command=self._test_connection).pack(side="left")
        ttk.Button(buttons, text="Save", command=self._save,
                   style=self._style("Accent.TButton")).pack(side="left", padx=self._px(8))
        row += 1

        self.server_status = ttk.Label(form, text="", foreground="gray", wraplength=self._px(560), justify="left")
        self.server_status.grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 0))
        row += 1

        ttk.Label(form, text=f"Settings are saved to app/{SETTINGS_PATH.name} (kept out of git). "
                             "Runs use the values shown here.",
                  foreground="gray", wraplength=self._px(560), justify="left"
                  ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self._on_mode()

    def _draw_zone(self, hover: bool = False) -> None:
        c, pal = self.zone, self.palette
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        m = self._px(6)
        c.configure(bg=pal["zone_hover"] if hover else pal["zone"])
        c.create_rectangle(m, m, w - m, h - m, dash=(6, 4), outline=pal["dash"], width=2)
        headline = "Drop a job posting here" if _DND else "Click to choose a job posting"
        c.create_text(w // 2, h // 2 - self._px(12), text=headline, font=self._zone_font, fill=pal["title"])
        sub = "or click to browse  -  .txt .eml .pdf .docx" if _DND else ".txt .eml .pdf .docx"
        c.create_text(w // 2, h // 2 + self._px(12), text=sub, font=self._zone_sub_font, fill=pal["muted"])

    # ---------- server tab behaviour ----------

    def _on_preset(self) -> None:
        p = find(self.provider_var.get())
        if not p:
            return
        self.mode_var.set(p.mode)
        if p.base_url:
            self.url_var.set(p.base_url)
        if p.model:
            self.model_var.set(p.model)
        if p.needs_key and self.key_var.get() == "local":
            self.key_var.set("")
        if not p.needs_key and not self.key_var.get():
            self.key_var.set("local")
        self.model_box.configure(values=())
        self._set_server_status("")
        self._set_server_alert(False)
        self._on_mode()

    def _on_mode(self) -> None:
        hosted = self.mode_var.get() == HOSTED
        self.privacy.configure(
            text=("Hosted mode: job postings and the full text of every resume will be sent to "
                  f"{host_of(self.url_var.get())}. Switch to a local server to keep them on this machine.")
            if hosted else ""
        )

    def _apply_fields(self) -> Config:
        """Copy the Server tab into self.config so runs use what is shown."""
        c = self.config
        c.llm_provider = self.provider_var.get()
        c.llm_mode = self.mode_var.get()
        c.llm_base_url = self.url_var.get().strip()
        c.llm_api_key = self.key_var.get().strip() or "local"
        c.llm_model = self.model_var.get().strip()
        try:
            c.concurrency = max(1, int(self.conc_var.get()))
        except (tk.TclError, ValueError):
            c.concurrency = 1
        self._refresh_summary()
        return c

    def _save(self) -> None:
        self._apply_fields().save_settings()
        self._set_server_status(f"Saved to {SETTINGS_PATH.name}.", _OK)

    def _test_connection(self) -> None:
        self._apply_fields()
        self._set_server_status(f"Connecting to {host_of(self.config.llm_base_url)} ...")
        self._fetch_models()

    def _fetch_models(self) -> None:
        threading.Thread(target=self._load_models, daemon=True).start()

    def _load_models(self) -> None:
        try:
            from .llm_client import list_models

            models = list_models(self.config)
        except Exception as exc:
            self.queue.put(("server_error", f"Could not reach {host_of(self.config.llm_base_url)}: {exc}"))
            return
        self.queue.put(("models", models))

    def _on_model_selected(self) -> None:
        """Picking a model in the dropdown loads it on the server right away."""
        self._apply_fields()
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self) -> None:
        try:
            from .llm_client import ensure_model_loaded

            state = ensure_model_loaded(
                self.config, log=lambda text: self.queue.put(("server_status", (text, "gray")))
            )
        except Exception as exc:
            self.queue.put(("server_error", f"Could not load {self.config.llm_model}: {exc}"))
            return
        verb = "is loaded and ready" if state == "ready" else "is now loaded"
        self.queue.put(("server_status", (f"{self.config.llm_model} {verb}.", _OK)))

    def _refresh_summary(self) -> None:
        if self._server_alert:
            self.summary.configure(text=unreachable_text(self.config.llm_base_url),
                                   foreground=_ERR, cursor="hand2")
            return
        self.summary.configure(text=summary_text(self.config),
                               foreground=_WARN if self.config.is_hosted else "gray", cursor="")

    def _set_server_alert(self, on: bool) -> None:
        """Red dot on the Server tab + red clickable summary while the server is unreachable."""
        self._server_alert = on
        self.notebook.tab(self._server_tab_index, image=self._dot if on else "", compound="right")
        self._refresh_summary()

    # ---------- match tab actions ----------

    def _browse_job(self) -> None:
        if self.busy:
            return
        path = filedialog.askopenfilename(
            title="Choose a job posting",
            filetypes=[("Job postings", "*.txt *.md *.eml *.pdf *.docx *.doc"), ("All files", "*.*")],
        )
        if path:
            self._start(Path(path))

    def _on_drop(self, event) -> None:  # pragma: no cover - needs a real DnD event
        self._draw_zone()
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self._start(Path(paths[0]))

    def _run_all(self) -> None:
        self._start(None)

    def _open_report(self) -> None:
        if self.last_report:
            webbrowser.open(self.last_report.resolve().as_uri())

    def _start(self, job_file: Path | None) -> None:
        if self.busy:
            return
        self._apply_fields().save_settings()  # what you see is what runs, and it persists
        if not self.config.llm_model:
            self._set_status("Set a model on the Server tab first.", error=True)
            self.notebook.select(1)
            return
        self.busy = True
        self.run_all_btn.configure(state="disabled")
        self.progress.configure(value=0)
        self._set_status("Working...")
        threading.Thread(target=self._work, args=(job_file,), daemon=True).start()

    # ---------- worker ----------

    def _work(self, job_file: Path | None) -> None:
        """Runs off the UI thread; all output goes through the queue."""
        writer = _QueueWriter(self.queue)
        try:
            with redirect_stdout(writer):
                from .documents import load_resumes
                from .email_ingest import load_job_from_file, load_jobs_from_folder
                from .matcher import run
                from .report import write_report

                config = self.config
                try:
                    from .llm_client import list_models

                    list_models(config)
                except Exception as exc:
                    msg = f"Cannot reach the model server at {host_of(config.llm_base_url)}: {exc}"
                    self.queue.put(("server_error", msg))
                    raise RuntimeError(msg) from exc
                # Load the model if the server has none loaded, so a run does
                # not fail once per resume with "No model loaded".
                try:
                    from .llm_client import ensure_model_loaded

                    ensure_model_loaded(config)
                except Exception as exc:
                    msg = f"Model {config.llm_model} is not ready on the server: {exc}"
                    self.queue.put(("server_error", msg))
                    raise RuntimeError(msg) from exc

                resumes = load_resumes(config.resumes_dir)
                if not resumes:
                    raise RuntimeError(f"No resumes found in {config.resumes_dir.resolve()}")

                if job_file is None:
                    jobs = load_jobs_from_folder(config.jobs_dir)
                    if not jobs:
                        raise RuntimeError(f"No job postings found in {config.jobs_dir.resolve()}")
                else:
                    jobs = [load_job_from_file(job_file)]

                print(f"Matching {len(jobs)} job(s) against {len(resumes)} resume(s) "
                      f"using {config.llm_model} @ {host_of(config.llm_base_url)}"
                      f"{' (hosted)' if config.is_hosted else ''}")
                top = run(config, jobs, resumes)
                report = write_report(top, config.results_dir)
                print(f"Report saved to {report}")
            writer.flush()
            self.queue.put(("done", report))
        except Exception as exc:
            writer.flush()
            self.queue.put(("error", str(exc)))

    # ---------- UI queue pump ----------

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                try:
                    self._handle(kind, payload)
                except Exception as exc:  # a handler bug must not stop the pump
                    self._append(f"[internal error] {kind}: {exc}")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _handle(self, kind: str, payload) -> None:
        if kind == "log":
            self._append(payload)
            match = _PROGRESS_RE.search(payload)
            if match:
                done, total = int(match.group(1)), int(match.group(2))
                self.progress.configure(maximum=total, value=done)
                self._set_status(f"Scoring {done}/{total}...")
        elif kind == "models":
            self._set_models(payload)
        elif kind == "server_status":
            text, color = payload
            self._set_server_status(text, color)
            self._append(text)
        elif kind == "server_error":
            self._set_server_status(payload, _ERR)
            self._append(f"[warn] {payload}")
            self._set_server_alert(True)
        elif kind == "done":
            self._finish(payload)
        elif kind == "error":
            self._append(f"[error] {payload}")
            self._set_status(payload, error=True)
            self._idle()

    def _set_models(self, models: list[str]) -> None:
        self._set_server_alert(False)
        self.model_box.configure(values=models)
        if models and not self.config.is_hosted and self.model_var.get() not in models:
            # Local servers report a handful of ids; preselect the configured
            # one by substring. Hosted lists are huge, so leave the text alone.
            self.model_var.set(pick_default_model(models, self.config.llm_model))
            self._apply_fields()
        shown = ", ".join(models[:8]) + (" ..." if len(models) > 8 else "")
        self._set_server_status(f"Connected: {len(models)} model(s). {shown}", _OK)
        self._append(f"Models on server ({len(models)}): {shown}")

    def _finish(self, report: Path) -> None:
        self.last_report = report
        self.open_btn.configure(state="normal")
        self.progress.configure(value=self.progress["maximum"])
        self._set_status(f"Done - {report.name}")
        self._idle()
        webbrowser.open(report.resolve().as_uri())

    def _idle(self) -> None:
        self.busy = False
        self.run_all_btn.configure(state="normal")

    def _append(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.configure(text=text, foreground=_ERR if error else "gray")

    def _set_server_status(self, text: str, color: str = "gray") -> None:
        self.server_status.configure(text=text, foreground=color)

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    MatcherWindow().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
