import os
import subprocess
import shutil
from urllib.parse import urlencode
import streamlit as st
from admin.ui import current, store
from admin.content_store import ContentError, read_json, ROOT
from admin.publishing import preview, search_preview, start_publish, CONFIG

st.title('미리보기·공개 반영')
record, payload = current()
st.write('저장한 수정본으로 홈페이지를 미리 확인한 다음 공개하세요.')
if st.button('최신 수정본 미리보기 만들기', icon=':material/preview:', type='primary'):
    try:
        with st.spinner('미리보기 준비와 업무·검색 확인 중입니다…'):
            preview(store(), record['id'])
        st.success('미리보기가 준비됐습니다.')
    except Exception as exc:
        st.error(str(exc) if isinstance(exc, ContentError) else '미리보기를 만들지 못했습니다. 관리자 도구를 다시 실행해 주세요.')
p = read_json(store().home / 'preview.json') if (store().home / 'preview.json').exists() else None
ready = bool(p and p['revision'] == record['id'])
if ready:
    st.link_button('미리보기 홈페이지 열기', p['url'])
    with st.form('search-check'):
        query = st.text_input('검색 결과 확인', placeholder='예: 산전검사')
        search = st.form_submit_button('검색')
    if search and len(query.strip()) >= 2:
        try:
            result = search_preview(p['url'], query)
            guides = [g for k in ['examinations','vaccination','services'] for g in result[k]['guides']]
            linked = {i for g in guides if not g.get('expired') for i in g['related_task_ids']}
            tasks = [t for t in result['items'] if t['id'] not in linked]
            st.write(f'안내 {len(guides)}건 · 추가 업무 {len(tasks)}건')
            for item in guides + tasks:
                with st.container(border=True):
                    st.subheader(item.get('title') or item.get('public_title') or item.get('name'))
                    st.write(item.get('summary') or item.get('public_summary') or '')
            st.link_button('홈페이지 모양으로 검색 결과 보기', p['url'] + '/?' + urlencode({'q':query}))
        except Exception: st.error('미리보기가 종료됐습니다. 미리보기를 다시 만들어 주세요.')
else:
    st.info('공개하기 전에 최신 수정본의 미리보기를 만들어 주세요.')
st.divider()
ack = st.checkbox('미리보기의 내용과 검색 결과를 확인했으며 홈페이지에 공개합니다.', disabled=not ready, key='confirm-'+record['id'])
if st.button('홈페이지에 공개 반영', disabled=not (ready and ack), icon=':material/publish:'):
    try:
        start_publish(store(), record['id'], p['id'])
        st.success('공개 반영을 시작했습니다. 아래 상태가 완료로 바뀔 때까지 관리 화면을 열어두세요.')
    except ContentError as exc: st.error(str(exc))

@st.fragment(run_every='3s')
def publication_status():
    path = store().home / 'job.json'
    if not path.exists(): return
    job = read_json(path)
    if job['status'] == 'success':
        st.success(job['stage']); st.link_button('공개 홈페이지 확인', CONFIG['production_url'])
    elif job['status'] == 'failed': st.error(job['stage'])
    else: st.info(job['stage'])
publication_status()
with st.expander('배포 계정 로그인'):
    st.write('로그인이 만료되거나 PC를 바꾼 경우 실행하세요. 열린 창에서 안내에 따라 Vercel에 로그인합니다.')
    if st.button('Vercel 로그인 연결'):
        node = shutil.which('node')
        entry = ROOT / '.tools/vercel-cli/node_modules/vercel/dist/index.js'
        if node and entry.exists():
            subprocess.Popen([node,str(entry),'login','--global-config',str(ROOT/'.tools/vercel-cli/auth')],
                             creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
            st.info('로그인 창의 안내를 완료한 뒤 공개 반영을 다시 시도하세요.')
        else: st.error('setup_admin.bat을 먼저 실행해 주세요.')
