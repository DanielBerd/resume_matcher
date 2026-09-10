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

import queue
import re
import sys
import threading
import tkinter as tk
import webbrowser
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import filedialog, ttk
from urllib.parse import urlparse

from .config import SETTINGS_PATH, Config
from .providers import HOSTED, LOCAL, find, pick_default_model, provider_names

try:  # optional: enables real drag-and-drop
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND = True
except ImportError:  # pragma: no cover - depends on optional install
    _DND = False

_PROGRESS_RE = re.compile(r"\[(\d+)/(\d+) total")
_WARN = "#b45309"
_ERR = "#b42318"
_OK = "#1a7f37"


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

        self.root = TkinterDnD.Tk() if _DND else tk.Tk()
        self.root.title("Resume Matcher")
        self.root.geometry("640x600")
        self.root.minsize(540, 500)
        self._build()
        self.root.after(100, self._drain)
        # A local server is cheap to ask; a hosted API is only queried on demand.
        if not self.config.is_hosted:
            self._fetch_models()

    # ---------- layout ----------

    def _build(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        match_tab = ttk.Frame(self.notebook)
        server_tab = ttk.Frame(self.notebook)
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
        pad = {"padx": 10, "pady": 6}
        self.summary = ttk.Label(tab, text="", foreground="gray", wraplength=600, justify="left")
        self.summary.pack(anchor="w", padx=10, pady=(8, 0))
        self.summary.bind("<Button-1>", lambda _e: self._server_alert and self.notebook.select(self._server_tab_index))

        # Drop zone
        self.zone = tk.Canvas(tab, height=130, highlightthickness=0)
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
        self.run_all_btn = ttk.Button(actions, text="Run all jobs in jobs/ folder", command=self._run_all)
        self.run_all_btn.pack(side="left")
        self.open_btn = ttk.Button(actions, text="Open last report", command=self._open_report, state="disabled")
        self.open_btn.pack(side="left", padx=8)

        self.progress = ttk.Progressbar(tab, mode="determinate")
        self.progress.pack(fill="x", padx=10)
        self.status = ttk.Label(tab, text="Ready", foreground="gray")
        self.status.pack(anchor="w", padx=10, pady=(4, 0))

        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        self.log = tk.Text(frame, height=10, wrap="word", state="disabled",
                           bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4",
                           font=("Consolas" if sys.platform == "win32" else "monospace", 9))
        bar = ttk.Scrollbar(frame, command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    def _build_server_tab(self, tab: ttk.Frame) -> None:
        c = self.config
        form = ttk.Frame(tab)
        form.pack(fill="x", padx=12, pady=12)
        form.columnconfigure(1, weight=1)
        row = 0

        def label(text: str) -> None:
            ttk.Label(form, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))

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
        ttk.Button(form, text="Fetch models", command=self._fetch_models).grid(row=row, column=2, padx=(8, 0))
        row += 1

        label("Concurrency:")
        self.conc_var = tk.IntVar(value=c.concurrency)
        conc = ttk.Frame(form)
        conc.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Spinbox(conc, from_=1, to=16, width=5, textvariable=self.conc_var).pack(side="left")
        ttk.Label(conc, text="requests in flight (match the server's parallel slots)",
                  foreground="gray").pack(side="left", padx=(8, 0))
        row += 1

        self.privacy = ttk.Label(form, text="", foreground=_WARN, wraplength=560, justify="left")
        self.privacy.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 2))
        row += 1

        buttons = ttk.Frame(form)
        buttons.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(buttons, text="Test connection", command=self._test_connection).pack(side="left")
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left", padx=8)
        row += 1

        self.server_status = ttk.Label(form, text="", foreground="gray", wraplength=560, justify="left")
        self.server_status.grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 0))
        row += 1

        ttk.Label(form, text=f"Settings are saved to app/{SETTINGS_PATH.name} (kept out of git). "
                             "Runs use the values shown here.",
                  foreground="gray", wraplength=560, justify="left"
                  ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self._on_mode()

    def _draw_zone(self, hover: bool = False) -> None:
        c = self.zone
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        c.configure(bg="#e8f0fe" if hover else "#f3f4f6")
        c.create_rectangle(6, 6, w - 6, h - 6, dash=(6, 4), outline="#9aa4b2", width=2)
        headline = "Drop a job posting here" if _DND else "Click to choose a job posting"
        c.create_text(w // 2, h // 2 - 12, text=headline, font=("", 12, "bold"), fill="#374151")
        sub = "or click to browse  -  .txt .eml .pdf .docx" if _DND else ".txt .eml .pdf .docx"
        c.create_text(w // 2, h // 2 + 12, text=sub, font=("", 9), fill="#6b7280")

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
