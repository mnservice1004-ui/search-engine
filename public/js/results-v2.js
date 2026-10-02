/* Search-result presentation only. Existing result buttons own detail/map/SMS
 * navigation; this module never replaces those buttons or makes API requests. */
(() => {
  'use strict';

  if (!document.body.classList.contains('results-v2')) return;

  const byId = (id) => document.getElementById(id);
  const results = byId('results');
  const filters = byId('results-filters');
  const count = byId('results-count');
  const pagination = byId('results-pagination');
  const extras = byId('results-extras');
  const heading = byId('results-heading');
  const status = byId('status');
  const input = byId('query');
  if (!results || !filters || !count || !pagination || !heading || !input) return;

  const PAGE_SIZE = 4;
  const CATEGORIES = Object.freeze([
    {key: 'all', label: '전체'},
    {key: 'business', label: '보건사업'},
    {key: 'certificate', label: '민원·제증명'},
    {key: 'health', label: '건강정보'},
    {key: 'news', label: '알림마당'},
    {key: 'about', label: '보건소 소개'}
  ]);
  // Editorial UI grouping of the verified public catalog, not a new claim
  // about departmental ownership. Unclassified/new services remain visible.
  const CERTIFICATE_IDS = new Set([
    'A001', 'A002', 'A003', 'A013', 'A014', 'A015', 'A016',
    'A017', 'A018', 'H004', 'R003', 'R004'
  ]);
  const HEALTH_IDS = new Set(['A008', 'A010', 'A011']);
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const ICON_PATHS = Object.freeze({
    certificate: [
      ['rect', {x: 6, y: 3, width: 12, height: 18, rx: 2}],
      ['path', {d: 'M9 8h6M9 12h6M9 16h4'}]
    ],
    vaccination: [
      ['path', {d: 'm14 3 7 7M17.5 6.5l-2 2M11 6l7 7M12.5 7.5 4 16l4 4 8.5-8.5M4 16l4 4M3 21l3-3M9 11l2 2M12 8l2 2'}]
    ],
    health: [
      ['path', {d: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z'}],
      ['path', {d: 'M3 12h5l2-4 3 8 2-4h6'}]
    ],
    family: [
      ['circle', {cx: 12, cy: 7, r: 4}],
      ['path', {d: 'M5 21v-3a7 7 0 0 1 14 0v3M9 17h6M12 14v6'}]
    ],
    about: [
      ['path', {d: 'M8 21V4h8v17M8 9H3v12h18V9h-5M11 7h2M11 11h2M11 15h2M11 21v-3h2v3M5 13v2M19 13v2'}]
    ],
    business: [
      ['path', {d: 'M8 3h8v3h4v15H4V6h4V3ZM8 6h8M12 10v7M8.5 13.5h7'}]
    ]
  });

  let entries = [];
  let selectedCategory = 'all';
  let page = 1;

  function textNode(tag, className, text = '') {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    return node;
  }

  function classify(task) {
    if (task.result_kind === 'guide') return task.result_category || 'business';
    const id = String(task.id || '');
    if (/^F\d{3}$/.test(id)) return 'about';
    if (CERTIFICATE_IDS.has(id)) return 'certificate';
    if (HEALTH_IDS.has(id)) return 'health';
    return 'business';
  }

  function categoryLabel(key) {
    return CATEGORIES.find((category) => category.key === key)?.label || '보건사업';
  }

  function icon(task, category) {
    const title = String(task.public_title || task.name || '');
    const kind = category === 'about' || category === 'certificate'
      ? category : /예방접종|백신/.test(title) ? 'vaccination'
        : /임신|임산부|산후|출산|영유아/.test(title) ? 'family' : category;
    const wrap = textNode('span', `rv-icon rv-icon-${kind}`);
    wrap.setAttribute('aria-hidden', 'true');
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.65');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('focusable', 'false');
    (ICON_PATHS[kind] || ICON_PATHS.business).forEach(([tag, attributes]) => {
      const shape = document.createElementNS(SVG_NS, tag);
      Object.entries(attributes).forEach(([name, value]) => {
        shape.setAttribute(name, String(value));
      });
      svg.appendChild(shape);
    });
    wrap.appendChild(svg);
    return wrap;
  }

  function highlightedTitle(value, query) {
    const node = textNode('span', 'rv-title result-name');
    const title = String(value || '업무 안내');
    const term = query.trim();
    if (!term) {
      node.textContent = title;
      return node;
    }
    // Literal substring matching keeps punctuation and user-supplied markup
    // harmless; no dynamic regular expression or HTML interpolation is used.
    let offset = 0;
    let found = title.toLocaleLowerCase('ko').indexOf(term.toLocaleLowerCase('ko'));
    while (found !== -1) {
      node.appendChild(document.createTextNode(title.slice(offset, found)));
      node.appendChild(textNode('span', 'rv-match', title.slice(found, found + term.length)));
      offset = found + term.length;
      found = title.toLocaleLowerCase('ko').indexOf(term.toLocaleLowerCase('ko'), offset);
    }
    node.appendChild(document.createTextNode(title.slice(offset)));
    return node;
  }

  function decorate(entry, query, recommended) {
    const {task, button, category} = entry;
    button.replaceChildren();
    button.classList.add('rv-result');
    button.classList.toggle('rv-recommended', recommended);
    button.dataset.resultCategory = category;
    if (recommended) button.appendChild(textNode('span', 'relevance-badge', '추천'));
    button.appendChild(icon(task, category));

    const copy = textNode('span', 'rv-copy');
    copy.appendChild(highlightedTitle(task.public_title || task.name, query));
    copy.appendChild(textNode('span', 'rv-summary',
      task.public_summary || task.route || '업무 내용과 방문 장소를 확인해 보세요.'));
    const meta = textNode('span', 'rv-meta');
    const location = task.show_map === false ? ''
      : [task.floor, task.room || task.place].filter(Boolean).join(' ');
    const parts = [categoryLabel(category), task.department, location, ...(task.result_meta || [])].filter(Boolean);
    parts.forEach((part, index) => {
      if (index) {
        const separator = textNode('span', 'rv-meta-separator', '›');
        separator.setAttribute('aria-hidden', 'true');
        meta.appendChild(separator);
      }
      meta.appendChild(textNode('span', 'rv-meta-item', part));
    });
    copy.appendChild(meta);
    button.appendChild(copy);
    const arrow = textNode('span', 'rv-arrow', '›');
    arrow.setAttribute('aria-hidden', 'true');
    button.appendChild(arrow);
    button.appendChild(textNode('span', 'sr-only', task.result_kind === 'guide' ? '이용 안내 자세히 보기' : '위치와 상세정보 보기'));
  }

  function updateCount(filteredCount) {
    count.replaceChildren(document.createTextNode('검색 결과 '));
    count.appendChild(textNode('strong', 'rv-count-number', String(entries.length)));
    count.appendChild(document.createTextNode('건'));
    if (selectedCategory !== 'all') {
      count.appendChild(textNode('span', 'rv-filtered-count',
        ` · ${categoryLabel(selectedCategory)} ${filteredCount}건`));
    }
  }

  function pageButton(label, target, options = {}) {
    const button = textNode('button', 'rv-page-button', label);
    button.type = 'button';
    button.dataset.page = String(target);
    button.disabled = Boolean(options.disabled);
    button.setAttribute('aria-controls', 'results');
    button.setAttribute('aria-label', options.label || `${target}페이지`);
    if (target === page && !options.label) button.setAttribute('aria-current', 'page');
    button.addEventListener('click', () => {
      page = target;
      updateView(true);
      pagination.querySelector('[aria-current="page"]')?.focus({preventScroll: true});
    });
    return button;
  }

  function renderPagination(totalPages) {
    pagination.replaceChildren();
    pagination.hidden = totalPages <= 1;
    if (totalPages <= 1) return;
    pagination.appendChild(pageButton('‹', page - 1, {
      label: '이전 페이지', disabled: page === 1
    }));
    const shown = new Set([1, totalPages, page - 1, page, page + 1]);
    let previous = 0;
    [...shown].filter((number) => number >= 1 && number <= totalPages)
      .sort((left, right) => left - right).forEach((number) => {
        if (previous && number - previous > 1) {
          const gap = textNode('span', 'rv-page-gap', '…');
          gap.setAttribute('aria-hidden', 'true');
          pagination.appendChild(gap);
        }
        pagination.appendChild(pageButton(String(number), number));
        previous = number;
      });
    pagination.appendChild(pageButton('›', page + 1, {
      label: '다음 페이지', disabled: page === totalPages
    }));
  }

  function updateView(announce = false) {
    const filtered = entries.filter((entry) => selectedCategory === 'all'
      || entry.category === selectedCategory);
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    page = Math.min(Math.max(page, 1), totalPages);
    const start = (page - 1) * PAGE_SIZE;
    const shown = new Set(filtered.slice(start, start + PAGE_SIZE));
    entries.forEach((entry) => { entry.button.hidden = !shown.has(entry); });
    filters.querySelectorAll('button').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.category === selectedCategory));
    });
    updateCount(filtered.length);
    renderPagination(totalPages);
    if (announce && status) {
      status.textContent = `${categoryLabel(selectedCategory)} ${filtered.length}건 · `
        + `${page}/${totalPages}페이지 · ${Math.min(start + 1, filtered.length)}–`
        + `${Math.min(start + PAGE_SIZE, filtered.length)}번째 안내 표시`;
    }
  }

  function renderFilters() {
    filters.replaceChildren();
    CATEGORIES.forEach(({key, label}) => {
      const size = key === 'all' ? entries.length
        : entries.filter((entry) => entry.category === key).length;
      const button = textNode('button', 'rv-filter', `${label} (${size})`);
      button.type = 'button';
      button.dataset.category = key;
      button.disabled = size === 0;
      button.setAttribute('aria-controls', 'results');
      button.setAttribute('aria-pressed', String(key === selectedCategory));
      button.addEventListener('click', () => {
        selectedCategory = key;
        page = 1;
        updateView(true);
      });
      filters.appendChild(button);
    });
  }

  function reset() {
    entries = [];
    selectedCategory = 'all';
    page = 1;
    filters.replaceChildren();
    count.replaceChildren();
    pagination.replaceChildren();
    filters.hidden = true;
    count.hidden = true;
    pagination.hidden = true;
    if (extras) extras.hidden = true;
  }

  function render(items) {
    reset();
    if (!Array.isArray(items) || !items.length) return;
    const buttons = [...results.querySelectorAll('.result-card')];
    // Defensive identity check: never decorate a stale/mismatched render.
    if (buttons.length !== items.length || buttons.some((button, index) =>
      button.dataset.taskId !== String(items[index].id))) return;
    const query = input.value.trim();
    const isSearch = Boolean(query && heading.textContent.includes('검색 결과'));
    if (isSearch) {
      heading.replaceChildren(textNode('span', 'rv-heading-query', `“${query}”`),
        document.createTextNode(' 검색 결과'));
    }
    entries = items.map((task, index) => ({task, button: buttons[index], category: classify(task)}));
    entries.forEach((entry, index) => decorate(entry, isSearch ? query : '', isSearch && index === 0 && !entry.task.is_archived));
    filters.hidden = false;
    count.hidden = false;
    if (extras) extras.hidden = false;
    renderFilters();
    updateView();
  }

  const helpDialog = byId('results-help-dialog');
  let helpTrigger = null;
  document.querySelectorAll('[data-results-help]').forEach((button) => {
    button.addEventListener('click', () => {
      helpTrigger = button;
      if (helpDialog && !helpDialog.open) helpDialog.showModal();
    });
  });
  byId('close-results-help')?.addEventListener('click', () => helpDialog?.close());
  helpDialog?.addEventListener('click', (event) => {
    if (event.target !== helpDialog) return;
    const box = helpDialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right
        || event.clientY < box.top || event.clientY > box.bottom) helpDialog.close();
  });
  helpDialog?.addEventListener('close', () => {
    if (helpTrigger?.isConnected) helpTrigger.focus({preventScroll: true});
    helpTrigger = null;
  });
  window.ResultsView = Object.freeze({render, reset});
})();
