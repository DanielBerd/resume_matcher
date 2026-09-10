#!/usr/bin/env python3
"""Double-click launcher for the Resume Matcher window.

The only thing that needs to be installed beforehand is Python itself. On
first run this creates a private environment next to the code and installs
the dependencies into it, showing progress in a small window; afterwards it
just opens the app. Started by ``run_gui.bat`` through ``pythonw`` on
Windows, so there is no console - problems are reported in a dialog.
"""

import os
import sys
import threading
import traceback
from pathlib import Path

TITLE = "Resume Matcher"
ROOT = Path(__file__).resolve().parent


def alert(message: str) -> None:
    """Show a message without assuming a console exists."""
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(TITLE, message)
        root.destroy()
        return
    except Exception:
        pass
    if sys.platform == "win32":  # tkinter itself may be what is broken
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)
            return
        except Exception:
            pass
    print(message)


def run_app() -> int:
    """Inside the venv: start the window."""
    sys.path.insert(0, str(ROOT))
    try:
        from resume_matcher.gui import main as gui_main
    except ModuleNotFoundError as exc:
        if exc.name == "tkinter":
            alert("Python is installed without tkinter, which this window needs.\n\n"
                  "On Windows, re-run the Python installer and enable 'tcl/tk and IDLE'.\n"
                  "On Linux, install it with:  sudo apt install python3-tk")
        else:
            alert(f"Missing dependency: {exc.name}\n\nDelete the .venv folder next to "
                  "run_gui.py and start it again to reinstall.")
        return 1
    return gui_main()


def setup_then_launch() -> int:
    """Outside the venv: prepare it with visible progress, then relaunch."""
    import bootstrap

    problem = bootstrap.python_ok()
    if problem:
        alert(problem)
        return 1

    # Fast path: everything already installed - no window needed.
    if bootstrap.venv_python().exists() and bootstrap.deps_current():
        bootstrap.relaunch(Path(__file__), sys.argv[1:], windowless=True, wait=False)
        return 0

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        # No window possible: do it in the console instead.
        try:
            bootstrap.ensure_ready(print)
        except RuntimeError as exc:
            print(exc)
            return 1
        return bootstrap.relaunch(Path(__file__), sys.argv[1:])

    root = tk.Tk()
    root.title(f"{TITLE} - first-time setup")
    root.geometry("560x340")
    ttk.Label(root, text="Setting things up. This only happens once.",
              font=("", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
    ttk.Label(root, text="Creating a private Python environment and installing dependencies.",
              foreground="gray").pack(anchor="w", padx=14)
    bar = ttk.Progressbar(root, mode="indeterminate")
    bar.pack(fill="x", padx=14, pady=8)
    bar.start(12)
    log = tk.Text(root, height=10, wrap="word", state="disabled", bg="#1e1e1e", fg="#d4d4d4",
                  font=("Consolas" if sys.platform == "win32" else "monospace", 9))
    log.pack(fill="both", expand=True, padx=14, pady=(0, 12))
    outcome: dict = {}

    def append(line: str) -> None:
        def _do():
            log.configure(state="normal")
            log.insert("end", line + "\n")
            log.see("end")
            log.configure(state="disabled")
        root.after(0, _do)

    def work() -> None:
        try:
            bootstrap.ensure_ready(append)
            append("Starting the app ...")
            outcome["ok"] = True
        except Exception as exc:
            outcome["error"] = str(exc)
        root.after(0, finish)

    def finish() -> None:
        bar.stop()
        if outcome.get("ok"):
            bootstrap.relaunch(Path(__file__), sys.argv[1:], windowless=True, wait=False)
            root.after(400, root.destroy)
        else:
            append("")
            append("Setup failed: " + outcome.get("error", "unknown error"))
            ttk.Button(root, text="Close", command=root.destroy).pack(pady=(0, 10))

    threading.Thread(target=work, daemon=True).start()
    root.mainloop()
    return 0 if outcome.get("ok") else 1


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    code = 1
    try:
        import bootstrap

        code = run_app() if bootstrap.running_inside_venv() else setup_then_launch()
    except KeyboardInterrupt:
        code = 0
    except Exception:
        alert("The window could not start:\n\n" + traceback.format_exc())
    sys.exit(code)
