#!/usr/bin/env python3
"""Double-click launcher for the Resume Matcher window.

Opens a small desktop app: drop a job posting on it to score that one job
against every resume, or press the button to run all postings in ``jobs/``.
"""

import os
import sys
import traceback
from pathlib import Path


def _run() -> int:
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root))
    try:
        from resume_matcher.gui import main as gui_main
    except ModuleNotFoundError as exc:
        if exc.name == "tkinter":
            print("Python is installed without tkinter, which this window needs.\n")
            print("On Windows, re-run the Python installer and enable 'tcl/tk and IDLE'.")
            print("On Linux, install it with:  sudo apt install python3-tk")
        else:
            print(f"Missing dependency: {exc.name}\n")
            print("Install the requirements first, from this folder:")
            print("    python -m pip install -r requirements.txt")
        return 1
    return gui_main()


if __name__ == "__main__":
    code = 1
    try:
        code = _run()
    except KeyboardInterrupt:
        code = 0
    except Exception:
        traceback.print_exc()
        input("\nPress Enter to close this window...")
    sys.exit(code)
