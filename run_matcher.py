#!/usr/bin/env python3
"""Double-click launcher for resume_matcher.

Only Python needs to be installed: the first run creates a private
environment next to the code and installs the dependencies into it. Then it
scores everything in jobs/ against resumes/, opens the HTML report, and keeps
the window open so you can read any messages.

Advanced usage (flags, test mode) still lives in ``python -m resume_matcher``."""

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

    from resume_matcher.cli import main as entry

    return entry(["--open"])


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
