"""Isolated loopback preview: fresh modules, read-only catalog, no SMS sends."""
import os
from pathlib import Path
import sys

bundle = Path(sys.argv[1]).resolve()
port = int(sys.argv[2])
sys.path.insert(0, str(bundle))
os.environ.update(VERCEL='1', PYTHON_DOTENV_DISABLED='1', DATA_BACKEND='sqlite',
                  SMS_MODE='mock', ENABLE_LLM='false')
from app import app, limiter
from flask import jsonify, request, send_from_directory

limiter.enabled = False

@app.before_request
def block_delivery():
    if request.path.startswith('/api/sms'):
        return jsonify(error='미리보기에서는 문자를 발송하지 않습니다.'), 403

@app.get('/__manager__/health')
def manager_health():
    return jsonify(bundle=bundle.name)

@app.get('/<path:filename>')
def public_file(filename):
    if filename.startswith('api/'):
        return jsonify(error='없는 주소입니다.'), 404
    return send_from_directory(bundle / 'public', filename)

app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)
