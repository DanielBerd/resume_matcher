"""A small desktop window for running the matcher without a terminal.

Two ways to start a run:
  * Drop a single job posting file on the drop zone (or click it to browse) -
    that one job is scored against every resume in the resumes folder.
  * Press "Run all jobs" to score every posting in the jobs folder, the same
    as `python -m resume_matcher`.

Real drag-and-drop needs the optional ``tkinterdnd2`` package; without it the
drop zone still works as a click-to-browse button.

Heavy imports (the LLM client, document parsing) are deliberately deferred to
the worker thread so the window appears instantly.
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

from .config import Config

try:  # optional: enables real drag-and-drop
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND = True
except ImportError:  # pragma: no cover - depends on optional install
    _DND = False

_PROGRESS_RE = re.compile(r"\[(\d+)/(\d+) total")


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
        self.config = config or Config()
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.last_report: Path | None = None

        self.root = TkinterDnD.Tk() if _DND else tk.Tk()
        self.root.title("Resume Matcher")
        self.root.geometry("620x560")
        self.root.minsize(520, 460)
        self._build()
        self.root.after(100, self._drain)
        # Populate the model list without blocking the window from appearing.
        threading.Thread(target=self._load_models, daemon=True).start()

    # ---------- layout ----------

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Model:").pack(side="left")
        self.model_var = tk.StringVar(value=self.config.llm_model)
        self.model_box = ttk.Combobox(top, textvariable=self.model_var, state="readonly")
        self.model_box.pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(top, text="Refresh", width=9, command=self._refresh_models).pack(side="left")

        # Drop zone
        self.zone = tk.Canvas(self.root, height=130, highlightthickness=0)
        self.zone.pack(fill="x", **pad)
        self.zone.bind("<Configure>", lambda _e: self._draw_zone())
        self.zone.bind("<Button-1>", lambda _e: self._browse_job())
        self.zone.configure(cursor="hand2")
        if _DND:
            self.zone.drop_target_register(DND_FILES)
            self.zone.dnd_bind("<<Drop>>", self._on_drop)
            self.zone.dnd_bind("<<DragEnter>>", lambda _e: self._draw_zone(hover=True))
            self.zone.dnd_bind("<<DragLeave>>", lambda _e: self._draw_zone())

        # Actions
        actions = ttk.Frame(self.root)
        actions.pack(fill="x", **pad)
        self.run_all_btn = ttk.Button(
            actions, text="Run all jobs in jobs/ folder", command=self._run_all
        )
        self.run_all_btn.pack(side="left")
        self.open_btn = ttk.Button(
            actions, text="Open last report", command=self._open_report, state="disabled"
        )
        self.open_btn.pack(side="left", padx=8)

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=12)
        self.status = ttk.Label(self.root, text="Ready", foreground="gray")
        self.status.pack(anchor="w", padx=12, pady=(4, 0))

        # Log
        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.log = tk.Text(frame, height=10, wrap="word", state="disabled",
                           bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4",
                           font=("Consolas" if sys.platform == "win32" else "monospace", 9))
        bar = ttk.Scrollbar(frame, command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    def _draw_zone(self, hover: bool = False) -> None:
        c = self.zone
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        bg = "#e8f0fe" if hover else "#f3f4f6"
        c.configure(bg=bg)
        c.create_rectangle(6, 6, w - 6, h - 6, dash=(6, 4), outline="#9aa4b2", width=2)
        headline = "Drop a job posting here" if _DND else "Click to choose a job posting"
        c.create_text(w // 2, h // 2 - 12, text=headline, font=("", 12, "bold"), fill="#374151")
        sub = "or click to browse  -  .txt .eml .pdf .docx" if _DND else ".txt .eml .pdf .docx"
        c.create_text(w // 2, h // 2 + 12, text=sub, font=("", 9), fill="#6b7280")

    # ---------- model list ----------

    def _load_models(self) -> None:
        try:
            from .llm_client import list_models

            models = list_models(self.config)
        except Exception as exc:
            self.queue.put(("models", []))
            self.queue.put(("log", f"[warn] could not reach the model server at "
                            f"{self.config.llm_base_url}: {exc}"))
            return
        self.queue.put(("models", models))

    def _refresh_models(self) -> None:
        self.queue.put(("log", "Refreshing model list..."))
        threading.Thread(target=self._load_models, daemon=True).start()

    # ---------- actions ----------

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
                config.llm_model = self.model_var.get() or config.llm_model

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
                      f"using {config.llm_model}")
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
                if kind == "log":
                    self._append(payload)
                    match = _PROGRESS_RE.search(payload)
                    if match:
                        done, total = int(match.group(1)), int(match.group(2))
                        self.progress.configure(maximum=total, value=done)
                        self._set_status(f"Scoring {done}/{total}...")
                elif kind == "models":
                    self._set_models(payload)
                elif kind == "done":
                    self._finish(payload)
                elif kind == "error":
                    self._append(f"[error] {payload}")
                    self._set_status(payload, error=True)
                    self._idle()
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _set_models(self, models: list[str]) -> None:
        self.model_box.configure(values=models)
        if models and self.model_var.get() not in models:
            from .cli import pick_default_model

            self.model_var.set(pick_default_model(models, self.config.llm_model))
        if models:
            self._append(f"Models on server: {', '.join(models)}")

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
        self.status.configure(text=text, foreground="#b42318" if error else "gray")

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    MatcherWindow().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
