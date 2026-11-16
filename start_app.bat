@echo off
rem ベール製造計画アプリを起動する（ダブルクリックで実行）
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m bale_planner.app %*
