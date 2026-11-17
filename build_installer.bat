@echo off
rem Build the installer (double-click). Output: dist folder
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File installer\build.ps1
pause
