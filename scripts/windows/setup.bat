@echo off
setlocal
cd /d "%~dp0\..\.."

echo ============================================================
echo Auckland Asset Risk - Windows environment setup
echo ============================================================

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python Launcher was not found.
  echo Install 64-bit Python 3.11 from https://www.python.org/downloads/
  echo Select "Add python.exe to PATH" during installation.
  pause
  exit /b 1
)

py -3.11 --version >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python 3.11 is not installed.
  echo Install 64-bit Python 3.11 and run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the project virtual environment...
  py -3.11 -m venv .venv
  if errorlevel 1 goto :failed
) else (
  echo Existing virtual environment found.
)

call ".venv\Scripts\activate.bat"
echo Updating packaging tools...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :failed

echo Installing the project and development dependencies...
python -m pip install -e ".[dev]"
if errorlevel 1 goto :failed

echo Running automated model tests...
python -m pytest -q
if errorlevel 1 goto :failed

echo.
echo SETUP COMPLETED SUCCESSFULLY.
echo Next: run scripts\windows\run_dashboard.bat
pause
exit /b 0

:failed
echo.
echo SETUP FAILED. Review the error above and see README.md.
pause
exit /b 1
