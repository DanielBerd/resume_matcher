#!/usr/bin/env python3
"""Double-click launcher for the Outlook inbox watcher.

Polls your (classic) Windows Outlook inbox for unread job emails, scores every
resume in ``resumes/`` against each one, and emails the ranked results back to
the sender. Keeps running until you close the window. Requires native Windows
with the classic Outlook desktop app; see the README for details.
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
        from resume_matcher.email_watch import main as watch_main
    except ModuleNotFoundError as exc:
        print(f"Missing dependency: {exc.name}\n")
        print("Install the requirements first, from this folder:")
        print("    python -m pip install -r requirements.txt")
        return 1
    return watch_main([])


if __name__ == "__main__":
    code = 1
    try:
        code = _run()
    except KeyboardInterrupt:
        print("\nStopped.")
        code = 0
    except Exception:
        traceback.print_exc()
    input("\nPress Enter to close this window...")
    sys.exit(code)
