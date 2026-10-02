const state = {
  selectedTask: null,
  mapPoints: {},
  mapPointsReady: false,
  mapPointsError: false,
  corridorRoutes: null,
  corridorRoutesError: false,
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
const routeEl = el('map-route');
const routeLineEl = el('map-route-line');
const floorImageEl = el('floor-image');
const detailDialogEl = el('detail-dialog');
const mapPanelEl = document.querySelector('.map-panel');
const guidanceGridEl = mapPanelEl.closest('.guidance-grid');
const mapSectionHeadEl = mapPanelEl.querySelector('.section-head');
const floorTabsEl = mapPanelEl.querySelector('.floor-tabs');
const mapStageEl = mapPanelEl.querySelector('.map-stage');
const MAP_CROPS = {
  '1층': {width: 2560, height: 1709, top: 0, visibleHeight: 1709},
  '2층': {width: 2560, height: 2000, top: 0, visibleHeight: 2000},
  '3층': {width: 2560, height: 1933, top: 0, visibleHeight: 1933}
};
let visibleMarkerPoint = null;

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
  visibleMarkerPoint = null;
  guidanceGridEl.style.removeProperty('--marker-overhang');
  markerEl.classList.remove('show');
  markerEl.classList.remove('arrived');
  routeEl.classList.remove('show');
  routeLineEl.removeAttribute('d');
}

function setMapControlsHidden(hidden) {
  [mapSectionHeadEl, floorTabsEl, mapStageEl].forEach((element) => {
    element.hidden = hidden;
  });
}

function setMapPanelHidden(hidden) {
  mapPanelEl.hidden = hidden;
  guidanceGridEl.classList.toggle('map-unavailable', hidden);
}

function setMapNavigationHidden(hidden) {
  [mapSectionHeadEl, floorTabsEl].forEach((element) => {
    element.hidden = hidden;
  });
}

function applyMapCrop(floor) {
  const crop = MAP_CROPS[floor];
  if (!crop) {
    mapStageEl.classList.remove('map-cropped');
    mapStageEl.style.removeProperty('--map-crop-width');
    mapStageEl.style.removeProperty('--map-crop-height');
    mapStageEl.style.removeProperty('--map-crop-offset');
    return;
  }
  mapStageEl.classList.add('map-cropped');
  mapStageEl.style.setProperty('--map-crop-width', crop.width);
  mapStageEl.style.setProperty('--map-crop-height', crop.visibleHeight);
  mapStageEl.style.setProperty(
    '--map-crop-offset',
    `${(-crop.top / crop.height) * 100}%`
  );
}

function syncMarkerToImage(point) {
  const box = point?.label_bbox;
  const image = floorImageEl.getBoundingClientRect();
  const stage = mapStageEl.getBoundingClientRect();
  const naturalWidth = floorImageEl.naturalWidth;
  const naturalHeight = floorImageEl.naturalHeight;
  if (!box || point.review_status === 'review_required'
      || ![box.left, box.top, box.width, box.height].every(Number.isFinite)
      || box.left < 0 || box.top < 0 || box.width <= 0 || box.height <= 0
      || box.left + box.width > naturalWidth || box.top + box.height > naturalHeight
      || image.width <= 0 || image.height <= 0 || !naturalWidth || !naturalHeight) return false;
  // The lower centre of the bitmap sits above the measured printed lettering.
  // Use the LIVE image rectangle, never the card padding or a stale crop inset.
  // A common 6 CSS-pixel gap keeps the lettering clear even on small screens.
  const border = getComputedStyle(mapStageEl);
  const x = image.left - stage.left - (Number.parseFloat(border.borderLeftWidth) || 0)
    + (box.left + box.width / 2) * image.width / naturalWidth;
  const y = image.top - stage.top - (Number.parseFloat(border.borderTopWidth) || 0)
    + box.top * image.height / naturalHeight - 6;
  // Let the icon paint beyond the map frame, while reserving its overhang in
  // layout so it cannot cover the dialog heading. Never clamp its map anchor.
  const markerHeight = Number.parseFloat(getComputedStyle(markerEl).height) || 0;
  const panel = mapPanelEl.getBoundingClientRect();
  // Reserve the entire dance envelope above the frame, not just its rest pose.
  const overhang = Math.max(0, markerHeight * 1.15 + 6
    - (image.top - panel.top + box.top * image.height / naturalHeight));
  guidanceGridEl.style.setProperty('--marker-overhang', `${overhang}px`);
  markerEl.style.left = `${x}px`;
  markerEl.style.top = `${y}px`;
  return true;
}

function syncRouteOverlayToImage() {
  // The route must share the floor image's exact rendered box, not the padded
  // card/stage box.  That keeps the independent 정문 door-threshold anchor on
  // the printed doorway when responsive layout or map-stage padding changes.
  const imageRect = floorImageEl.getBoundingClientRect();
  const stageRect = mapStageEl.getBoundingClientRect();
  if (imageRect.width <= 0 || imageRect.height <= 0 || stageRect.width <= 0 || stageRect.height <= 0) return false;
  // clientLeft/clientTop round fractional borders at browser/OS scale factors.
  // Use the painted CSS border width so the SVG and image share the same origin.
  const stageStyle = getComputedStyle(mapStageEl);
  const borderLeft = Number.parseFloat(stageStyle.borderLeftWidth) || 0;
  const borderTop = Number.parseFloat(stageStyle.borderTopWidth) || 0;
  routeEl.style.inset = 'auto';
  routeEl.style.left = `${imageRect.left - stageRect.left - borderLeft}px`;
  routeEl.style.top = `${imageRect.top - stageRect.top - borderTop}px`;
  routeEl.style.right = 'auto';
  routeEl.style.bottom = 'auto';
  routeEl.style.width = `${imageRect.width}px`;
  routeEl.style.height = `${imageRect.height}px`;
  const maxStrokePercent = Number(routeEl.dataset?.maxStrokeWidthPercent || 0);
  const strokeWidth = maxStrokePercent > 0
    ? Math.min(7, imageRect.width * maxStrokePercent / 100) : 7;
  routeEl.style.setProperty('--route-stroke-width', `${strokeWidth}px`);
  return true;
}

function observeRouteImageSize() {
  // Route text and dialog scrollbars can reflow the image after showMap().
  // Keep the SVG on the live image box, without changing any waypoint.
  const observer = new ResizeObserver(() => {
    if (detailDialogEl.open && visibleMarkerPoint) syncMarkerToImage(visibleMarkerPoint);
    if (detailDialogEl.open && routeEl.classList.contains('show')) {
      syncRouteOverlayToImage();
    }
  });
  observer.observe(floorImageEl);
  return observer;
}

const routeImageSizeObserver = observeRouteImageSize();

function isValidMapPoint(point) {
  return Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.y))
    && Number(point.x) >= 0 && Number(point.x) <= 100
    && Number(point.y) >= 0 && Number(point.y) <= 100;
}

function isVerifiedMapTarget(point) {
  return point?.review_status !== 'review_required';
}

function getDisplayedMapTarget(task) {
  // This is the exact location string rendered in each search-result card.
  // Corridor routes are therefore shared by the visible destination, rather
  // than by an internal task ID or an older raw-task place value.
  return task?.room || task?.place || '';
}

function getMapTargetName(task, point) {
  return point?.printed_label || getDisplayedMapTarget(task);
}

function getMapTargetRoute(task, point) {
  const targetName = getMapTargetName(task, point);
  const targetType = point?.map_target_type === 'department'
    ? '담당 부서 위치'
    : '방문 장소';
  return `${targetType}: ${task.floor} ${targetName}`;
}

function createMapRoutePath(points) {
  return points.map((point, index) => `${index ? 'L' : 'M'} ${Number(point.x).toFixed(2)} ${Number(point.y).toFixed(2)}`).join(' ');
}

function normalizeRouteTargetName(value) {
  return String(value || '')
    .normalize('NFC')
    .replace(/[\s·ㆍ・]+/g, '')
    .replace(/^\d+층/, '');
}

function getMapPointForTarget(points, target) {
  const normalizedTarget = normalizeRouteTargetName(target);
  if (!normalizedTarget) return null;
  let point = points[target] || Object.entries(points).find(([name]) =>
    name !== 'start' && name !== '정문'
      && normalizeRouteTargetName(name) === normalizedTarget
  )?.[1] || Object.entries(points).find(([name]) =>
    name !== 'start' && name !== '정문'
      && (String(target).includes(name) || name.includes(String(target)))
  )?.[1];
  // Registry aliases share the verified destination anchor as well as the
  // route. Do not use a stale coordinate copied into an alias entry.
  const visited = new Set();
  while (point?.alias_of) {
    if (visited.has(point.alias_of)) return null;
    visited.add(point.alias_of);
    point = points[point.alias_of];
  }
  return point || null;
}

function getCorridorRoute(floor, target) {
  const routes = state.corridorRoutes?.floors?.[floor]?.routes;
  if (!routes) return null;
  if (routes[target]) return routes[target];
  const canonicalTarget = normalizeRouteTargetName(target);
  const routeKey = Object.keys(routes).find((name) => normalizeRouteTargetName(name) === canonicalTarget);
  return routeKey ? routes[routeKey] : null;
}

function showCorridorRoute(route, floor, selectionToken) {
  routeEl.classList.remove('show');
  routeLineEl.removeAttribute('d');
  if (selectionToken !== state.mapSelectionToken || route?.status !== 'VERIFIED') return false;
  const registry = state.corridorRoutes?.floors?.[floor];
  const requiredStartId = registry?.route_start_waypoint ||
    (floor === '1층' ? state.corridorRoutes?.render_contract?.route_start_waypoint : null);
  const requiredStartType = floor === '1층' ? 'entrance' : registry?.route_start_point_type;
  // Independent, verified start per floor: the printed main door on 1F;
  // the user-specified circular throat on 2F/3F. Never copy a 1F entrance
  // onto an upper floor or measure a start relative to the outer card.
  if (!requiredStartId || route.waypoint_ids?.[0] !== requiredStartId) return false;
  const startPoint = registry?.waypoints?.[requiredStartId];
  // Legacy 1F-only points predate an explicit floor field; their registry
  // still fixes the floor. New upper-floor points must declare it explicitly.
  const matchesFloor = (point) => point?.floor === floor ||
    (floor === '1층' && point?.floor === undefined);
  if (!['entrance', 'floor_transition'].includes(requiredStartType) ||
      startPoint?.point_type !== requiredStartType || startPoint?.status !== 'VERIFIED' ||
      !matchesFloor(startPoint) || !isValidMapPoint(startPoint)) return false;
  const points = route.waypoint_ids.map((id) => registry?.waypoints?.[id]);
  // Do not filter a missing waypoint: that would create a diagonal shortcut.
  if (points.length < 2 || !points.every((point) => isValidMapPoint(point) &&
      point.status === 'VERIFIED' && matchesFloor(point))) return false;
  routeEl.dataset.maxStrokeWidthPercent = String(route.max_stroke_width_percent || 0);
  if (!syncRouteOverlayToImage()) return false;
  // The SVG now occupies only the actual floor-image rectangle, so natural
  // map percentages are used directly without card-padding conversion.
  routeLineEl.setAttribute('d', createMapRoutePath(points));
  routeEl.classList.add('show');
  return true;
}

function resetMap() {
  state.mapSelectionToken += 1;
  setMapPanelHidden(false);
  setMapControlsHidden(false);
  applyMapCrop('');
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
  window.VaccinationView?.reset();
  window.ServiceGuidanceView?.reset();
  window.ResultsView?.reset();
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
  applyMapCrop(floor);
  const floorImagePath = floorNumber ? `/images/floor-${floorNumber}.webp` : '';
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
  if (selectionToken !== state.mapSelectionToken) return;
  if (!syncMarkerToImage(point)) return;
  visibleMarkerPoint = point;
  markerEl.classList.remove('is-resetting');
  markerEl.classList.add('show', 'arrived');
  // The route is selected by the verified printed map target, not by task ID
  // or the wording of an individual search result.  All results resolving to
  // the same 1층 민원실 target therefore share one corridor route.
  const corridorRoute = getCorridorRoute(task.floor, getMapTargetName(task, point));
  if (showCorridorRoute(corridorRoute, task.floor, selectionToken)) {
    const routeNotice = corridorRoute.display_notice || '빨간 선은 확인된 복도와 출입구 접근점까지만 표시합니다.';
    el('route-text').textContent = `${getMapTargetRoute(task, point)}. ${routeNotice}`;
  } else {
    routeEl.classList.remove('show');
    const reason = corridorRoute?.reason || '복도와 출입구 연결 확인이 필요합니다.';
    el('route-text').textContent = `${getMapTargetRoute(task, point)}. ${reason}`;
  }
}

function showMap(task) {
  const selectionToken = ++state.mapSelectionToken;
  if (task?.show_map === false) {
    setMapPanelHidden(true);
    setMapControlsHidden(true);
    hideMapLocation();
    routeLineEl.removeAttribute('d');
    markerEl.style.left = '';
    markerEl.style.top = '';
    setActiveFloor('', true);
    floorImageEl.alt = '';
    el('floor-label').textContent = '방문 장소 확인';
    el('route-text').textContent = task.route || '방문 장소는 전화로 확인해 주세요.';
    return;
  }
  setMapPanelHidden(false);
  setMapControlsHidden(false);
  setMapNavigationHidden(true);
  const displayedTarget = getDisplayedMapTarget(task);
  if (!task?.floor || !displayedTarget) {
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
  const point = getMapPointForTarget(points, displayedTarget);
  if (!isValidMapPoint(point)) {
    hideMapLocation();
    el('route-text').textContent = `${task.floor} ${displayedTarget}: 지도 좌표 확인이 필요합니다.`;
    return;
  }
  if (!isVerifiedMapTarget(point)) {
    setMapPanelHidden(true);
    setMapControlsHidden(true);
    hideMapLocation();
    routeLineEl.removeAttribute('d');
    markerEl.style.left = '';
    markerEl.style.top = '';
    setActiveFloor('', true);
    floorImageEl.alt = '';
    el('floor-label').textContent = '방문 장소 확인';
    el('route-text').textContent = `${task.floor} ${displayedTarget}: 지도 위치 확인이 필요합니다.`;
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
  if (!hasPublicText(value)) return false;
  const row = createText('div', `detail-row ${className}`.trim(), '');
  row.appendChild(createText('strong', '', label));
  row.appendChild(createText('span', '', value));
  container.appendChild(row);
  return true;
}

function hasPublicText(value) {
  return typeof value === 'string' && value.trim();
}

function joinPublicText(values) {
  return [...new Set(values.filter((value) => typeof value === 'string' && value.trim()))].join(' ');
}

function getPrimaryContact(task) {
  const directContact = task?.primary_contact;
  if (directContact && (directContact.phone || directContact.display_phone)) return directContact;
  const contacts = Array.isArray(task?.contacts) ? task.contacts : [];
  return contacts.find((contact) => contact.is_primary && (contact.phone || contact.display_phone)) || null;
}

function appendPrimaryContact(container, contact) {
  const purpose = contact.purpose || contact.role;
  if (purpose) container.appendChild(createText('span', '', `${purpose}: `));
  const displayPhone = contact.display_phone || contact.phone || '';
  const telDigits = String(contact.phone || displayPhone).replace(/\D/g, '');
  if (telDigits) {
    const link = createText('a', 'contact-link', displayPhone);
    link.href = `tel:${telDigits}`;
    container.appendChild(link);
  } else {
    container.appendChild(createText('span', '', displayPhone));
  }
  if (contact.condition) {
    container.appendChild(document.createElement('br'));
    container.appendChild(createText('span', '', `조건: ${contact.condition}`));
  }
}

// Reviewed facility/department LOCATION guides, independent of title wording.
// Unlisted and future tasks keep full guidance; never infer from an '안내' suffix.
const LOCATION_ONLY_GUIDE_IDS = new Set([
  'F102', 'F103', 'F104', 'F106', 'F107', 'F108', 'F109', 'F110',
  'F111', 'F112', 'F201', 'F202', 'F203', 'F204', 'F206',
  'F301', 'F302', 'F303', 'F305'
]);
function isLocationOnlyGuide(task) {
  return Boolean(hasPublicText(task?.public_title) && LOCATION_ONLY_GUIDE_IDS.has(task?.id));
}

function getLocationVisitText(task) {
  // Directions and cautions have different meanings; never merge them into
  // an apparent sequence of actions for a visitor.
  return task?.visit_steps || '';
}

function showDetail(task) {
  state.selectedTask = task;
  clearChildren(detailEl);
  detailEl.className = 'detail-grid';
  const isGuidedTask = hasPublicText(task.public_title);
  const isLocationGuide = isLocationOnlyGuide(task);
  if (isGuidedTask) detailEl.appendChild(createText('h3', '', task.public_title));

  const publicLocation = isGuidedTask ? task.route : null;
  if (!isLocationGuide) {
    addDetailRow(detailEl, '어떤 업무인가요?', isGuidedTask ? task.public_summary : null);
    addDetailRow(detailEl, '누가 이용할 수 있나요?', isGuidedTask ? task.eligibility : null);
  }
  addDetailRow(detailEl, '어디로 가나요?', publicLocation);
  addDetailRow(detailEl, '무엇을 준비하나요?', isGuidedTask ? task.documents : null);
  addDetailRow(detailEl, '비용은 얼마인가요?', isGuidedTask ? task.fee : null);
  addDetailRow(detailEl, '언제 이용하나요?', isGuidedTask ? task.operating_hours : null);
  addDetailRow(
    detailEl,
    '어떻게 이용하나요?',
    isGuidedTask ? (isLocationGuide ? getLocationVisitText(task) : task.visit_steps) : null,
    'script-box'
  );
  if (!isLocationGuide && task.primary_action !== task.visit_steps) {
    addDetailRow(detailEl, '추가 안내', isGuidedTask ? task.primary_action : null);
  }

  const primaryContact = getPrimaryContact(task);
  const detailContacts = [];
  const seenPhones = new Set();
  for (const contact of [primaryContact, ...(Array.isArray(task.contacts) ? task.contacts : [])]) {
    if (!contact) continue;
    const key = String(contact.phone || contact.display_phone || '').replace(/\D/g, '');
    if (!key || seenPhones.has(key)) continue;
    seenPhones.add(key);
    detailContacts.push(contact);
  }
  if (detailContacts.length) {
    const phoneRow = createText('div', 'detail-row', '');
    phoneRow.appendChild(createText('strong', '', '문의전화'));
    const contactValue = createText('span', '', '');
    for (const contact of detailContacts) {
      if (contactValue.children.length) contactValue.appendChild(document.createElement('br'));
      appendPrimaryContact(contactValue, contact);
    }
    phoneRow.appendChild(contactValue);
    detailEl.appendChild(phoneRow);
  }
  addDetailRow(detailEl, '꼭 알아두세요', isGuidedTask ? task.public_caution : null);

  if (isGuidedTask) {
    const smsButton = createText('button', 'contact-button', '이 안내를 문자메시지로 받기');
    smsButton.type = 'button';
    smsButton.addEventListener('click', openSmsDialog);
    detailEl.appendChild(smsButton);
    if (!primaryContact?.phone) {
      detailEl.appendChild(createText('p', 'help', detailContacts.length
        ? '위 문의전화에서 필요한 업무의 번호를 선택해 주세요.'
        : '문의전화는 미등록 상태이며, 안내 내용은 문자로 받을 수 있습니다.'));
    }
  }
  showMap(task);
  window.DetailView?.render(task, {isLocationGuide, primaryContact});
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
    button.setAttribute('aria-controls', task.result_kind === 'guide' ? 'service-guide-dialog' : 'detail-dialog');

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
      if (task.result_kind === 'guide') { task.open(button); return; }
      document.querySelectorAll('.result-card').forEach((card) => {
        card.classList.remove('active');
        card.setAttribute('aria-pressed', 'false');
      });
      button.classList.add('active');
      button.setAttribute('aria-pressed', 'true');
      state.detailTrigger = button;
      if (!detailDialogEl.open) detailDialogEl.showModal();
      // A cached floor image renders synchronously. Open the dialog before
      // showDetail measures its image box, including on every later result.
      showDetail(task);
    });
    resultsEl.appendChild(button);
  });
  window.ResultsView?.render(items);
}

async function runSearch(value = queryInput.value) {
  const query = value.trim();
  const workspace = el('search-workspace');
  workspace.hidden = false;
  if (state.searchController) state.searchController.abort();
  window.VaccinationView?.reset();
  window.ServiceGuidanceView?.reset();
  if (query.length < 2) {
    resetSearchView();
    statusEl.textContent = '두 글자 이상의 검색어를 입력하십시오.';
    workspace.scrollIntoView({block: 'start', behavior: 'auto'});
    return;
  }
  statusEl.textContent = '검색 중입니다...';
  state.searchController = new AbortController();
  const controller = state.searchController;
  try {
    const data = await getJson('/api/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(document.body.classList.contains('results-v2') ? {query, limit: 100} : {query}),
      signal: controller.signal
    });
    if (controller.signal.aborted || state.searchController !== controller) return;
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
    const guides = window.ServiceGuidanceView?.entries(data, query, async (taskId, trigger) => {
      const task = await getJson(`/api/tasks/${encodeURIComponent(taskId)}`);
      if (query !== queryInput.value.trim() || !trigger.isConnected) return;
      state.detailTrigger = trigger;
      if (!detailDialogEl.open) detailDialogEl.showModal();
      showDetail(task);
    }) || [];
    const entries = window.ServiceGuidanceView?.compose(guides, items) || items;
    renderResults(entries);
    window.VaccinationView?.render(data.vaccination, query);
    statusEl.textContent = `검색 결과 ${entries.length}건 · 이용 안내 ${guides.length}건 · 업무·위치 ${entries.length - guides.length}건`;
    if (!guides.length && !items.length && window.VaccinationView?.hasResults()) {
      resultsEl.querySelector('.empty').textContent = '일치하는 업무·이용 안내가 없습니다. 아래 참고자료를 확인할 수 있습니다.';
    }
    workspace.scrollIntoView({block: 'start', behavior: 'auto'});
  } catch (error) {
    if (controller.signal.aborted || state.searchController !== controller) return;
    if (error.name === 'AbortError') return;
    resetSearchView('검색 중 오류가 발생했습니다. 잠시 후 다시 시도하십시오.');
    statusEl.textContent = error.message;
    workspace.scrollIntoView({block: 'start', behavior: 'auto'});
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

const SMS_MESSAGE_KIND = 'guidance';
let smsPreviewVersion = 0;
let smsRequestId = null;
let smsBusy = false;
let smsPreviewReady = false;
let smsDialogTrigger = null;

async function updateSmsPreview() {
  const version = ++smsPreviewVersion;
  smsRequestId = crypto.randomUUID();
  smsPreviewReady = false;
  el('send-sms').disabled = true;
  el('sms-preview').value = '';
  el('sms-status').textContent = '발송 내용을 확인하고 있습니다...';
  try {
    const data = await getJson('/api/sms/preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task_id: state.selectedTask.id, message_kind: SMS_MESSAGE_KIND})
    });
    if (version !== smsPreviewVersion) return;
    el('sms-preview').value = data.text;
    smsPreviewReady = data.ready;
    el('sms-status').textContent = smsPreviewReady ? '' : (data.notice || '문자 발송 준비가 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.');
    el('send-sms').disabled = !smsPreviewReady || smsBusy;
  } catch (error) {
    if (version === smsPreviewVersion) el('sms-status').textContent = error.message;
  }
}

function smsTaskHeading(task) {
  const title = task?.public_title || '';
  return title === '예방접종 장소와 준비사항을 확인하고 싶으신가요?'
    ? '예방접종 장소와 준비사항을 알려드릴게요.'
    : title;
}

function openSmsDialog(event) {
  if (smsBusy) return;
  smsDialogTrigger = event?.currentTarget || document.activeElement;
  el('sms-task-name').textContent = smsTaskHeading(state.selectedTask);
  el('sms-status').textContent = '';
  el('recipient').value = '';
  el('consent').checked = false;
  el('sms-dialog').showModal();
  updateSmsPreview();
}

function showSmsResult(data) {
  const mocked = data.status === 'mocked';
  el('sms-result-title').textContent = mocked ? '모의 발송이 완료되었습니다' : '발송되었습니다';
  el('sms-result-message').textContent = mocked
    ? '테스트 모드입니다. 실제 문자는 발송되지 않았습니다.'
    : '발송 서비스에 요청이 접수되었습니다.\n실제 수신까지는 시간이 걸릴 수 있습니다.';
  el('sms-dialog').close();
  el('sms-result-dialog').showModal();
}

function dismissSmsResult(event) {
  // Native dialog backdrops and the card's own empty padding target the dialog.
  if (event.target === el('sms-result-dialog')) el('sms-result-dialog').close();
}

async function submitSms(event) {
  event.preventDefault();
  if (smsBusy || !smsPreviewReady) return;
  smsBusy = true;
  const sendButton = el('send-sms');
  sendButton.disabled = true;
  el('recipient').readOnly = true;
  el('consent').disabled = true;
  el('cancel-sms').disabled = true;
  el('sms-status').textContent = '전송 중입니다...';
  try {
    const data = await getJson('/api/sms', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        task_id: state.selectedTask.id,
        recipient: el('recipient').value,
        consent: el('consent').checked,
        message_kind: SMS_MESSAGE_KIND,
        request_id: smsRequestId
      })
    });
    if (data.status !== 'accepted' && data.status !== 'mocked') {
      throw new Error('문자 발송 결과를 확인할 수 없습니다. 중복 발송하지 말고 관리자에게 확인해 주세요.');
    }
    smsPreviewReady = false;
    el('sms-status').textContent = '';
    showSmsResult(data);
  } catch (error) {
    el('sms-status').textContent = error.message;
  } finally {
    smsBusy = false;
    sendButton.disabled = !smsPreviewReady;
    el('recipient').readOnly = false;
    el('consent').disabled = false;
    el('cancel-sms').disabled = false;
  }
}

el('search-button').addEventListener('click', () => runSearch());
el('clear-button').addEventListener('click', () => {
  if (state.searchController) state.searchController.abort();
  if (state.suggestionController) state.suggestionController.abort();
  queryInput.value = '';
  clearChildren(suggestionsEl);
  resetSearchView();
  el('search-workspace').hidden = true;
  statusEl.textContent = '검색어를 입력해 주세요.';
  queryInput.focus({preventScroll: true});
  window.scrollTo({top: 0, behavior: 'auto'});
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
el('sms-form').addEventListener('submit', submitSms);
el('recipient').addEventListener('input', () => { smsRequestId = crypto.randomUUID(); });
el('cancel-sms').addEventListener('click', () => { if (!smsBusy) el('sms-dialog').close(); });
el('sms-dialog').addEventListener('cancel', (event) => { if (smsBusy) event.preventDefault(); });
el('sms-result-dialog').addEventListener('click', dismissSmsResult);
el('close-sms-result').addEventListener('click', () => el('sms-result-dialog').close());
el('sms-result-dialog').addEventListener('close', () => {
  if (smsDialogTrigger?.isConnected) smsDialogTrigger.focus({preventScroll: true});
});
el('close-detail').addEventListener('click', () => detailDialogEl.close());
detailDialogEl.addEventListener('close', () => {
  if (state.detailTrigger?.isConnected) state.detailTrigger.focus();
  state.detailTrigger = null;
});

function initializeHeroSubtitle(viewport) {
  const subtitle = viewport?.querySelector('.hero-subtitle');
  if (!subtitle) return;
  const characters = Array.from(subtitle.textContent, (character) => {
    const span = document.createElement('span');
    span.textContent = character;
    return span;
  });
  if (!characters.length) return;
  // Hidden characters retain the full sentence's centred, wrapping layout.
  // The static accessible label is not rewritten for every character.
  subtitle.replaceChildren(...characters);
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const characterInterval = 90;
  const blinkDuration = 3000;
  let timer = null;
  let index = 0;
  let paused = false;

  const typeNext = () => {
    characters[index].style.visibility = 'visible';
    index += 1;
    if (index === characters.length) {
      viewport.dataset.phase = 'blinking';
      subtitle.classList.add('is-blinking');
      timer = window.setTimeout(restart, blinkDuration);
    } else {
      timer = window.setTimeout(typeNext, characterInterval);
    }
  };

  const restart = () => {
    window.clearTimeout(timer);
    subtitle.classList.remove('is-blinking');
    index = 0;
    const staticText = paused || reducedMotion.matches || document.hidden;
    characters.forEach((span) => { span.style.visibility = staticText ? 'visible' : 'hidden'; });
    viewport.dataset.phase = staticText ? 'static' : 'typing';
    if (!staticText) timer = window.setTimeout(typeNext, characterInterval);
  };

  const toggle = () => {
    paused = !paused;
    viewport.setAttribute('aria-pressed', String(paused));
    restart();
  };
  viewport.addEventListener('click', toggle);
  viewport.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    toggle();
  });
  reducedMotion.addEventListener('change', restart);
  document.addEventListener('visibilitychange', restart);
  restart();
}
initializeHeroSubtitle(document.querySelector('.hero-subtitle-viewport'));

getJson('/api/map-points').then((data) => {
  state.mapPoints = data;
  state.mapPointsReady = true;
  if (state.selectedTask) showMap(state.selectedTask);
}).catch(() => {
  state.mapPointsError = true;
  if (state.selectedTask) showMap(state.selectedTask);
});
// Preserve the initial HOME composition; do not scroll or open a mobile keyboard.
if (matchMedia('(min-width: 761px) and (pointer: fine)').matches) {
  queryInput.focus({preventScroll: true});
}



// Temporary v2.7 only: Korean current-floor display, not an interactive control.
const mapFloorBadgeEl = document.createElement('span');
mapFloorBadgeEl.className = 'map-floor-badge';
mapFloorBadgeEl.hidden = true;
mapFloorBadgeEl.setAttribute('aria-hidden', 'true');
mapStageEl.appendChild(mapFloorBadgeEl);
function updateMapFloorBadge() {
  const match = /^([123])층$/.exec(el('floor-label').textContent || '');
  const visible = Boolean(match) && !mapPanelEl.hidden && !mapStageEl.hidden;
  mapFloorBadgeEl.hidden = !visible;
  if (!visible) return;
  const floorText = `${match[1]}층`;
  mapFloorBadgeEl.textContent = floorText;
  mapStageEl.setAttribute('role', 'img');
  mapStageEl.setAttribute('aria-label', `현재 ${floorText} 배치도`);
  floorImageEl.alt = '';
}
new MutationObserver(updateMapFloorBadge).observe(el('floor-label'), {childList: true, characterData: true, subtree: true});
new MutationObserver(updateMapFloorBadge).observe(mapPanelEl, {attributes: true, attributeFilter: ['hidden']});
new MutationObserver(updateMapFloorBadge).observe(mapStageEl, {attributes: true, attributeFilter: ['hidden']});
updateMapFloorBadge();

window.addEventListener('resize', () => {
  if (detailDialogEl.open && visibleMarkerPoint) syncMarkerToImage(visibleMarkerPoint);
  const task = state.selectedTask;
  if (!task?.show_map || !state.corridorRoutes) return;
  const floorPoints = state.mapPoints[task.floor] || {};
  const displayedTarget = getDisplayedMapTarget(task);
  const point = getMapPointForTarget(floorPoints, displayedTarget);
  showCorridorRoute(getCorridorRoute(task.floor, getMapTargetName(task, point)), task.floor, state.mapSelectionToken);
});

getJson('/data/corridor_routes.json?candidate_revision=shared-route-target-3', {cache: 'no-store'}).then((routes) => {
  state.corridorRoutes = routes;
  if (state.selectedTask) showMap(state.selectedTask);
}).catch(() => {
  state.corridorRoutesError = true;
  hideMapLocation();
});
