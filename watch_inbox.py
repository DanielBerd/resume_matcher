#!/usr/bin/env python3
"""Double-click launcher for the Outlook inbox watcher.

Only Python needs to be installed: the first run creates a private
environment next to the code and installs the dependencies into it. Polls
your (classic) Windows Outlook inbox for unread job emails, scores every
resume in ``resumes/`` against each one, and emails the ranked results to
your own mailbox. Keeps running until you close the window. Requires native
Windows with the classic Outlook desktop app; see the README for details."""

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _run() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    import bootstrap

    if not bootstrap.running_inside_venv():
        # First run: set up the private environment (prints progress), then
        # run this same script inside it.
        problem = bootstrap.python_ok()
        if problem:
            print(problem)
            return 1
        try:
            bootstrap.ensure_ready(print)
        except RuntimeError as exc:
            print(exc)
            return 1
        return bootstrap.relaunch(Path(__file__), sys.argv[1:])

    from resume_matcher.email_watch import main as entry

    return entry([])


if __name__ == "__main__":
    code = 1
    try:
        code = _run()
    except KeyboardInterrupt:
        print("\nStopped.")
        code = 0
    except Exception:
        traceback.print_exc()
    if os.environ.get("RESUME_MATCHER_IN_VENV") == "1":
        input("\nPress Enter to close this window...")
    sys.exit(code)
