from datetime import date
import streamlit as st
from admin.ui import current, save, lines, task_names

st.title('월간 일정')
record, payload = current()
plans = payload['data']['plans']
with st.expander('공개할 월 변경'):
    with st.form('month'):
        month = st.text_input('공개 월', plans['month'], placeholder='2026-11')
        department = st.text_input('부서', plans['department'])
        clear = st.checkbox('다른 달로 변경할 때 빈 일정 목록으로 시작', True)
        change = st.form_submit_button('공개 월 저장')
    if change:
        if month != plans['month'] and clear: plans['items'] = []
        plans['month'] = month; plans['department'] = department
        if len(month.split('-')) == 2:
            year, number = month.split('-')
            if number.isdigit(): plans['title'] = f'{year}년 {int(number)}월 월간 일정·프로그램'
        save(payload, record, '공개 월 변경')
index = {g['id']:g for g in plans['items']}
selected = st.selectbox('수정할 일정', ['new', *index], format_func=lambda k:'＋ 새 일정 등록' if k == 'new' else index[k]['title'])
if selected == 'new':
    prefix = 'MP' + plans['month'].replace('-','') + '-'
    num = max([int(i.rsplit('-',1)[1]) for i in index if i.startswith(prefix)] or [0]) + 1
    item = dict(id=prefix+f'{num:02}', source_items=[], title='', department=plans['department'], team='',
                schedule_text='',period={'start':None,'end':None},schedule_review=False,location='',audience='',content='',notes=[],related_tasks=[],active=True)
else: item = index[selected]
names = task_names(payload)
with st.form('plan-' + record['id'] + selected):
    item['active'] = st.checkbox('홈페이지에 표시', item.get('active', True))
    item['title'] = st.text_input('일정·프로그램명', item['title'])
    item['team'] = st.text_input('담당 팀', item['team'])
    item['schedule_text'] = st.text_input('화면에 표시할 일정', item['schedule_text'], placeholder='2026. 11. 2.(월) 10:00 ~ 12:00')
    for field, label in [('start','시작일'),('end','종료일')]:
        value = item['period'][field]
        chosen = st.date_input(label, date.fromisoformat(value) if value else None, key=field+record['id']+selected)
        item['period'][field] = chosen.isoformat() if chosen else None
    item['schedule_review'] = st.checkbox('일정 확인 필요', item['schedule_review'])
    item['location'] = st.text_input('장소', item['location'])
    item['audience'] = st.text_area('대상', item['audience'])
    item['content'] = st.text_area('내용', item['content'], height=180)
    notes = st.text_area('추가 안내 — 없으면 비워두세요', '\n'.join(item['notes']))
    related = st.multiselect('연결할 업무', list(names), default=[t['task_id'] for t in item['related_tasks']], format_func=names.get)
    submitted = st.form_submit_button('수정본 저장', type='primary')
if submitted:
    item['notes'] = lines(notes)
    item['related_tasks'] = [dict(task_id=i, title=names[i], href='/?task='+i) for i in related]
    if selected == 'new': plans['items'].append(item)
    save(payload, record, item['title'] + ' 일정 저장')
