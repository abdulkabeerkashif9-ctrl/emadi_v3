@echo off
setlocal
cd /d "%~dp0"
title ERP Fleet Manager

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Python 3.10+ was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer, then run this again.
  goto :end
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 ( echo Failed to create the virtual environment. & goto :end )
)

if not exist ".venv\.deps_ok" (
  echo Installing dependencies - first run only...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 ( echo Dependency install failed. Check your internet connection. & goto :end )
  echo ok> ".venv\.deps_ok"
)

echo.
echo Starting on http://localhost:8800  (close this window to stop)
".venv\Scripts\python.exe" -m fleetmanager --port 8800
echo.
echo The server stopped - see the message above.

:end
pause
