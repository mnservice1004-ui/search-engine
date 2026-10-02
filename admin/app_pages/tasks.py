from datetime import date
import pandas as pd
import streamlit as st
from admin.ui import current, save, lines, task_names
from admin.content_store import replace_phone, ContentError

st.title('업무·연락처')
record, payload = current()
names = task_names(payload)
selected = st.selectbox('수정할 업무', list(names), format_func=names.get)
task = next(t for t in payload['data']['catalog']['tasks'] if t['id'] == selected)
guidance = next((g for g in payload['data']['tasks']['tasks'] if g['task_id'] == selected), None)
key = record['id'] + selected
with st.form('task-' + key):
    task['name'] = st.text_input('업무명', task['name'])
    task['department'] = st.text_input('부서', task['department'])
    task['team'] = st.text_input('담당 팀', task['team'] or '')
    aliases = [a for a in payload['data']['catalog']['aliases'] if a['task_id'] == selected]
    terms = st.text_area('검색어 — 한 줄에 하나씩', '\n'.join(a['text'] for a in aliases))
    if guidance:
        st.subheader('민원인에게 보여줄 안내')
        old_title = guidance['public_title']
        labels = {'public_title':'안내 제목','public_summary':'요약','eligibility':'대상',
                  'documents':'준비물·서류','fee':'비용','operating_hours':'운영시간',
                  'visit_steps':'이용 방법','public_caution':'유의사항','primary_action':'문의·신청 방법'}
        for field, label in labels.items():
            value = st.text_area(label, guidance[field] or '', height=80)
            guidance[field] = value or (None if field in {'documents','fee','operating_hours'} else '')
        guidance['verified_date'] = st.date_input('내용 확인일', date.fromisoformat(guidance['verified_date'])).isoformat()
        guidance['organization'] = dict(department=task['department'], team=task['team'] or None)
        guidance['public_search_terms'] = list(dict.fromkeys(
            [guidance['public_title']] + [t for t in guidance['public_search_terms'] if t != old_title]))[:6]
    else:
        task['representative'] = st.text_input('대표 질문', task['representative'])
        task['script'] = st.text_area('안내 내용', task['script'])
        task['caution'] = st.text_area('유의사항', task['caution'])
    st.subheader('공식 문의전화')
    st.caption('대표전화는 한 개만 선택하세요. 새 행을 추가해 여러 문의처를 등록할 수 있습니다.')
    original = [c for c in payload['data']['catalog']['contacts'] if c['task_id'] == selected]
    rows = [{'문의처':c['label'],'전화번호':c['phone'],'담당 업무':c['contact_role'] or '',
             '이용 조건':c['condition_text'] or '', '확인일':c['verified_at'],'대표전화':bool(c['is_primary'])} for c in original]
    edited = st.data_editor(pd.DataFrame(rows, columns=['문의처','전화번호','담당 업무','이용 조건','확인일','대표전화']),
                            hide_index=True, num_rows='dynamic', key='contacts-' + key,
                            column_config={'대표전화':st.column_config.CheckboxColumn(default=False)})
    submitted = st.form_submit_button('수정본 저장', type='primary')
if submitted:
    old_aliases = {a['text']:a for a in aliases}
    payload['data']['catalog']['aliases'] = [a for a in payload['data']['catalog']['aliases'] if a['task_id'] != selected]
    payload['data']['catalog']['aliases'] += [old_aliases.get(t, dict(task_id=selected,text=t,weight=10,type='관리자 등록')) for t in lines(terms)]
    contacts = [dict(task_id=selected,phone=str(r['전화번호']),display_phone=str(r['전화번호']),
                     label=str(r['문의처']),contact_role=str(r['담당 업무']) or None, condition_text=str(r['이용 조건']) or None,
                     verified_at=str(r['확인일']),is_primary=int(bool(r['대표전화']))) for r in edited.fillna('').to_dict('records')]
    payload['data']['catalog']['contacts'] = [c for c in payload['data']['catalog']['contacts'] if c['task_id'] != selected] + contacts
    save(payload, record, task['name'] + ' 수정')
with st.expander('같은 전화번호를 모든 안내에서 변경'):
    st.write('업무·검사·예방접종·사업 안내·위탁의료기관에 반복된 번호를 함께 변경합니다.')
    with st.form('replace-phone'):
        old = st.text_input('기존 전화번호'); new = st.text_input('새 전화번호')
        replace = st.form_submit_button('해당 번호를 찾아 수정본에 저장')
    if replace:
        fresh_record, fresh_payload = current()
        try:
            count = replace_phone(fresh_payload, old, new)
            if count: save(fresh_payload, fresh_record, f'전화번호 변경 ({count}개 필드)')
            else: st.info('기존 번호와 일치하는 연락처가 없습니다.')
        except ContentError as exc: st.error(str(exc))
