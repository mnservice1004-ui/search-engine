import streamlit as st
from admin.ui import current, store, save
from admin.content_store import ContentError

st.title('홈페이지 사진')
record, payload = current()
photos = payload['photos']
selected = st.selectbox('수정할 사진', range(4), format_func=lambda i:f'{i+1}번째 · {photos[i]["caption"]}')
photo = photos[selected]
st.image(str(store().home / 'assets' / photo['asset']), width=520)
with st.form('photo-' + record['id'] + str(selected)):
    uploaded = st.file_uploader('새 사진 — 변경할 때만 선택', type=['jpg','jpeg','png','webp'])
    photo['caption'] = st.text_input('사진 위에 표시할 문구', photo['caption'])
    photo['alt'] = st.text_input('사진 설명', photo['alt'])
    position = st.selectbox('표시 순서', range(4), index=selected, format_func=lambda i:f'{i+1}번째')
    submitted = st.form_submit_button('수정본 저장', type='primary')
if submitted:
    try:
        if uploaded: photo['asset'] = store().add_photo(uploaded.getvalue())
        photos.insert(position, photos.pop(selected))
        save(payload, record, '홈페이지 사진 수정')
    except ContentError as exc: st.error(str(exc))
