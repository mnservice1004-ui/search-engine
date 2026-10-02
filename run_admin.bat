@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo 먼저 setup_admin.bat을 실행하십시오.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" admin\launch.py
if errorlevel 1 pause
