@echo off
rem Start the app from source (development). Installed PCs use the Start menu shortcut.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m bale_planner.app %*
