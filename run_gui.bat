@echo off
REM Double-click launcher for the Resume Matcher window (Windows).
REM Uses pythonw so only the app window appears - no console behind it.
REM Any startup problem is reported in a dialog box by run_gui.py.

cd /d "%~dp0"

REM "start" lets this script exit immediately so its console does not linger.
where pyw >nul 2>nul && (
    start "" pyw run_gui.py
    goto :eof
)
where pythonw >nul 2>nul && (
    start "" pythonw run_gui.py
    goto :eof
)

REM No windowless interpreter found: fall back to a console one.
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
