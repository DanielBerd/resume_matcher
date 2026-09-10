# Double-click this file on Windows to start Resume Matcher with no console
# window at all - not even the brief flash a .bat file shows. It simply runs
# run_gui.py; keep both files together.
import runpy
import sys
from pathlib import Path

script = Path(__file__).resolve().with_suffix(".py")
sys.argv[0] = str(script)
runpy.run_path(str(script), run_name="__main__")
