#!/usr/bin/env python3
"""Double-click launcher for resume_matcher.

For users who would rather click a file than type commands: this runs the
matcher against the ``jobs/`` and ``resumes/`` folders next to it, then opens
the HTML report in your browser. On Windows you can double-click this file;
elsewhere run ``python run_matcher.py``.

Advanced usage (flags, test mode) still lives in ``python -m resume_matcher``.
"""

import os
import sys
import traceback
from pathlib import Path


def _run() -> int:
    # A double-click can start us in a different working directory, so anchor
    # to this file's folder and make the package importable from here.
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root))

    try:
        from resume_matcher.cli import main as cli_main
    except ModuleNotFoundError as exc:
        print(f"Missing dependency: {exc.name}\n")
        print("Install the requirements first, from this folder:")
        print("    python -m pip install -r requirements.txt")
        return 1

    # --open pops the HTML report; the rest uses defaults (jobs/, resumes/,
    # and the interactive model picker).
    return cli_main(["--open"])


if __name__ == "__main__":
    code = 1
    try:
        code = _run()
    except KeyboardInterrupt:
        print("\nCancelled.")
    except Exception:
        traceback.print_exc()
    # Keep the console open so a double-click user can read the output.
    input("\nPress Enter to close this window...")
    sys.exit(code)
