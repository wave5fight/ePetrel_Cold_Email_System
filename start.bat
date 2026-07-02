@echo off
setlocal

cd /d "%~dp0"

set "APP_HOST=127.0.0.1"
set "APP_PORT=8000"
set "APP_URL=http://%APP_HOST%:%APP_PORT%"
set "PYTHON_EXE=%CD%\python_env\python.exe"

title ePetrel Cold Email System

echo.
echo ==========================================
echo   ePetrel Cold Email System - Windows
echo ==========================================
echo.

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Missing Windows embedded Python:
  echo         %PYTHON_EXE%
  echo.
  echo Please make sure the python_env folder is included next to start.bat.
  echo.
  pause
  exit /b 1
)

if not exist "web_app.py" (
  echo [ERROR] web_app.py was not found.
  echo Please run this script from the project folder.
  echo.
  pause
  exit /b 1
)

if not exist "templates" (
  echo [ERROR] templates folder was not found.
  echo.
  pause
  exit /b 1
)

if not exist "static" (
  echo [ERROR] static folder was not found.
  echo.
  pause
  exit /b 1
)

if not exist "database" mkdir database
if not exist "logs" mkdir logs

echo Starting local server at %APP_URL%
echo Keep this window open while using ePetrel.
echo.

start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '%APP_URL%'"

"%PYTHON_EXE%" -m uvicorn web_app:app --host %APP_HOST% --port %APP_PORT%

echo.
echo ePetrel has stopped. If this was unexpected, check the error message above.
pause
