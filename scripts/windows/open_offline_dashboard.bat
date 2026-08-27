@echo off
setlocal
cd /d "%~dp0\..\.."

if not exist "dashboard\index.html" (
  echo ERROR: The offline dashboard is missing.
  echo Run scripts\windows\run_pipeline.bat to rebuild it.
  pause
  exit /b 1
)

echo Opening the self-contained offline dashboard...
start "" "%CD%\dashboard\index.html"
