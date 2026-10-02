import streamlit as st
from admin.ui import current, store
from admin.content_store import read_json

st.title('홈페이지 관리')
st.write('업무 안내와 일정을 수정하고, 확인한 내용을 홈페이지에 공개하세요.')
record, payload = current()
published = read_json(store().home / 'published.json')
with st.container(horizontal=True):
    st.metric('업무', len(payload['data']['catalog']['tasks']))
    st.metric('사업·검사·접종 안내', sum(len(payload['data'][k]['guides']) for k in ['services','examinations','vaccination']))
    st.metric('월간 일정', len(payload['data']['plans']['items']))
if published['revision'] == record['id']:
    st.info('공개본 이후 저장된 수정 내용이 없습니다.')
else:
    st.warning('아직 공개하지 않은 수정 내용이 있습니다. 미리보기에서 확인해 주세요.')
st.subheader('수정부터 공개까지')
st.markdown('''1. 왼쪽 메뉴에서 수정할 항목을 선택합니다.
2. 내용을 고치고 **수정본 저장**을 누릅니다.
3. **미리보기·공개 반영**에서 미리보기를 만들고 검색 결과를 확인합니다.
4. 확인란을 선택한 뒤 **홈페이지에 공개 반영**을 누릅니다.
5. **공개 반영 완료**가 표시되면 공개 홈페이지에서 확인합니다.''')
st.subheader('자주 하는 작업')
st.markdown('''- **전화번호 변경:** 업무·연락처에서 업무를 선택하거나, 같은 번호를 한꺼번에 바꾸는 기능을 사용하세요.
- **검색 결과 연결:** 사업 안내·검색어에서 안내를 선택하고 검색어를 한 줄에 하나씩 추가하세요. 예: 산전검사, 혼전검사.
- **새로운 사업 등록:** 사업 안내·검색어에서 새 안내를 만들고 관련 업무·문의처를 연결하세요.
- **다음 달 일정:** 월간 일정에서 공개할 월을 바꾸고 새 일정을 등록하세요. 이전 일정은 이력에서 복원할 수 있습니다.
- **잘못 수정한 경우:** 이력·백업·복원에서 이전 내용을 수정본으로 복원하고 미리보기 후 다시 공개하세요.
- **다른 곳에 백업:** 이력·백업·복원에서 백업 파일을 내려받아 별도 저장장치에도 보관하세요.''')
st.caption('담당자 개인 이름은 입력하지 않고 부서·담당 업무·공식 전화번호로 안내하세요. 금액·대상·운영시간은 원문을 확인한 뒤 수정하세요.')
st.subheader('문제가 생겼을 때')
st.markdown('''- **저장은 됐는데 홈페이지가 그대로일 때:** 공개 반영 완료 여부를 확인하고 홈페이지를 새로고침하세요.
- **미리보기가 열리지 않을 때:** 이 관리 화면에서 미리보기를 다시 만드세요.
- **배포 로그인 오류:** 미리보기·공개 반영의 로그인 연결을 실행한 뒤 다시 시도하세요.
- **관리 화면이 종료됐을 때:** 관리자 실행.bat을 다시 여세요. 저장한 내용은 유지됩니다.
- **관리 PC를 바꿀 때:** 프로젝트 폴더와 내려받은 백업을 함께 옮기고 setup_admin.bat을 실행하세요. 배포 계정은 새 PC에서 다시 로그인해야 합니다.''')
