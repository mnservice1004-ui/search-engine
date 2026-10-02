"""Local operator interface for the public health-center website."""
import sys
from pathlib import Path
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from admin.ui import store

st.set_page_config(page_title='동탄구보건소 홈페이지 관리', page_icon=':material/edit_note:', layout='wide')
if st.get_option('server.address') not in ('127.0.0.1', 'localhost', '::1'):
    st.error('관리자 실행.bat 또는 run_admin.bat으로 실행해 주세요. 이 도구는 현재 PC에서만 사용합니다.')
    st.stop()
try:
    store().initialize()
except Exception as exc:
    st.error(f'관리 자료를 열 수 없습니다: {exc}')
    st.stop()
if st.session_state.get('notice'):
    st.success(st.session_state.pop('notice'))
navigation = st.navigation([
    st.Page('app_pages/start.py', title='시작·사용 방법', icon=':material/home:', default=True),
    st.Page('app_pages/tasks.py', title='업무·연락처', icon=':material/contact_phone:'),
    st.Page('app_pages/guides.py', title='사업 안내·검색어', icon=':material/manage_search:'),
    st.Page('app_pages/plans.py', title='월간 일정', icon=':material/calendar_month:'),
    st.Page('app_pages/photos.py', title='홈페이지 사진', icon=':material/photo_library:'),
    st.Page('app_pages/publish.py', title='미리보기·공개 반영', icon=':material/publish:'),
    st.Page('app_pages/history.py', title='이력·백업·복원', icon=':material/history:'),
])
with st.sidebar:
    st.caption('이 PC에서만 열리는 관리 화면')
    st.link_button('공개 홈페이지 열기', 'https://search-engine-delta-seven.vercel.app/')
    st.caption('저장은 수정본에 적용됩니다. 홈페이지에는 공개 반영 후 표시됩니다.')
navigation.run()
