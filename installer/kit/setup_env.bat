@echo off
rem ===========================================================================
rem  Bale Planner - setup on the customer PC (run once, double-click)
rem  Requires: Python 3.11+ (python.org) installed with tcl/tk.
rem  Creates .venv in this folder and installs packages from .\wheels (offline).
rem ===========================================================================
setlocal
cd /d "%~dp0"

echo [1/4] Checking Python...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if errorlevel 1 goto nopython
%PY% -c "import sys; print('      Python', sys.version.split()[0], sys.executable)"
%PY% -c "import tkinter" 2>nul
if errorlevel 1 goto notk

echo [2/4] Creating virtual environment (.venv)...
if exist ".venv" rmdir /s /q ".venv"
%PY% -m venv .venv
if errorlevel 1 goto fail

echo [3/4] Installing packages from .\wheels (no internet needed)...
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt --disable-pip-version-check -q
if errorlevel 1 goto fail

echo [4/4] Self check...
".venv\Scripts\python.exe" -m bale_planner.app --check setup_check.txt
set "RC=%errorlevel%"
type setup_check.txt
echo.
if not "%RC%"=="0" goto fail

echo ===========================================================================
echo  SETUP COMPLETED.  Start the app with start_app.bat
echo  (tablet full screen: start_app_fullscreen.bat)
echo ===========================================================================
pause
exit /b 0

:nopython
echo.
echo ERROR: Python 3.11 or later was not found.
echo   Install Python from python.org (see docs: install_python.md, step 2),
echo   then run this file again.
pause
exit /b 1

:notk
echo.
echo ERROR: tkinter is not available in this Python.
echo   Re-run the Python installer, choose "Modify" and check "tcl/tk and IDLE".
pause
exit /b 1

:fail
echo.
echo ERROR: setup failed. Send the messages above to the developer.
pause
exit /b 1
