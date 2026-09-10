"""One-click setup shared by the launchers. Standard library only.

First run: create ``.venv`` next to this file, install requirements.txt into
it, and relaunch the launcher inside it. Later runs: a hash of
requirements.txt is compared to a stamp in the venv, so nothing is installed
unless the requirements changed, and the relaunch takes well under a second.

Callers pass a ``log`` callable (console print, or a GUI log) so the slow
first-time install is visible wherever it is happening.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / ".requirements.sha256"
MIN_PYTHON = (3, 10)
# Set on the relaunched process so it knows not to bootstrap again.
IN_VENV_FLAG = "RESUME_MATCHER_IN_VENV"


def quiet_subprocess_kwargs() -> dict:
    """Keyword arguments that keep a child process from showing a console.

    On Windows a console-subsystem child with no console gets a brand-new,
    visible one - and so do its own children. Hiding the window at creation
    time covers the whole subtree. Elsewhere there is nothing to hide.
    """
    if sys.platform != "win32":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def setup_interpreter(venv: Path = VENV) -> Path:
    """The venv interpreter used for ensurepip/pip during setup.

    On Windows that is pythonw.exe: a GUI-subsystem program cannot open a
    console, and neither can anything it launches via sys.executable (which
    is how ensurepip and pip run their helpers). This is what removes the
    console flash from first-time setup.
    """
    win = venv_python(venv, windowless=True)
    return win if sys.platform == "win32" and win.exists() else venv_python(venv)


def venv_python(venv: Path = VENV, windowless: bool = False) -> Path:
    """Interpreter inside the venv. windowless picks pythonw on Windows."""
    if sys.platform == "win32":
        return venv / "Scripts" / ("pythonw.exe" if windowless else "python.exe")
    return venv / "bin" / "python"


def running_inside_venv(venv: Path = VENV) -> bool:
    if os.environ.get(IN_VENV_FLAG) == "1":
        return True
    try:
        return Path(sys.prefix).resolve() == venv.resolve()
    except OSError:
        return False


def requirements_hash(path: Path = REQUIREMENTS) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deps_current(stamp: Path = STAMP, requirements: Path = REQUIREMENTS) -> bool:
    try:
        return stamp.read_text().strip() == requirements_hash(requirements)
    except OSError:
        return False


def python_ok() -> str | None:
    """None if this interpreter will do, else a message saying why not."""
    if sys.version_info < MIN_PYTHON:
        want = ".".join(map(str, MIN_PYTHON))
        have = ".".join(map(str, sys.version_info[:3]))
        return (f"Python {want} or newer is needed; this is {have}.\n"
                "Install a current Python from https://www.python.org/downloads/")
    return None


def ensure_ready(log=print, venv: Path = VENV, requirements: Path = REQUIREMENTS) -> Path:
    """Create the venv and install requirements as needed. Returns its python.

    Raises RuntimeError with a user-facing message on failure.
    """
    stamp = venv / STAMP.name
    py = venv_python(venv)
    if not py.exists():
        log(f"First-time setup: creating a private Python environment in {venv.name}/ ...")
        # with_pip=False: creating the interpreter is pure file copying with
        # no subprocess. pip is bootstrapped separately below, through an
        # interpreter that cannot pop up a console window.
        try:
            import venv as venv_mod

            venv_mod.EnvBuilder(with_pip=False, clear=False, symlinks=(sys.platform != "win32")).create(venv)
        except Exception as exc:
            raise RuntimeError(f"Could not create the environment: {exc}") from exc
        if not py.exists():
            raise RuntimeError(f"Environment was created but {py} is missing.")
        result = subprocess.run(
            [str(setup_interpreter(venv)), "-Im", "ensurepip", "--upgrade", "--default-pip"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", **quiet_subprocess_kwargs(),
        )
        if result.returncode != 0:  # ensurepip missing on some Linux system Pythons
            raise RuntimeError(
                "Could not set up pip in the environment:\n" + result.stdout.strip()[-400:] + "\n"
                "On Debian/Ubuntu install it with:  sudo apt install python3-venv\n"
                "Then run this again."
            )

    if not deps_current(stamp, requirements):
        log("Installing dependencies (this takes a minute or two the first time) ...")
        cmd = [str(setup_interpreter(venv)), "-m", "pip", "install", "--disable-pip-version-check",
               "--no-input", "-r", str(requirements)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                **quiet_subprocess_kwargs())
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line and not line.startswith("WARNING: Running pip as the 'root'"):
                log("  " + line)
        if proc.wait() != 0:
            raise RuntimeError(
                "Installing dependencies failed. Check your internet connection and "
                "try again, or install by hand:\n"
                f"    {py} -m pip install -r requirements.txt"
            )
        stamp.write_text(requirements_hash(requirements) + "\n")
        log("Dependencies installed.")
    return py


def relaunch(script: Path, args: list[str], windowless: bool = False, wait: bool = True) -> int:
    """Run ``script`` inside the venv. Returns its exit code (0 if not waiting)."""
    py = venv_python(VENV, windowless=windowless)
    if windowless and not py.exists():
        py = venv_python(VENV)  # no pythonw (non-Windows): plain python is fine
    env = {**os.environ, IN_VENV_FLAG: "1"}
    cmd = [str(py), str(script), *args]
    if wait:
        return subprocess.call(cmd, env=env)
    kwargs = quiet_subprocess_kwargs() if windowless else {}
    subprocess.Popen(cmd, env=env, **kwargs)
    return 0
