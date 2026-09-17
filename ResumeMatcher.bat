@echo off
REM Double-click to start Resume Matcher. Everything it needs is in app\.
REM If Python is not installed, the window that opens says where to get it.

REM First run: create the "Resume Matcher" shortcuts (here and in the Start
REM Menu). They carry the app icon, start without a console flash, and are
REM what makes pinning to the taskbar work. See app\make_shortcut.ps1.
if not exist "%~dp0Resume Matcher.lnk" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\make_shortcut.ps1" -Root "%~dp0." >nul 2>nul
)

cd /d "%~dp0app"
call run_gui.bat
