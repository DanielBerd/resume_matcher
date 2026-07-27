#!/usr/bin/env python3
"""Double-click launcher for the Resume Matcher window.

Opens a small desktop app: drop a job posting on it to score that one job
against every resume, or press the button to run all postings in ``jobs/``.

This is normally started by ``run_gui.bat`` through ``pythonw``, so there is
no console window - problems are reported in a dialog box instead of printed.
"""

import os
import sys
import traceback
from pathlib import Path

TITLE = "Resume Matcher"


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


def _run() -> int:
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root))
    try:
        from resume_matcher.gui import main as gui_main
    except ModuleNotFoundError as exc:
        if exc.name == "tkinter":
            alert(
                "Python is installed without tkinter, which this window needs.\n\n"
                "On Windows, re-run the Python installer and enable "
                "'tcl/tk and IDLE'.\n"
                "On Linux, install it with:  sudo apt install python3-tk"
            )
        else:
            alert(
                f"Missing dependency: {exc.name}\n\n"
                "Install the requirements first, from this folder:\n"
                "    python -m pip install -r requirements.txt"
            )
        return 1
    return gui_main()


if __name__ == "__main__":
    code = 1
    try:
        code = _run()
    except KeyboardInterrupt:
        code = 0
    except Exception:
        alert("The window could not start:\n\n" + traceback.format_exc())
    sys.exit(code)
