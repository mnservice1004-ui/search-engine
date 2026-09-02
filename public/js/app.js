const state = {
  selectedTask: null,
  mapPoints: {},
  mapPointsReady: false,
  mapPointsError: false,
  mapSelectionToken: 0,
  suggestionTimer: null,
  searchController: null,
  suggestionController: null,
  detailTrigger: null
};

const el = (id) => document.getElementById(id);
const queryInput = el('query');
const statusEl = el('status');
const resultsEl = el('results');
const resultsHeadingEl = el('results-heading');
const suggestionsEl = el('suggestions');
const detailEl = el('detail');
const markerEl = el('map-marker');
const mapLabelEl = el('map-label');
const routeEl = el('map-route');
const routeLineEl = el('map-route-line');
const floorImageEl = el('floor-image');
const detailDialogEl = el('detail-dialog');
const mapPanelEl = document.querySelector('.map-panel');
const mapSectionHeadEl = mapPanelEl.querySelector('.section-head');
const floorTabsEl = mapPanelEl.querySelector('.floor-tabs');
const mapStageEl = mapPanelEl.querySelector('.map-stage');

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

function hideMapLocation() {
  markerEl.classList.remove('show');
  markerEl.classList.remove('arrived');
  mapLabelEl.classList.remove('show');
  routeEl.classList.remove('show');
}

function setMapControlsHidden(hidden) {
  [mapSectionHeadEl, floorTabsEl, mapStageEl].forEach((element) => {
    element.hidden = hidden;
  });
}

function isValidMapPoint(point) {
  return Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.y))
    && Number(point.x) >= 0 && Number(point.x) <= 100
    && Number(point.y) >= 0 && Number(point.y) <= 100;
}

function createMapRoutePath(startPoint, point) {
  const startX = Number(startPoint.x);
  const startY = Number(startPoint.y);
  const endX = Number(point.x);
  const endY = Number(point.y);
  const distance = Math.hypot(endX - startX, endY - startY);
  const bend = Math.min(12, Math.max(5, distance * 0.28));
  const normalX = distance ? -(endY - startY) / distance : 0;
  const normalY = distance ? (endX - startX) / distance : 0;
  const controlX = Math.max(4, Math.min(96, (startX + endX) / 2 + normalX * bend));
  const controlY = Math.max(4, Math.min(96, (startY + endY) / 2 + normalY * bend));

  return `M ${startX} ${startY} Q ${controlX.toFixed(2)} ${controlY.toFixed(2)} ${endX} ${endY}`;
}

function showMapRoute(startPoint, point, selectionToken) {
  routeEl.classList.remove('show');
  void routeEl.offsetWidth;
  if (selectionToken !== state.mapSelectionToken) return;
  routeLineEl.setAttribute('d', createMapRoutePath(startPoint, point));
  routeEl.classList.add('show');
}

function resetMap() {
  state.mapSelectionToken += 1;
  setMapControlsHidden(false);
  hideMapLocation();
  floorImageEl.removeAttribute('src');
  floorImageEl.alt = '층별 배치도';
  el('floor-label').textContent = '층을 선택하십시오';
  el('route-text').textContent = '검색 결과를 선택하면 위치가 표시됩니다.';
  document.querySelectorAll('.floor-tabs button').forEach((button) => {
    button.classList.remove('active');
    button.setAttribute('aria-pressed', 'false');
  });
}

function resetSearchView(message = '검색 결과가 이곳에 표시됩니다.', preserveHeading = false) {
  state.selectedTask = null;
  if (!preserveHeading) resultsHeadingEl.textContent = '민원 검색 결과';
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
  const floorImagePath = floorNumber ? `/images/floor-${floorNumber}.jpg` : '';
  if (floorImagePath) {
    if (floorImageEl.getAttribute('src') !== floorImagePath) floorImageEl.src = floorImagePath;
  } else {
    floorImageEl.removeAttribute('src');
  }
  floorImageEl.alt = floor ? `${floor} 배치도` : '층별 배치도';
  el('floor-label').textContent = floor || '층을 선택하십시오';
  if (!preserveMarker) {
    hideMapLocation();
    el('route-text').textContent = floor
      ? `${floor} 배치도를 수동으로 보고 있습니다. 검색 결과를 선택하면 위치가 표시됩니다.`
      : '검색 결과를 선택하면 위치가 표시됩니다.';
  }
}

function startRunnerJourney(startPoint, point, task, selectionToken) {
  const finishJourney = () => {
    if (selectionToken !== state.mapSelectionToken) return;
    mapLabelEl.classList.add('show');
    markerEl.classList.add('arrived');
  };
  const setMarkerPosition = (position) => {
    markerEl.style.left = `${position.x}%`;
    markerEl.style.top = `${position.y}%`;
  };

  mapLabelEl.style.left = `${point.x}%`;
  mapLabelEl.style.top = `${point.y}%`;
  mapLabelEl.textContent = `${task.floor} ${task.place}`;
  mapLabelEl.classList.remove('show');
  el('route-text').textContent = task.route || `${task.floor} ${task.place}로 안내합니다.`;

  if (!isValidMapPoint(startPoint)) {
    routeEl.classList.remove('show');
    setMarkerPosition(point);
    markerEl.classList.add('show');
    finishJourney();
    return;
  }

  const samePosition = Number(startPoint.x) === Number(point.x) && Number(startPoint.y) === Number(point.y);
  if (samePosition) routeEl.classList.remove('show');
  else showMapRoute(startPoint, point, selectionToken);
  markerEl.classList.remove('arrived');
  markerEl.classList.add('is-resetting');
  setMarkerPosition(startPoint);
  markerEl.classList.add('show');
  void markerEl.offsetWidth;
  markerEl.classList.remove('is-resetting');

  const reducedMotion = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion || samePosition) {
    setMarkerPosition(point);
    finishJourney();
    return;
  }

  let journeyFinished = false;
  let fallbackTimer;
  const completeJourney = () => {
    if (journeyFinished) return;
    journeyFinished = true;
    if (fallbackTimer) globalThis.clearTimeout(fallbackTimer);
    markerEl.removeEventListener('transitionend', onTransitionEnd);
    finishJourney();
  };
  const onTransitionEnd = (event) => {
    if (event.target === markerEl && event.propertyName === 'top') completeJourney();
  };
  markerEl.addEventListener('transitionend', onTransitionEnd);
  fallbackTimer = globalThis.setTimeout(completeJourney, 320);
  const nextFrame = globalThis.requestAnimationFrame || ((callback) => globalThis.setTimeout(callback, 0));
  nextFrame(() => {
    if (selectionToken !== state.mapSelectionToken) return;
    setMarkerPosition(point);
  });
}

function showMap(task) {
  const selectionToken = ++state.mapSelectionToken;
  if (task?.show_map === false) {
    setMapControlsHidden(true);
    hideMapLocation();
    routeLineEl.removeAttribute('d');
    markerEl.style.left = '';
    markerEl.style.top = '';
    mapLabelEl.style.left = '';
    mapLabelEl.style.top = '';
    mapLabelEl.textContent = '';
    setActiveFloor('', true);
    floorImageEl.alt = '';
    el('floor-label').textContent = '방문 장소 확인';
    el('route-text').textContent = task.route || '방문 장소는 전화로 확인해 주세요.';
    return;
  }
  setMapControlsHidden(false);
  if (!task?.floor || !task?.place) {
    hideMapLocation();
    setActiveFloor(task?.floor || '', true);
    el('route-text').textContent = '선택한 업무의 위치 정보가 없습니다.';
    return;
  }

  hideMapLocation();
  setActiveFloor(task.floor, true);
  if (!state.mapPointsReady) {
    el('route-text').textContent = state.mapPointsError
      ? '지도 좌표를 불러오지 못했습니다. 새로고침 후 다시 시도하십시오.'
      : '지도 좌표를 불러오는 중입니다.';
    return;
  }
  const points = state.mapPoints[task.floor] || {};
  const point = points[task.place] || Object.entries(points).find(([name]) =>
    name !== 'start' && name !== '정문'
      && (String(task.place).includes(name) || name.includes(String(task.place)))
  )?.[1];
  if (!isValidMapPoint(point)) {
    hideMapLocation();
    el('route-text').textContent = `${task.floor} ${task.place}: 지도 좌표 확인이 필요합니다.`;
    return;
  }
  const startPoint = isValidMapPoint(points.정문)
    ? points.정문
    : isValidMapPoint(points.start) ? points.start : null;

  const revealPoint = () => {
    if (selectionToken !== state.mapSelectionToken) return;
    startRunnerJourney(startPoint, point, task, selectionToken);
  };

  if (floorImageEl.complete && floorImageEl.naturalWidth > 0) {
    revealPoint();
    return;
  }

  floorImageEl.addEventListener('load', revealPoint, {once: true});
  floorImageEl.addEventListener('error', () => {
    if (selectionToken !== state.mapSelectionToken) return;
    hideMapLocation();
    el('route-text').textContent = `${task.floor} 배치도를 불러오지 못했습니다.`;
  }, {once: true});
}

function addDetailRow(container, label, value, className = '') {
  const row = createText('div', `detail-row ${className}`.trim(), '');
  row.appendChild(createText('strong', '', label));
  row.appendChild(createText('span', '', value || '확인 필요'));
  container.appendChild(row);
}

function joinPublicText(values) {
  return [...new Set(values.filter((value) => typeof value === 'string' && value.trim()))].join(' ');
}

function appendPublicContacts(container, contacts) {
  contacts.forEach((contact, index) => {
    if (index > 0) container.appendChild(document.createElement('br'));
    const displayPhone = contact.display_phone || contact.phone || '';
    const telDigits = String(contact.phone || displayPhone).replace(/\D/g, '');
    if (telDigits) {
      const link = createText('a', 'contact-link', displayPhone);
      link.href = `tel:${telDigits}`;
      container.appendChild(link);
    } else {
      container.appendChild(createText('span', '', displayPhone));
    }
    if (contact.is_primary) container.appendChild(createText('span', '', ' · 대표'));
    if (contact.purpose) container.appendChild(createText('span', '', ` · ${contact.purpose}`));
    if (contact.condition) {
      container.appendChild(createText('span', '', ` · 조건: ${contact.condition}`));
    }
  });
}

function showDetail(task) {
  state.selectedTask = task;
  clearChildren(detailEl);
  detailEl.className = 'detail-grid';
  detailEl.appendChild(createText('h3', '', task.public_title || task.name));
  addDetailRow(detailEl, '문의하는 곳', [task.department, task.team].filter(Boolean).join(' / '));
  addDetailRow(
    detailEl,
    '문의 안내',
    task.public_summary || '전화로 문의해 주세요.'
  );
  const publicLocation = task.show_map === false
    ? task.route
    : [task.floor, task.room || task.place].filter(Boolean).join(' ');
  addDetailRow(detailEl, '어디로 가나요?', publicLocation || '방문 장소는 전화로 확인해 주세요.');
  addDetailRow(detailEl, '이런 경우 이용하세요', task.eligibility || task.question || '전화로 확인해 주세요.');
  addDetailRow(
    detailEl,
    '방문 전 확인사항',
    joinPublicText([task.public_caution, task.caution, task.documents, task.fee, task.operating_hours])
      || '방문 전에 전화로 확인해 주세요.'
  );
  addDetailRow(
    detailEl,
    '이렇게 이용하세요',
    task.primary_action || task.visit_steps
      ? joinPublicText([task.primary_action, task.visit_steps])
      : task.script,
    'script-box'
  );

  const phoneRow = createText('div', 'detail-row', '');
  phoneRow.appendChild(createText('strong', '', '공식 업무전화'));
  const contacts = Array.isArray(task.contacts) ? task.contacts : [];
  const verifiedContact = task.primary_contact || contacts.find((contact) => contact.is_primary);
  if (contacts.length) {
    const contactValue = createText('span', '', '');
    appendPublicContacts(contactValue, contacts);
    phoneRow.appendChild(contactValue);
  } else {
    phoneRow.appendChild(createText('span', '', '전화로 확인해 주세요.'));
  }
  detailEl.appendChild(phoneRow);
  addDetailRow(detailEl, '최근 공식 확인일', task.verified_date || verifiedContact?.verified_date || '전화로 확인해 주세요.');

  const smsButton = createText('button', 'contact-button', '이 연락처를 문자로 받기');
  smsButton.type = 'button';
  smsButton.disabled = !task.primary_contact?.phone;
  if (!task.primary_contact?.phone) {
    smsButton.title = '대표 공식 업무전화가 등록된 뒤 사용할 수 있습니다.';
  }
  smsButton.addEventListener('click', openSmsDialog);
  detailEl.appendChild(smsButton);
  if (!task.primary_contact?.phone) {
    detailEl.appendChild(createText('p', 'help', '대표 공식 업무전화 미등록으로 문자 기능이 비활성화되어 있습니다.'));
  }
  showMap(task);
}

function renderResults(items) {
  clearChildren(resultsEl);
  if (!items.length) {
    resetSearchView('일치하는 결과가 없습니다. 핵심어를 바꾸어 다시 검색하십시오.', true);
    return;
  }
  items.forEach((task, index) => {
    const button = createText('button', 'result-card', '');
    button.type = 'button';
    button.dataset.taskId = task.id;
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-controls', 'detail-dialog');

    button.appendChild(createText('span', 'result-index', String(index + 1).padStart(2, '0')));

    const main = createText('span', 'result-main', '');
    main.appendChild(createText(
      'span',
      'result-department',
      [task.department || '문의 부서 확인 필요', task.team].filter(Boolean).join(' · ')
    ));
    main.appendChild(createText('span', 'result-name', task.public_title || task.name));

    const facts = createText('span', 'result-facts', '');
    const addFact = (className, value) => {
      if (value) facts.appendChild(createText('span', `result-fact ${className}`, value));
    };
    if (task.show_map !== false) {
      addFact('fact-floor', task.floor);
      addFact('fact-place', task.room || task.place);
    }
    addFact('fact-route', task.route);
    addFact('fact-hours', '방문 전 업무시간 확인');
    main.appendChild(facts);
    button.appendChild(main);

    const side = createText('span', 'result-side', '');
    side.appendChild(createText('span', 'relevance-badge', index === 0 ? '높은 관련도' : '관련 안내'));
    side.appendChild(createText('span', 'result-action', '위치와 상세정보'));
    button.appendChild(side);

    button.addEventListener('click', () => {
      document.querySelectorAll('.result-card').forEach((card) => {
        card.classList.remove('active');
        card.setAttribute('aria-pressed', 'false');
      });
      button.classList.add('active');
      button.setAttribute('aria-pressed', 'true');
      showDetail(task);
      state.detailTrigger = button;
      if (!detailDialogEl.open) detailDialogEl.showModal();
    });
    resultsEl.appendChild(button);
  });
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
    const items = data.results || data.items || [];
    const total = data.total ?? data.total_count ?? items.length;
    const returnedCount = data.returned_count ?? data.displayed_count ?? items.length;
    const shown = returnedCount < total
      ? `관련 업무 ${total}건 · 상위 ${returnedCount}건 표시`
      : `관련 업무 ${total}건`;
    resultsHeadingEl.textContent = `“${query}” 검색 결과`;
    statusEl.textContent = `${shown}${aiNotice}`;
    renderResults(items);
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
  el('sms-task-name').textContent = state.selectedTask?.public_title || state.selectedTask?.name || '';
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
  statusEl.textContent = '검색어를 입력해 주세요.';
  queryInput.focus();
});
document.querySelectorAll('.quick-suggestion').forEach((button) => {
  button.addEventListener('click', () => {
    const query = button.dataset.query || button.textContent;
    queryInput.value = query;
    clearChildren(suggestionsEl);
    runSearch(query);
  });
});
queryInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') runSearch(); });
queryInput.addEventListener('input', () => {
  if (state.suggestionController) state.suggestionController.abort();
  clearTimeout(state.suggestionTimer);
  state.suggestionTimer = setTimeout(loadSuggestions, 300);
});
document.querySelectorAll('.floor-tabs button').forEach((button) =>
  button.addEventListener('click', () => {
    if (state.selectedTask?.show_map === false) {
      showMap(state.selectedTask);
      return;
    }
    if (state.selectedTask?.floor === button.dataset.floor) {
      showMap(state.selectedTask);
      return;
    }
    state.mapSelectionToken += 1;
    setActiveFloor(button.dataset.floor, false);
  })
);
el('sms-form').addEventListener('submit', submitSms);
el('cancel-sms').addEventListener('click', () => el('sms-dialog').close());
el('close-detail').addEventListener('click', () => detailDialogEl.close());
detailDialogEl.addEventListener('close', () => {
  if (state.detailTrigger?.isConnected) state.detailTrigger.focus();
  state.detailTrigger = null;
});

const heroSubtitleViewport = document.querySelector('.hero-subtitle-viewport');
if (heroSubtitleViewport) {
  const toggleHeroSubtitle = () => {
    const paused = !heroSubtitleViewport.classList.contains('is-paused');
    heroSubtitleViewport.classList.toggle('is-paused', paused);
    heroSubtitleViewport.setAttribute('aria-pressed', paused ? 'true' : 'false');
    if (!paused) heroSubtitleViewport.blur();
  };
  heroSubtitleViewport.addEventListener('click', toggleHeroSubtitle);
  heroSubtitleViewport.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    toggleHeroSubtitle();
  });
}

getJson('/api/map-points').then((data) => {
  state.mapPoints = data;
  state.mapPointsReady = true;
  if (state.selectedTask) showMap(state.selectedTask);
}).catch(() => {
  state.mapPointsError = true;
  if (state.selectedTask) showMap(state.selectedTask);
});
queryInput.focus();
