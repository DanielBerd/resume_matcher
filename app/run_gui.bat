@echo off
REM Double-click launcher for the Resume Matcher window (Windows).
REM Uses pythonw so only the app window appears - no console behind it.
REM Started by ResumeMatcher.bat one folder up; can also be run directly.
REM Any startup problem is reported in a dialog box by run_gui.py.

cd /d "%~dp0"

REM "where" is not enough to detect Python: Windows 10/11 ship a python.exe
REM stub that only opens the Microsoft Store, and it would be found. So each
REM candidate is actually run first; the stub fails that check, real ones pass.
pyw -c "" >nul 2>nul && (
    start "" pyw run_gui.py
    goto :eof
)
pythonw -c "" >nul 2>nul && (
    start "" pythonw run_gui.py
    goto :eof
)
REM No windowless interpreter found: fall back to a console one.
py -c "" >nul 2>nul && (
    py run_gui.py
    goto :eof
)
python -c "" >nul 2>nul && (
    python run_gui.py
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
