import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import get_all_tasks, get_event_rows  # noqa: E402


st.set_page_config(page_title="보건민원 검색 관리자", layout="wide")
st.title("보건민원 검색 데이터·이용현황")
st.caption("외부 민원인용 화면이 아니라 내부 검수·분석용 화면입니다.")

tasks = pd.DataFrame(get_all_tasks())
events = pd.DataFrame(get_event_rows())

left, middle, right = st.columns(3)
left.metric("활성 업무", len(tasks))
middle.metric("공식 연락처 미등록", int(tasks["phone"].fillna("").eq("").sum()) if not tasks.empty else 0)
right.metric("주의사항 보유", int(tasks["caution"].fillna("").ne("").sum()) if not tasks.empty else 0)

st.subheader("업무 데이터 검수")
if tasks.empty:
    st.warning("업무 데이터가 없습니다.")
else:
    visible_columns = [
        "id", "name", "department", "team", "floor", "place", "status",
        "contact_name", "contact_role", "phone", "contact_verified_at", "source"
    ]
    st.dataframe(tasks[visible_columns], use_container_width=True, hide_index=True)

st.subheader("개인정보를 남기지 않는 집계")
if events.empty:
    st.info("아직 집계 이벤트가 없습니다.")
else:
    counts = events.groupby("event_type").size().rename("count").reset_index()
    st.bar_chart(counts, x="event_type", y="count")
    st.dataframe(events[["event_type", "task_id", "result_count", "created_at"]], use_container_width=True, hide_index=True)

st.warning("검색 원문, IP, 민원인의 휴대전화번호는 분석 화면과 로그에 저장하지 마십시오.")
