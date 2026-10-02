@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Python 3.12를 설치한 뒤 다시 실행해 주세요.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install -r requirements-admin.txt
if errorlevel 1 (
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo 공개 반영에는 Node.js가 필요합니다. Node.js LTS를 설치한 뒤 다시 실행해 주세요.
  pause
  exit /b 1
)
if not exist .tools\vercel-cli\node_modules\vercel\dist\index.js (
  call npm install --prefix .tools\vercel-cli vercel@59.11.7
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
echo 설치가 끝났습니다. 관리자 실행.bat을 여세요.
pause
