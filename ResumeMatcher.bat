@echo off
REM Double-click to start Resume Matcher. Everything it needs is in app\.
REM If Python is not installed, the window that opens says where to get it.
cd /d "%~dp0app"
call run_gui.bat
