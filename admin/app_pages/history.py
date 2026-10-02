import streamlit as st
from admin.ui import current, store
from admin.content_store import ContentError

st.title('이력·백업·복원')
record, payload = current()
history = store().history()
selected = st.selectbox('이전 수정 내용', [r['id'] for r in history],
                        format_func=lambda i:next(r['at']+' · '+r['label'] for r in history if r['id']==i))
if st.button('선택한 내용을 수정본으로 복원', disabled=selected == record['id']):
    try:
        store().restore(selected, record['id'])
        st.session_state.notice = '수정본을 복원했습니다. 미리보기 후 공개하면 홈페이지에도 적용됩니다.'
        st.rerun()
    except ContentError as exc: st.error(str(exc))
st.divider()
st.subheader('백업 내려받기')
st.write('현재 수정본의 안내·연락처·일정·사진을 하나의 파일로 보관합니다. 배포 계정과 비밀번호는 포함되지 않습니다.')
if st.button('백업 파일 준비'):
    st.session_state.backup_data = store().backup()
    st.session_state.backup_revision = record['id']
if st.session_state.get('backup_data') and st.session_state.get('backup_revision') == record['id']:
    st.download_button('백업 파일 내려받기', st.session_state.backup_data,
                       file_name='동탄구보건소_홈페이지_백업.zip', mime='application/zip')
st.subheader('백업 파일 불러오기')
uploaded = st.file_uploader('관리 도구에서 내려받은 백업 파일', type=['zip'])
if st.button('백업 내용을 수정본으로 불러오기', disabled=uploaded is None):
    try:
        store().import_backup(uploaded.getvalue(), record['id'])
        st.session_state.notice = '백업을 수정본으로 불러왔습니다. 미리보기에서 내용을 확인해 주세요.'
        st.rerun()
    except Exception as exc:
        st.error(str(exc) if isinstance(exc, ContentError) else '이 관리 도구에서 만든 올바른 백업 파일인지 확인해 주세요.')
