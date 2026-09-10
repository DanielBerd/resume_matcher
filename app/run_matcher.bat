@echo off
REM Double-click launcher for resume_matcher on Windows.
REM Runs the tool with whichever Python is installed. No terminal needed.

cd /d "%~dp0"

REM "where" is not enough to detect Python: Windows 10/11 ship a python.exe
REM stub that only opens the Microsoft Store, and it would be found. So each
REM candidate is actually run first; the stub fails that check, real ones pass.
py -c "" >nul 2>nul && (
    py run_matcher.py
    goto :eof
)
python -c "" >nul 2>nul && (
    python run_matcher.py
    goto :eof
)

echo Python was not found on this computer.
echo.
echo Install Python 3.10 or newer from https://www.python.org/downloads/
echo and tick "Add Python to PATH" during installation, then run this again.
echo.
echo (If Windows offers to install Python from the Microsoft Store instead,
echo that works too.)
echo.
pause
