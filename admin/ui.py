from copy import deepcopy
import os
import streamlit as st
from admin.content_store import Store, ContentError, ROOT

@st.cache_resource
def _store(home):
    return Store(home=home)

def store():
    return _store(os.getenv('HEALTH_MANAGER_HOME', str(ROOT / '.tools/site-manager')))

def current():
    record = store().read()
    return record, deepcopy(record['payload'])

def save(payload, record, label):
    try:
        store().save(payload, record['id'], label)
        st.session_state.notice = label + ' — 수정본에 저장했습니다.'
        st.rerun()
    except ContentError as exc:
        st.error(str(exc))

def lines(value):
    return list(dict.fromkeys(s.strip() for s in value.splitlines() if s.strip()))

def task_names(payload):
    return {t['id']: t['name'] + (' · ' + t['department'] if t['department'] else '')
            for t in payload['data']['catalog']['tasks']}

def contact_editor(contacts, key):
    import pandas as pd
    frame = pd.DataFrame([{'문의처':c['label'], '전화번호':c['phone']} for c in contacts], columns=['문의처','전화번호'])
    edited = st.data_editor(frame, hide_index=True, num_rows='dynamic', key=key,
                            column_config={'문의처':st.column_config.TextColumn(required=True),
                                           '전화번호':st.column_config.TextColumn(required=True)})
    return [dict(label=str(row['문의처']).strip(), phone=str(row['전화번호']).strip())
            for row in edited.fillna('').to_dict('records')]

def reference_editor(refs, key):
    import pandas as pd
    edited = st.data_editor(pd.DataFrame([{'출처 이름':r['title'], '공식 페이지 주소':r['url']} for r in refs],
                            columns=['출처 이름','공식 페이지 주소']), hide_index=True, num_rows='dynamic', key=key)
    return [dict(title=str(row['출처 이름']), url=str(row['공식 페이지 주소']))
            for row in edited.fillna('').to_dict('records')]
