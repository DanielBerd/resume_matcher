@echo off
REM Double-click launcher for the Resume Matcher window (Windows).

cd /d "%~dp0"

where py >nul 2>nul && (
    py run_gui.py
    goto :eof
)
where python >nul 2>nul && (
    python run_gui.py
    goto :eof
)

echo Python was not found on this computer.
echo.
echo Install Python from https://www.python.org/downloads/ and be sure to
echo tick "Add Python to PATH" during installation, then run this again.
echo.
pause
