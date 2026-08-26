@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo 먼저 setup_windows.bat을 실행하십시오.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m streamlit run admin\dashboard.py
if errorlevel 1 pause
