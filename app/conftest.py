"""Make the package and bootstrap importable when pytest runs from any directory."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
