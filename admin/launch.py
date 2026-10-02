"""Double-click launcher; manager and preview are bound to loopback only."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
def main():
    os.chdir(ROOT)
    try:
        import streamlit
        if tuple(map(int, streamlit.__version__.split('.')[:2])) < (1, 62): raise ImportError()
    except ImportError:
        print('setup_admin.bat을 먼저 실행해 주세요.'); return 1
    runtime = ROOT / '.tools/site-manager'
    runtime.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    log = (runtime/'manager.log').open('a',encoding='utf-8')
    command = [sys.executable,'-m','streamlit','run',str(ROOT/'admin/dashboard.py'),
               '--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true',
               '--server.enableXsrfProtection=true','--server.enableCORS=true','--browser.gatherUsageStats=false']
    command.append('--client.toolbarMode=minimal')
    process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    url=f'http://127.0.0.1:{port}'
    for _ in range(100):
        if process.poll() is not None:
            print('관리 도구를 시작하지 못했습니다. setup_admin.bat을 실행한 뒤 다시 시도해 주세요.'); return 1
        try:
            with urllib.request.urlopen(url+'/_stcore/health',timeout=1) as response:
                if response.status==200: break
        except OSError: pass
        time.sleep(.2)
    else:
        process.terminate(); print('실행 시간이 초과됐습니다. 다시 실행해 주세요.'); return 1
    (runtime/'manager-url.txt').write_text(url,encoding='utf-8')
    webbrowser.open(url)
    print('관리 화면: '+url)
    print('종료하려면 이 창에서 Ctrl+C를 누르세요. 저장된 내용은 유지됩니다.')
    try: process.wait()
    except KeyboardInterrupt: process.terminate(); process.wait(timeout=10)
    finally: log.close()
    return 0

if __name__=='__main__': raise SystemExit(main())
