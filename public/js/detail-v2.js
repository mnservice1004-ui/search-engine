/* Detail presentation only. The reviewed data, route geometry and SMS owner
   remain in app.js. No medical facts or floor coordinates are inferred here. */
(() => {
  'use strict';
  const byId = (id) => document.getElementById(id);
  const dialog = byId('detail-dialog');
  const detail = byId('detail');
  const stage = dialog?.querySelector('.map-stage');
  const viewport = dialog?.querySelector('.detail-map-viewport');
  const panel = dialog?.querySelector('.map-panel');
  if (!dialog || !detail || !stage || !viewport || !panel) return;
  let selected = null;
  let zoom = 100;
  let restoring = 0;
  let sharedTask = null;
  let printZoom = 100;
  let printExpanded = false;

  const paths = {
    location: ['M12 22s8-8 8-14a8 8 0 0 0-16 0c0 6 8 14 8 14Z', 'M9 8a3 3 0 1 0 6 0 3 3 0 0 0-6 0'],
    hours: ['M22 12a10 10 0 1 0-20 0 10 10 0 0 0 20 0', 'M12 6v6l4 2'],
    department: ['M3 22V7h5V2h8v5h5v15H3Z', 'M10 22v-5h4v5M6 10v2m4-7v2m4-2v2m4 3v2M6 15v2m12-2v2M10 10v2m4-2v2'],
    eligibility: ['M15 6a3 3 0 1 0-6 0 3 3 0 0 0 6 0', 'M4 22v-5a8 8 0 0 1 16 0v5H4Z'],
    documents: ['M5 2h10l4 4v16H5V2Z', 'M14 2v5h5M8 11h8M8 15h8M8 19h5'],
    fee: ['M22 12a10 10 0 1 0-20 0 10 10 0 0 0 20 0', 'm6 8 3 9 3-7 3 7 3-9M5 12h14'],
    steps: ['M16 4a2 2 0 1 0-4 0 2 2 0 0 0 4 0', 'm7 11 5-3 4 5 4 1M12 8l-2 8-5 6m5-6 6 2 1 4'],
    phone: ['m5 2 4 5-3 3a16 16 0 0 0 8 8l3-3 5 4c-1 5-5 4-8 3C7 19 2 14 1 7 0 4 2 2 5 2Z'],
    caution: ['M22 12a10 10 0 1 0-20 0 10 10 0 0 0 20 0', 'M12 6v8m0 3v1'],
    sms: ['M21 3H3v15h4v4l5-4h9V3Z', 'M7 10h.1m4 0h.1m4 0h.1'],
    print: ['M6 8V2h12v6M6 18H2V8h20v10h-4M6 14h12v8H6V14Z', 'M18 11h1'],
    link: ['m9 15 6-6M8 16l-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0']
  };
  function icon(kind) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', kind === 'link' ? '-2 -2 28 28' : '0 0 24 24');
    svg.setAttribute('class', 'detail-icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.8');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    (paths[kind] || paths.documents).forEach((d) => {
      const path = document.createElementNS(svg.namespaceURI, 'path');
      path.setAttribute('d', d);
      svg.appendChild(path);
    });
    return svg;
  }
  function node(tag, className, text = '') {
    const result = document.createElement(tag);
    result.className = className;
    result.textContent = text;
    return result;
  }
  function action(tag, label, kind) {
    const button = node(tag, '', label);
    if (tag === 'button') button.type = 'button';
    button.prepend(icon(kind));
    return button;
  }
  // Only explicitly reviewed sequences may become numbered instructions.
  // Sentence punctuation and visual wrapping do not imply an action step.
  const REVIEWED_STEP_GUIDE_IDS = new Set(['F109']);
  function splitSteps(text) {
    return String(text || '').split(/\r?\n+/u).map((line) => line.trim()).filter(Boolean);
  }
  function sharedUrl(taskId, base = window.location.href) {
    if (!/^[A-Z][0-9]{3}$/.test(String(taskId))) return null;
    const url = new URL('/', base);
    url.searchParams.set('task', taskId);
    return url.href;
  }
  function resetZoom(value = 100) {
    zoom = Math.max(100, Math.min(200, Number(value) || 100));
    stage.style.width = `${zoom}%`;
    viewport.classList.toggle('is-zoomed', zoom > 100);
    if (zoom > 100) viewport.style.maxHeight = `${Math.max(280, viewport.clientWidth * 2000 / 2560 + 80)}px`;
    else viewport.style.removeProperty('max-height');
    byId('detail-zoom-reset').textContent = `${zoom}%`;
    byId('detail-zoom-in').disabled = zoom === 200;
    byId('detail-zoom-out').disabled = zoom === 100;
    if (zoom === 100) { viewport.scrollLeft = 0; viewport.scrollTop = 0; }
    // A real layout resize drives app.js's existing image ResizeObserver.
    // Never transform the image independently from its route and marker.
  }
  function mapExpanded(expanded) {
    dialog.classList.toggle('is-map-expanded', expanded);
    byId('detail-map-expand').setAttribute('aria-expanded', String(expanded));
    byId('detail-map-expand').textContent = expanded ? '상세정보 함께 보기' : '지도 크게 보기';
  }
  function syncMapStatus() {
    if (!selected) return;
    const sourceBox = typeof visibleMarkerPoint !== 'undefined' ? visibleMarkerPoint?.label_bbox : null;
    const image = byId('floor-image');
    if (sourceBox && image.naturalWidth > 0 && image.naturalHeight > 0) {
      // Print layout can reflow while JS is blocked by the print dialog.
      // CSS uses the same source-image anchor instead of stale screen pixels.
      stage.style.setProperty('--detail-marker-x', (sourceBox.left + sourceBox.width / 2) / image.naturalWidth);
      stage.style.setProperty('--detail-marker-y', sourceBox.top / image.naturalHeight);
      if (typeof getComputedStyle === 'function') {
        const markerHeight = Number.parseFloat(getComputedStyle(byId('map-marker')).height) || 0;
        const inset = Number.parseFloat(getComputedStyle(stage).paddingTop) || 0;
        const clearance = Math.max(0, markerHeight * 1.15 + 10 - inset
          - sourceBox.top * image.getBoundingClientRect().height / image.naturalHeight);
        viewport.style.setProperty('--detail-marker-clearance', `${clearance}px`);
      }
    } else {
      viewport.style.removeProperty('--detail-marker-clearance');
    }
    const hasRoute = byId('map-route').classList.contains('show');
    const startCoordinates = /^M\s+([\d.]+)\s+([\d.]+)/.exec(byId('map-route-line').getAttribute('d') || '');
    let startMarker = byId('detail-route-start');
    if (!startMarker) {
      startMarker = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      startMarker.id = 'detail-route-start';
      startMarker.setAttribute('r', '0.9');
      startMarker.setAttribute('vector-effect', 'non-scaling-stroke');
      byId('map-route').appendChild(startMarker);
    }
    startMarker.style.display = hasRoute && startCoordinates ? '' : 'none';
    if (startCoordinates) { startMarker.setAttribute('cx', startCoordinates[1]); startMarker.setAttribute('cy', startCoordinates[2]); }
    const hidden = panel.hidden || stage.hidden;
    const ready = byId('floor-image').complete && byId('floor-image').naturalWidth > 0;
    const start = selected.floor === '1층' ? '1층 정문' : `${selected.floor || ''} 지정 출발점`;
    const text = hidden ? '' : hasRoute
      ? `${start}에서 출발하는 안내 경로입니다. 실시간 현재 위치는 표시하지 않습니다.`
      : ready ? '확인된 위치를 표시합니다. 연결 경로가 없는 경우 방문 전 담당 부서에 문의해 주세요.'
      : '지도를 불러오는 중입니다. 표시되지 않으면 담당 부서에 문의해 주세요.';
    const status = byId('detail-map-status');
    if (status.textContent !== text) status.textContent = text;
    dialog.querySelector('.detail-map-legend').hidden = hidden || !hasRoute;
    ['detail-zoom-in', 'detail-zoom-reset', 'detail-zoom-out', 'detail-map-expand'].forEach((id) => {
      const unavailable = hidden || !ready;
      byId(id).disabled = unavailable || (id === 'detail-zoom-in' && zoom === 200)
        || (id === 'detail-zoom-out' && zoom === 100);
    });
  }
  function enhanceRow(row, kind, label, numberedSteps = false) {
    row.dataset.detailKind = kind;
    const heading = row.querySelector('strong');
    if (heading) { heading.textContent = label; heading.prepend(icon(kind)); }
    if (kind === 'steps' && numberedSteps) {
      const value = row.querySelector('span');
      const steps = splitSteps(value?.textContent);
      if (value && steps.length > 1) {
        const list = node('ol', 'detail-steps');
        steps.forEach((text) => list.appendChild(node('li', '', text)));
        value.replaceChildren(list);
      }
    }
    return row;
  }
  function render(task, {isLocationGuide = false, primaryContact = null} = {}) {
    selected = task;
    mapExpanded(false);
    resetZoom();
    const title = task.public_title || task.name || '민원 안내';
    const summary = isLocationGuide ? task.route : task.public_summary;
    byId('detail-dialog-title').textContent = title;
    byId('detail-context').textContent = task.department || '보건민원';
    byId('detail-subtitle').textContent = summary || '등록된 방문 장소와 이용 안내를 확인해 주세요.';
    byId('detail-map-label').textContent = [task.floor, task.room || task.place].filter(Boolean).join(' · ');
    const oldRows = new Map([...detail.querySelectorAll('.detail-row')].map((row) => [row.querySelector('strong')?.textContent, row]));
    const sms = detail.querySelector('.contact-button');
    detail.replaceChildren(node('span', 'detail-service-tag', isLocationGuide ? '위치 안내' : '민원 안내'),
      node('h3', 'detail-service-title', title));
    // The dialog header already contains this summary. Keep the card compact
    // without changing the reviewed source text used by search and SMS.
    const order = [
      ['어디로 가나요?', 'location', '위치'], ['언제 이용하나요?', 'hours', '운영시간'],
      ['누가 이용할 수 있나요?', 'eligibility', '이용 대상'], ['무엇을 준비하나요?', 'documents', '준비사항'],
      ['비용은 얼마인가요?', 'fee', '비용'], ['어떻게 이용하나요?', 'steps', isLocationGuide ? '찾아가는 방법' : '이용 절차'],
      ['추가 안내', 'note', '추가 안내'],
      ['문의전화', 'phone', '문의전화'], ['꼭 알아두세요', 'caution', '방문 전 확인']
    ];
    order.forEach(([oldLabel, kind, label], index) => {
      if (oldRows.has(oldLabel)) detail.appendChild(enhanceRow(oldRows.get(oldLabel), kind, label,
        kind === 'steps' && REVIEWED_STEP_GUIDE_IDS.has(task.id)));
      if (index === 1 && (task.department || task.team)) {
        const row = node('div', 'detail-row');
        row.append(node('strong', '', '담당 부서'), node('span', '', [task.department, task.team].filter(Boolean).join(' · ')));
        detail.appendChild(enhanceRow(row, 'department', '담당 부서'));
      }
    });
    const actions = node('div', 'detail-actions');
    if (sms) { sms.prepend(icon('sms')); actions.appendChild(sms); }
    const secondary = node('div', 'detail-secondary-actions');
    const digits = String(primaryContact?.phone || primaryContact?.display_phone || '').replace(/\D/g, '');
    const phone = action(digits ? 'a' : 'button', '전화 문의', 'phone');
    if (digits) { phone.href = `tel:${digits}`; phone.setAttribute('aria-label', `담당 부서 전화 문의 ${primaryContact.display_phone || primaryContact.phone}`); }
    else {
      phone.disabled = true;
      phone.title = task.contacts?.some((contact) => contact.phone || contact.display_phone)
        ? '위 문의전화에서 필요한 업무의 번호를 선택해 주세요.'
        : '등록된 문의전화가 없습니다.';
    }
    const print = action('button', '인쇄하기', 'print');
    print.id = 'detail-print';
    print.addEventListener('click', () => {
      beginPrint();
      requestAnimationFrame(() => requestAnimationFrame(() => window.print()));
    });
    const copy = action('button', '링크 복사', 'link');
    copy.id = 'detail-copy-link';
    copy.addEventListener('click', () => copyLink(task.id));
    secondary.append(phone, print, copy);
    const status = node('p', '', '');
    status.id = 'detail-action-status'; status.setAttribute('role', 'status');
    actions.append(secondary, status);
    detail.appendChild(actions);
    dialog.scrollTop = 0;
    syncMapStatus();
  }
  async function copyLink(taskId) {
    const url = sharedUrl(taskId);
    const status = byId('detail-action-status');
    if (!url || !status) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(url);
      if (selected?.id === taskId) status.textContent = '이 안내로 바로 연결되는 링크를 복사했습니다.';
    } catch {
      if (selected?.id !== taskId) return;
      status.textContent = '아래 링크를 선택하여 복사해 주세요.';
      const input = node('input', 'detail-share-fallback');
      input.readOnly = true; input.value = url; input.setAttribute('aria-label', '복사할 안내 링크');
      status.appendChild(input); input.focus(); input.select();
    }
  }
  function beginPrint() {
    if (!dialog.open || document.body.classList.contains('detail-printing')) return;
    printZoom = zoom; printExpanded = dialog.classList.contains('is-map-expanded');
    document.body.classList.add('detail-printing'); mapExpanded(false); resetZoom();
  }
  function endPrint() {
    if (!document.body.classList.contains('detail-printing')) return;
    document.body.classList.remove('detail-printing'); mapExpanded(printExpanded); resetZoom(printZoom);
  }
  async function restoreSharedTask() {
    const taskParams = new URL(window.location.href).searchParams.getAll('task');
    const id = taskParams.length === 1 ? taskParams[0] : null;
    const token = ++restoring;
    if (!id || !/^[A-Z][0-9]{3}$/.test(id) || (typeof smsBusy !== 'undefined' && smsBusy)) return;
    try {
      const task = await getJson(`/api/tasks/${encodeURIComponent(id)}`);
      if (token !== restoring || new URL(window.location.href).searchParams.get('task') !== id
          || (typeof smsBusy !== 'undefined' && smsBusy)) return;
      if (task.id !== id || !task.public_title) throw new Error('Unregistered task');
      state.detailTrigger = byId('query');
      if (!dialog.open) dialog.showModal();
      sharedTask = id;
      showDetail(task);
    } catch {
      if (token !== restoring || new URL(window.location.href).searchParams.get('task') !== id
          || (typeof smsBusy !== 'undefined' && smsBusy)) return;
      // Show errors visibly in the existing results area, never a broken map.
      byId('search-workspace').hidden = false;
      byId('results-heading').textContent = '안내 링크 확인';
      resetSearchView('요청하신 안내를 불러오지 못했습니다. 검색창에서 업무를 다시 찾아 주세요.');
      byId('status').textContent = '안내 링크를 확인해 주세요.';
    }
  }
  byId('detail-zoom-in').addEventListener('click', () => resetZoom(zoom + 25));
  const locationIcon = dialog.querySelector('.detail-location-pill > span');
  locationIcon.replaceChildren(icon('location'));
  byId('detail-zoom-out').addEventListener('click', () => resetZoom(zoom - 25));
  byId('detail-zoom-reset').addEventListener('click', () => resetZoom());
  byId('detail-map-expand').addEventListener('click', () => { mapExpanded(!dialog.classList.contains('is-map-expanded')); resetZoom(); });
  new MutationObserver(syncMapStatus).observe(byId('map-route'), {attributes: true, attributeFilter: ['class']});
  new MutationObserver(syncMapStatus).observe(panel, {attributes: true, attributeFilter: ['hidden']});
  byId('floor-image').addEventListener('load', syncMapStatus);
  byId('floor-image').addEventListener('error', syncMapStatus);
  new ResizeObserver(syncMapStatus).observe(byId('floor-image'));
  window.addEventListener('beforeprint', beginPrint);
  window.addEventListener('afterprint', endPrint);
  window.addEventListener('popstate', restoreSharedTask);
  document.addEventListener('DOMContentLoaded', restoreSharedTask, {once: true});
  dialog.addEventListener('close', () => {
    endPrint(); mapExpanded(false); resetZoom();
    if (sharedTask && new URL(window.location.href).searchParams.get('task') === sharedTask) {
      const url = new URL(window.location.href); url.searchParams.delete('task');
      window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    }
    sharedTask = null;
  });
  window.DetailView = Object.freeze({render, resetZoom, splitSteps, sharedUrl});
})();
