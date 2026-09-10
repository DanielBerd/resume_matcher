@echo off
REM Double-click launcher for the Outlook inbox watcher (Windows).
REM Polls Outlook for job emails and replies with resume matches.

cd /d "%~dp0"

where py >nul 2>nul && (
    py watch_inbox.py
    goto :eof
)
where python >nul 2>nul && (
    python watch_inbox.py
    goto :eof
)

echo Python was not found on this computer.
echo.
echo Install Python from https://www.python.org/downloads/ and be sure to
echo tick "Add Python to PATH" during installation, then run this again.
echo.
pause
