@echo off
REM Double-click to start Resume Matcher. Everything it needs is in app\.
REM If Python is not installed, the window that opens says where to get it.

REM First run: put a "Resume Matcher" shortcut next to this file. It carries
REM the app icon (a .bat cannot), can be pinned to Start or copied to the
REM desktop, and starts this console minimized so nothing flashes on screen.
if not exist "%~dp0Resume Matcher.lnk" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%~dp0Resume Matcher.lnk');" ^
        "$s.TargetPath = '%~dp0ResumeMatcher.bat';" ^
        "$s.WorkingDirectory = '%~dp0';" ^
        "$s.IconLocation = '%~dp0app\resume_matcher\icon.ico';" ^
        "$s.WindowStyle = 7;" ^
        "$s.Description = 'Resume Matcher';" ^
        "$s.Save()" >nul 2>nul
)

cd /d "%~dp0app"
call run_gui.bat
