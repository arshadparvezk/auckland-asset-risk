@echo off
setlocal
cd /d "%~dp0\..\.."

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: The project environment is missing.
  echo Run scripts\windows\setup.bat first.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
set "PIPELINE_REFRESH="
if /I "%~1"=="--refresh" set "PIPELINE_REFRESH=--refresh"

echo Running the complete financial-risk modelling pipeline...
python -m asset_risk.pipeline --project-root . %PIPELINE_REFRESH%
if errorlevel 1 goto :failed

echo Rebuilding the standalone recruiter dashboard...
python scripts\build_static_dashboard.py
if errorlevel 1 goto :failed

echo.
echo PIPELINE COMPLETED SUCCESSFULLY.
echo Run scripts\windows\run_dashboard.bat to explore the outputs.
pause
exit /b 0

:failed
echo.
echo PIPELINE FAILED. Review the error above and see LAPTOP_SETUP_GUIDE.md.
pause
exit /b 1
