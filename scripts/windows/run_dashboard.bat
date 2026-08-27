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
echo Starting the Auckland Asset Risk dashboard...
echo Your browser should open at http://localhost:8501
echo Press Ctrl+C in this window to stop the dashboard.
python -m streamlit run app.py
