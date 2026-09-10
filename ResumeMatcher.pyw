# Double-click this file to start Resume Matcher.
#
# Windows opens .pyw files with no console window. The first run sets up a
# private Python environment in app/ (a minute or two, with a progress bar);
# after that the window opens straight away. On macOS or Linux run:
#     python ResumeMatcher.pyw
#
# If double-clicking opens this file in an editor instead of running it, use
# app\run_gui.bat, or right-click -> Open with -> Python.
import runpy
import sys
from pathlib import Path

script = Path(__file__).resolve().parent / "app" / "run_gui.py"
sys.argv[0] = str(script)
runpy.run_path(str(script), run_name="__main__")
