@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher를 찾을 수 없습니다. Python 3.12를 먼저 설치하십시오.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
if errorlevel 1 (
  echo Python 가상환경 생성에 실패했습니다.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 (
  echo pip 업그레이드에 실패했습니다.
  pause
  exit /b 1
)
python -m pip install -r requirements-dev.txt
if errorlevel 1 (
  echo 패키지 설치에 실패했습니다. 인터넷 연결과 오류 문구를 확인하십시오.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env
if not exist data\tasks.json (
  echo data\tasks.json이 없습니다.
  echo 매뉴얼의 데이터 추출 단계를 먼저 실행하십시오.
  pause
  exit /b 1
)
python scripts\init_db.py
if errorlevel 1 (
  echo SQLite 초기화에 실패했습니다.
  pause
  exit /b 1
)
echo 설치와 SQLite 초기화가 완료되었습니다.
pause
