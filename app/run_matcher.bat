@echo off
REM Double-click launcher for resume_matcher on Windows.
REM Runs the tool with whichever Python is installed. No terminal needed.

cd /d "%~dp0"

REM Prefer the "py" launcher, then fall back to "python".
where py >nul 2>nul && (
    py run_matcher.py
    goto :eof
)
where python >nul 2>nul && (
    python run_matcher.py
    goto :eof
)

echo Python was not found on this computer.
echo.
echo Install Python from https://www.python.org/downloads/ and be sure to
echo tick "Add Python to PATH" during installation, then run this again.
echo.
pause
