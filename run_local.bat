@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo 먼저 setup_windows.bat을 실행하십시오.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
if not exist data\health_search.db (
  echo data\health_search.db가 없습니다. setup_windows.bat을 다시 실행하십시오.
  pause
  exit /b 1
)
python app.py
if errorlevel 1 (
  echo 서버 실행에 실패했습니다. 위 오류를 확인하십시오.
  pause
)
