@echo off
rem Start Bale Planner in full screen (tablet). Press F11 to toggle.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m bale_planner.app --fullscreen %*
