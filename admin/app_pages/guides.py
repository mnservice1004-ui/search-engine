from datetime import date
import streamlit as st
from admin.ui import current, save, lines, task_names, contact_editor, reference_editor
from admin.content_store import new_guide

st.title('사업 안내·검색어')
record, payload = current()
kinds = {'services':'보건사업·민원 안내','examinations':'검사·건강검진','vaccination':'예방접종'}
kind = st.selectbox('안내 종류', list(kinds), format_func=kinds.get)
rows = payload['data'][kind]['guides']
index = {g['id']:g for g in rows}
selected = st.selectbox('수정할 안내', ['new',*index], format_func=lambda k: '＋ 새 안내 등록' if k == 'new' else index[k]['title'])
guide = new_guide(payload, kind) if selected == 'new' else index[selected]
key = record['id'] + kind + selected
names = task_names(payload)
with st.form('guide-' + key):
    guide['active'] = st.checkbox('홈페이지에 표시', value=guide.get('active', True))
    guide['title'] = st.text_input('안내 제목', guide['title'])
    guide['summary'] = st.text_area('요약', guide['summary'])
    keywords = st.text_area('검색어 — 한 줄에 하나씩', '\n'.join(guide['keywords']),
                             help='예: 산전검사, 혼전검사. 저장 후 미리보기에서 실제 검색 결과를 확인하세요.')
    details = st.text_area('상세 내용 — 항목별로 줄바꿈', '\n'.join(guide['details']), height=220)
    guide['related_task_ids'] = st.multiselect('연결할 업무·위치 안내', list(names), default=guide['related_task_ids'], format_func=names.get)
    if kind == 'vaccination':
        guide['phone'] = st.text_input('공식 문의전화', guide['phone'])
        guide['review_required'] = st.checkbox('추가 확인이 필요한 안내', guide['review_required'])
        guide['checked_on'] = st.date_input('내용 확인일', date.fromisoformat(guide['checked_on'])).isoformat()
    else:
        guide['fee'] = st.text_input('비용', guide['fee'])
        guide['result_time'] = st.text_input('결과·처리 기간', guide['result_time'])
        guide['confirmation'] = st.text_area('확인이 필요한 내용', guide['confirmation'])
        st.write('공식 문의처')
        guide['contacts'] = contact_editor(guide['contacts'], 'contacts-' + key)
    guide['caution'] = st.text_area('유의사항', guide['caution'])
    if kind != 'examinations':
        until = st.text_input('안내 종료일 — 없으면 비워두세요', guide.get('valid_until') or '', placeholder='2026-12-31')
        guide['valid_until'] = until or (None if kind == 'vaccination' else '')
    st.write('공식 출처')
    field = 'sources' if kind == 'vaccination' else 'references'
    guide[field] = reference_editor(guide[field], 'references-' + key)
    submitted = st.form_submit_button('수정본 저장', type='primary')
if submitted:
    guide['keywords'] = lines(keywords); guide['details'] = lines(details)
    if selected == 'new': rows.append(guide)
    if 'related_task_labels' in guide:
        guide['related_task_labels'] = {k:v for k,v in guide['related_task_labels'].items() if k in guide['related_task_ids']}
    save(payload, record, guide['title'] + (' 등록' if selected == 'new' else ' 수정'))
