const state = {
  selectedTask: null,
  mapPoints: {},
  mapPointsReady: false,
  mapPointsError: false,
  suggestionTimer: null,
  searchController: null,
  suggestionController: null
};

const el = (id) => document.getElementById(id);
const queryInput = el('query');
const statusEl = el('status');
const resultsEl = el('results');
const suggestionsEl = el('suggestions');
const detailEl = el('detail');
const markerEl = el('map-marker');
const mapLabelEl = el('map-label');
const floorImageEl = el('floor-image');

async function getJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || '요청을 처리하지 못했습니다.');
  return body;
}

function clearChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function createText(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text || '';
  return node;
}

function resetMap() {
  markerEl.classList.remove('show');
  mapLabelEl.classList.remove('show');
  floorImageEl.removeAttribute('src');
  floorImageEl.alt = '층별 배치도';
  el('floor-label').textContent = '층을 선택하십시오';
  el('route-text').textContent = '검색 결과를 선택하면 위치가 표시됩니다.';
  document.querySelectorAll('.floor-tabs button').forEach((button) => {
    button.classList.remove('active');
    button.setAttribute('aria-pressed', 'false');
  });
}

function resetSearchView(message = '검색 결과가 이곳에 표시됩니다.') {
  state.selectedTask = null;
  clearChildren(resultsEl);
  resultsEl.appendChild(createText('p', 'empty', message));
  detailEl.className = 'empty';
  detailEl.textContent = '검색 결과를 선택하십시오.';
  resetMap();
}

function setActiveFloor(floor, preserveMarker = false) {
  document.querySelectorAll('.floor-tabs button').forEach((button) => {
    button.classList.toggle('active', button.dataset.floor === floor);
    button.setAttribute('aria-pressed', button.dataset.floor === floor ? 'true' : 'false');
  });
  const floorNumber = String(floor || '').replace('층', '');
  floorImageEl.src = floorNumber ? `/images/floor-${floorNumber}.jpg` : '';
  floorImageEl.alt = floor ? `${floor} 배치도` : '층별 배치도';
  el('floor-label').textContent = floor || '층을 선택하십시오';
  if (!preserveMarker) {
    markerEl.classList.remove('show');
    mapLabelEl.classList.remove('show');
    el('route-text').textContent = floor
      ? `${floor} 배치도를 수동으로 보고 있습니다. 검색 결과를 선택하면 위치가 표시됩니다.`
      : '검색 결과를 선택하면 위치가 표시됩니다.';
  }
}

function showMap(task) {
  setActiveFloor(task.floor, true);
  if (!state.mapPointsReady) {
    markerEl.classList.remove('show');
    mapLabelEl.classList.remove('show');
    el('route-text').textContent = state.mapPointsError
      ? '지도 좌표를 불러오지 못했습니다. 새로고침 후 다시 시도하십시오.'
      : '지도 좌표를 불러오는 중입니다.';
    return;
  }
  const points = state.mapPoints[task.floor] || {};
  const point = points[task.place] || Object.entries(points).find(([name]) =>
    name !== 'start' && (String(task.place).includes(name) || name.includes(String(task.place)))
  )?.[1];
  if (!point) {
    markerEl.classList.remove('show');
    mapLabelEl.classList.remove('show');
    el('route-text').textContent = `${task.floor} ${task.place}: 지도 좌표 확인이 필요합니다.`;
    return;
  }
  markerEl.style.left = `${point.x}%`;
  markerEl.style.top = `${point.y}%`;
  mapLabelEl.style.left = `${point.x}%`;
  mapLabelEl.style.top = `${point.y}%`;
  mapLabelEl.textContent = `${task.floor} ${task.place}`;
  markerEl.classList.add('show');
  mapLabelEl.classList.add('show');
  el('route-text').textContent = task.route || `${task.floor} ${task.place}로 안내합니다.`;
}

function addDetailRow(container, label, value, className = '') {
  const row = createText('div', `detail-row ${className}`.trim(), '');
  row.appendChild(createText('strong', '', label));
  row.appendChild(createText('span', '', value || '확인 필요'));
  container.appendChild(row);
}

function showDetail(task) {
  state.selectedTask = task;
  clearChildren(detailEl);
  detailEl.className = 'detail-grid';
  detailEl.appendChild(createText('h3', '', task.name));
  addDetailRow(detailEl, '담당', [task.department, task.team].filter(Boolean).join(' / '));
  addDetailRow(
    detailEl,
    '담당자/직위',
    [task.contact_name, task.contact_role].filter(Boolean).join(' / ') || '[공식 확인 필요]'
  );
  addDetailRow(detailEl, '위치', [task.floor, task.place].filter(Boolean).join(' '));
  if (task.status && task.status !== '정상') {
    addDetailRow(detailEl, '운영 상태', task.status, 'warning-box');
  }
  if (task.location_condition || task.locationCondition) {
    addDetailRow(detailEl, '위치 적용 조건', task.location_condition || task.locationCondition, 'warning-box');
  }
  addDetailRow(detailEl, '확인 질문', task.question);
  addDetailRow(detailEl, '주의사항', task.caution || '특이사항 없음');
  addDetailRow(detailEl, '안내 멘트', task.script, 'script-box');

  const phoneRow = createText('div', 'detail-row', '');
  phoneRow.appendChild(createText('strong', '', '공식 업무전화'));
  if (task.phone) {
    const link = createText('a', 'contact-link', task.phone);
    link.href = `tel:${String(task.phone).replace(/[^0-9+]/g, '')}`;
    phoneRow.appendChild(link);
  } else {
    phoneRow.appendChild(createText('span', '', '[공식 확인 필요]'));
  }
  detailEl.appendChild(phoneRow);
  addDetailRow(detailEl, '연락처 최종 확인일', task.contact_verified_at || '[공식 확인 필요]');
  addDetailRow(detailEl, '자료 출처', task.source || '[공식 확인 필요]');
  if (task.note) addDetailRow(detailEl, '검수 메모', task.note, 'warning-box');

  const smsButton = createText('button', 'contact-button', '이 연락처를 문자로 받기');
  smsButton.type = 'button';
  smsButton.disabled = !task.phone;
  if (!task.phone) smsButton.title = '공식 업무전화가 등록된 뒤 사용할 수 있습니다.';
  smsButton.addEventListener('click', openSmsDialog);
  detailEl.appendChild(smsButton);
  if (!task.phone) {
    detailEl.appendChild(createText('p', 'help', '공식 업무전화 미등록으로 문자 기능이 비활성화되어 있습니다.'));
  }
  showMap(task);
}

function renderResults(items) {
  clearChildren(resultsEl);
  if (!items.length) {
    resetSearchView('일치하는 결과가 없습니다. 핵심어를 바꾸어 다시 검색하십시오.');
    return;
  }
  items.forEach((task, index) => {
    const button = createText('button', 'result-card', '');
    button.type = 'button';
    button.dataset.taskId = task.id;
    button.setAttribute('aria-pressed', 'false');
    button.appendChild(createText('span', 'result-name', `${index + 1}. ${task.name}`));
    button.appendChild(createText('span', 'result-meta', `${task.department || '담당부서 확인 필요'} · ${task.floor || ''} ${task.place || ''}`));
    button.addEventListener('click', () => {
      document.querySelectorAll('.result-card').forEach((card) => {
        card.classList.remove('active');
        card.setAttribute('aria-pressed', 'false');
      });
      button.classList.add('active');
      button.setAttribute('aria-pressed', 'true');
      showDetail(task);
    });
    resultsEl.appendChild(button);
  });
  resultsEl.firstElementChild.classList.add('active');
  resultsEl.firstElementChild.setAttribute('aria-pressed', 'true');
  showDetail(items[0]);
}

async function runSearch(value = queryInput.value) {
  const query = value.trim();
  if (state.searchController) state.searchController.abort();
  if (query.length < 2) {
    resetSearchView();
    statusEl.textContent = '두 글자 이상의 검색어를 입력하십시오.';
    return;
  }
  statusEl.textContent = '검색 중입니다...';
  state.searchController = new AbortController();
  try {
    const data = await getJson('/api/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query}),
      signal: state.searchController.signal
    });
    if (query !== queryInput.value.trim()) return;
    const aiNotice = data.expanded_terms?.length
      ? ' · AI 보조 검색어를 사용했습니다.'
      : '';
    const shown = data.displayed_count < data.total_count
      ? `총 ${data.total_count}건 중 상위 ${data.displayed_count}건`
      : `${data.total_count}건`;
    statusEl.textContent = `“${query}” 관련 결과 ${shown}${aiNotice}`;
    renderResults(data.items);
  } catch (error) {
    if (error.name === 'AbortError') return;
    resetSearchView('검색 중 오류가 발생했습니다. 잠시 후 다시 시도하십시오.');
    statusEl.textContent = error.message;
  }
}

async function loadSuggestions() {
  const query = queryInput.value.trim();
  clearChildren(suggestionsEl);
  if (state.suggestionController) state.suggestionController.abort();
  if (!query) return;
  state.suggestionController = new AbortController();
  try {
    const data = await getJson('/api/suggestions', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query}),
      signal: state.suggestionController.signal
    });
    if (query !== queryInput.value.trim()) return;
    data.items.forEach((text) => {
      const button = createText('button', '', text);
      button.type = 'button';
      button.addEventListener('click', () => {
        queryInput.value = text;
        clearChildren(suggestionsEl);
        runSearch(text);
      });
      suggestionsEl.appendChild(button);
    });
  } catch (error) {
    if (error.name === 'AbortError') return;
    clearChildren(suggestionsEl);
  }
}

function openSmsDialog() {
  el('sms-task-name').textContent = state.selectedTask?.name || '';
  el('sms-status').textContent = '';
  el('recipient').value = '';
  el('consent').checked = false;
  el('sms-dialog').showModal();
}

async function submitSms(event) {
  event.preventDefault();
  const sendButton = el('send-sms');
  sendButton.disabled = true;
  el('sms-status').textContent = '전송 중입니다...';
  try {
    const data = await getJson('/api/sms', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        task_id: state.selectedTask.id,
        recipient: el('recipient').value,
        consent: el('consent').checked
      })
    });
    el('sms-status').textContent = data.status === 'mocked'
      ? '모의 전송에 성공했습니다. SMS_MODE=live에서 실제 전송됩니다.'
      : '문자 발송 요청이 접수되었습니다.';
  } catch (error) {
    el('sms-status').textContent = error.message;
  } finally {
    sendButton.disabled = false;
  }
}

el('search-button').addEventListener('click', () => runSearch());
el('clear-button').addEventListener('click', () => {
  if (state.searchController) state.searchController.abort();
  if (state.suggestionController) state.suggestionController.abort();
  queryInput.value = '';
  clearChildren(suggestionsEl);
  resetSearchView();
  statusEl.textContent = '검색어를 입력하십시오.';
  queryInput.focus();
});
queryInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') runSearch(); });
queryInput.addEventListener('input', () => {
  if (state.suggestionController) state.suggestionController.abort();
  clearTimeout(state.suggestionTimer);
  state.suggestionTimer = setTimeout(loadSuggestions, 300);
});
document.querySelectorAll('.floor-tabs button').forEach((button) =>
  button.addEventListener('click', () => setActiveFloor(button.dataset.floor, false))
);
el('sms-form').addEventListener('submit', submitSms);
el('cancel-sms').addEventListener('click', () => el('sms-dialog').close());

getJson('/api/map-points').then((data) => {
  state.mapPoints = data;
  state.mapPointsReady = true;
  if (state.selectedTask) showMap(state.selectedTask);
}).catch(() => {
  state.mapPointsError = true;
  if (state.selectedTask) showMap(state.selectedTask);
});
queryInput.focus();
