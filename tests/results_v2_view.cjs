'use strict';

// Presentation-only VM checks: public JSON and source files, no HTTP or DB.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'public/js/results-v2.js'), 'utf8');
const tasks = JSON.parse(fs.readFileSync(path.join(root, 'data/deployment_catalog.json'), 'utf8')).tasks;
const cases = [];

class Node {
  constructor(tag = 'div', text = '') {
    Object.assign(this, {tagName: tag, children: [], ownText: text, attrs: {},
      dataset: {}, listeners: {}, hidden: false, disabled: false, value: '', className: '',
      isConnected: true, open: false});
    this.classList = {
      contains: (name) => this.className.split(/\s+/).includes(name),
      add: (...names) => { this.className = [...new Set([...this.className.split(/\s+/), ...names])].filter(Boolean).join(' '); },
      toggle: (name, enabled) => {
        const present = this.classList.contains(name);
        if (enabled === undefined) enabled = !present;
        if (enabled) this.classList.add(name);
        else this.className = this.className.split(/\s+/).filter((item) => item !== name).join(' ');
      }
    };
  }
  set textContent(text) { this.ownText = String(text); this.children = []; }
  get textContent() { return this.ownText + this.children.map((child) => child.textContent).join(''); }
  set innerHTML(_) { throw new Error('Unsafe HTML interpolation is forbidden'); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; this.ownText = ''; }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  getAttribute(key) { return this.attrs[key] ?? null; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  click() { if (!this.disabled) for (const listener of this.listeners.click || []) listener({target: this}); }
  emit(type, extra = {}) { for (const listener of this.listeners[type] || []) listener({target: this, ...extra}); }
  showModal() { this.open = true; }
  close() { this.open = false; this.emit('close'); }
  getBoundingClientRect() { return {left: 10, right: 90, top: 10, bottom: 90}; }
  focus() { this.focused = true; }
  matches(selector) {
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    const attr = selector.match(/^\[([^=\]]+)="([^"]*)"\]$/);
    if (attr) return this.getAttribute(attr[1]) === attr[2];
    return this.tagName === selector;
  }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => [
      ...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function harness({enabled = true, missing = ''} = {}) {
  const elements = Object.fromEntries(['results', 'results-filters', 'results-count',
    'results-pagination', 'results-extras', 'results-heading', 'status', 'query',
    'results-help-dialog', 'close-results-help']
    .filter((id) => id !== missing).map((id) => [id, new Node()]));
  const body = new Node('body');
  const helpButton = new Node('button');
  if (enabled) body.className = 'home-v2 results-v2';
  const document = {
    body, getElementById: (id) => elements[id],
    querySelectorAll: (selector) => selector === '[data-results-help]' ? [helpButton] : [],
    createElement: (tag) => new Node(tag),
    createElementNS: (_namespace, tag) => new Node(tag),
    createTextNode: (text) => new Node('#text', text)
  };
  const context = {document, window: {}, Intl};
  vm.runInNewContext(source, context, {filename: 'results-v2.js'});
  let selected = [];
  function render(items = tasks, {query = '', title = '전체 업무 안내'} = {}) {
    elements.query.value = query;
    elements['results-heading'].textContent = title;
    selected = [];
    const buttons = items.map((task) => {
      const button = new Node('button');
      button.className = 'result-card';
      button.dataset.taskId = String(task.id);
      button.setAttribute('aria-controls', 'detail-dialog');
      button.setAttribute('aria-haspopup', 'dialog');
      button.addEventListener('click', () => selected.push(task.id));
      return button;
    });
    elements.results.replaceChildren(...buttons);
    context.window.ResultsView.render(items);
    return buttons;
  }
  const filter = (key) => elements['results-filters'].children.find((button) => button.dataset.category === key);
  const page = (number) => elements['results-pagination'].children.find((button) =>
    button.dataset.page === String(number) && button.getAttribute('aria-label') === `${number}페이지`);
  const visible = () => elements.results.children.filter((button) => !button.hidden);
  return {elements, context, render, filter, page, visible, helpButton, selected: () => selected};
}

function test(name, run) { run(); cases.push(name); }

test('legacy HOME is not modified', () => {
  assert.equal(harness({enabled: false}).context.window.ResultsView, undefined);
});
test('missing presentation element fails closed', () => {
  assert.equal(harness({missing: 'results-filters'}).context.window.ResultsView, undefined);
});
test('all 63 real tasks produce mutually exclusive accurate tab counts', () => {
  const h = harness(); h.render();
  const expected = {all: 63, business: 25, certificate: 12, health: 3, news: 0, about: 23};
  for (const [key, size] of Object.entries(expected)) assert.ok(h.filter(key).textContent.endsWith(`(${size})`));
  assert.equal(Object.values(expected).slice(1).reduce((sum, value) => sum + value, 0), tasks.length);
});
test('first page contains four cards and catalog has sixteen pages', () => {
  const h = harness(); h.render();
  assert.equal(h.visible().length, 4);
  assert.equal(h.page(1).getAttribute('aria-current'), 'page');
  assert.ok(h.page(16));
});
test('zero-data news filter is explicitly disabled', () => {
  const h = harness(); h.render();
  assert.equal(h.filter('news').disabled, true);
  h.filter('news').click();
  assert.equal(h.filter('all').getAttribute('aria-pressed'), 'true');
  assert.equal(h.visible().length, 4);
});
test('facility filter has six pages and final three correct facilities', () => {
  const h = harness(); h.render(); h.filter('about').click(); h.page(6).click();
  assert.equal(h.visible().length, 3);
  assert.ok(h.visible().every((button) => button.dataset.taskId.startsWith('F')));
  assert.ok(h.elements['results-count'].textContent.includes('보건소 소개 23건'));
});
test('certificate filter has twelve records over three pages', () => {
  const h = harness(); h.render(); h.filter('certificate').click(); h.page(3).click();
  assert.equal(h.visible().length, 4);
  assert.ok(h.visible().every((button) => button.dataset.resultCategory === 'certificate'));
});
test('health filter has three records and hides unnecessary pagination', () => {
  const h = harness(); h.render(); h.filter('health').click();
  assert.equal(h.visible().length, 3);
  assert.equal(h.elements['results-pagination'].hidden, true);
});
test('changing category resets page and aria selection', () => {
  const h = harness(); h.render(); h.page(16).click(); h.filter('business').click();
  assert.equal(h.page(1).getAttribute('aria-current'), 'page');
  assert.equal(h.filter('business').getAttribute('aria-pressed'), 'true');
  assert.equal(h.filter('all').getAttribute('aria-pressed'), 'false');
});
test('page switch preserves result buttons and their registered events', () => {
  const h = harness(); const buttons = h.render(); h.page(16).click();
  assert.equal(h.visible().length, 3);
  assert.equal(h.visible()[0], buttons[60]);
  h.visible()[0].click(); assert.deepEqual(h.selected(), [tasks[60].id]);
  assert.equal(buttons[60].getAttribute('aria-controls'), 'detail-dialog');
  assert.equal(buttons[60].getAttribute('aria-haspopup'), 'dialog');
});
test('page switch restores keyboard focus and announces range', () => {
  const h = harness(); h.render(); h.page(2).click();
  assert.equal(h.page(2).focused, true);
  assert.ok(h.elements.status.textContent.includes('5–8번째'));
});
test('search query and public title are text even when containing HTML', () => {
  const h = harness(); const query = '<img src=x onerror=alert(1)>';
  h.render([{id: 'X001', name: query, public_summary: '<script>alert(2)</script>'}], {query, title: '검색 결과'});
  assert.equal(h.elements.results.querySelectorAll('img').length, 0);
  assert.equal(h.elements.results.querySelectorAll('script').length, 0);
  assert.equal(h.elements['results-heading'].textContent, `“${query}” 검색 결과`);
  assert.equal(h.elements.results.querySelector('.rv-match').textContent, query);
});
test('query punctuation uses literal substring matching', () => {
  const h = harness(); h.render([{id: 'X001', name: '검사 [안내]+ ([안내]+)'}], {query: '[안내]+', title: '검색 결과'});
  assert.equal(h.elements.results.querySelectorAll('.rv-match').length, 2);
});
test('only the first ranked search card receives recommendation', () => {
  const h = harness(); h.render(tasks.slice(0, 7), {query: '접수', title: '접수 검색 결과'});
  assert.equal(h.elements.results.querySelectorAll('.relevance-badge').length, 1);
  assert.equal(h.elements.results.children[0].classList.contains('rv-recommended'), true);
});
test('directory and category listings never claim a recommendation', () => {
  const h = harness(); h.render(tasks, {query: 'stale query', title: '전체 업무 안내'});
  assert.equal(h.elements.results.querySelectorAll('.relevance-badge').length, 0);
  assert.equal(h.elements.results.querySelectorAll('.rv-match').length, 0);
});
test('withheld-map record does not display unverified location metadata', () => {
  const h = harness(); h.render([{id: 'M002', name: '지원', department: '담당 부서',
    floor: '9층', room: '미확인장소', show_map: false}]);
  assert.equal(h.elements.results.querySelector('.rv-meta').textContent.includes('미확인장소'), false);
});
test('all dynamic metadata is text and existing public summary wins', () => {
  const h = harness(); h.render([{id: 'X001', name: '제목', public_summary: '공개 설명',
    route: '대체 안내', department: '<iframe>', floor: '1층', place: '<img>'}]);
  assert.equal(h.elements.results.querySelector('.rv-summary').textContent, '공개 설명');
  assert.equal(h.elements.results.querySelectorAll('iframe').length, 0);
  assert.equal(h.elements.results.querySelectorAll('img').length, 0);
});
test('reset clears counts pagination filters and related panel', () => {
  const h = harness(); h.render(); h.context.window.ResultsView.reset();
  for (const id of ['results-count', 'results-filters', 'results-pagination', 'results-extras']) {
    assert.equal(h.elements[id].hidden, true);
  }
  assert.equal(h.elements['results-count'].textContent, '');
});
test('new search resets previous category and page state', () => {
  const h = harness(); h.render(); h.filter('about').click(); h.page(6).click();
  h.render(tasks.slice(0, 8), {query: '접수', title: '검색 결과'});
  assert.equal(h.filter('all').getAttribute('aria-pressed'), 'true');
  assert.equal(h.page(1).getAttribute('aria-current'), 'page');
  assert.equal(h.visible().length, 4);
});
test('empty and invalid result input hides controls without throwing', () => {
  const h = harness(); h.render([]);
  h.context.window.ResultsView.render(null);
  assert.equal(h.elements['results-count'].hidden, true);
  assert.equal(h.elements['results-extras'].hidden, true);
});
test('stale task identities fail closed without replacing an active button', () => {
  const h = harness(); const buttons = h.render(tasks.slice(0, 1));
  buttons[0].dataset.taskId = 'DIFFERENT';
  h.context.window.ResultsView.render(tasks.slice(0, 1));
  assert.equal(h.elements.results.children[0], buttons[0]);
  assert.equal(h.elements['results-filters'].hidden, true);
});
test('mismatched result length does not partially decorate', () => {
  const h = harness(); h.render(tasks.slice(0, 1));
  h.context.window.ResultsView.render(tasks.slice(0, 2));
  assert.equal(h.elements['results-count'].hidden, true);
});
test('new service IDs remain visible instead of disappearing from all tabs', () => {
  const h = harness(); h.render([{id: 'NEW001', name: '신규 업무'}]);
  assert.equal(h.filter('business').textContent, '보건사업 (1)');
  assert.equal(h.visible()[0].dataset.taskId, 'NEW001');
});
test('total reflects data rather than the 234-record reference image', () => {
  const h = harness(); h.render(tasks.slice(0, 6));
  assert.equal(h.elements['results-count'].querySelector('strong').textContent, '6');
  assert.equal(h.elements['results-count'].textContent.includes('234'), false);
});
test('help dialog opens and close button restores trigger focus', () => {
  const h = harness(); h.helpButton.click();
  assert.equal(h.elements['results-help-dialog'].open, true);
  h.elements['close-results-help'].click();
  assert.equal(h.elements['results-help-dialog'].open, false);
  assert.equal(h.helpButton.focused, true);
});
test('help dialog content clicks do not dismiss the dialog', () => {
  const h = harness(); h.helpButton.click();
  h.elements['results-help-dialog'].emit('click', {clientX: 50, clientY: 50});
  assert.equal(h.elements['results-help-dialog'].open, true);
});
test('help dialog backdrop click dismisses the dialog', () => {
  const h = harness(); h.helpButton.click();
  h.elements['results-help-dialog'].emit('click', {clientX: 5, clientY: 5});
  assert.equal(h.elements['results-help-dialog'].open, false);
});

test('guidance and its two real tasks share one truthful result count', () => {
  const h = harness();
  const guide = {id:'guide-V005',result_kind:'guide',public_title:'65세 이상 폐렴구균 예방접종',public_summary:'무료 예방접종',department:'예방접종 안내',show_map:false};
  const selected = [guide,...tasks.filter(t=>['M009','F109'].includes(t.id))];
  h.render(selected,{query:'폐렴',title:'검색 결과'});
  assert.equal(h.visible().length,3);
  assert.equal(h.elements['results-count'].textContent,'검색 결과 3건');
  assert.equal(h.filter('business').textContent,'보건사업 (2)');
  assert.equal(h.filter('about').textContent,'보건소 소개 (1)');
  assert.ok(h.elements['results-heading'].querySelector('.rv-heading-query'));
});
test('guide-only queries use the existing card renderer and show fees safely', () => {
  const h = harness();
  h.render([{id:'guide-E008',result_kind:'guide',public_title:'갑상선 검사',show_map:false,
    result_meta:['10,000원','결과·처리 1주','<script>']}],{query:'갑상선',title:'검색 결과'});
  assert.equal(h.visible().length,1);
  const card=h.visible()[0];
  assert.ok(card.classList.contains('rv-result'));
  assert.ok(card.querySelector('.rv-meta').textContent.includes('10,000원'));
  assert.ok(card.textContent.includes('이용 안내 자세히 보기'));
  assert.equal(card.querySelectorAll('script').length,0);
});
test('expired guidance is never styled as a current recommendation', () => {
  const h = harness();
  h.render([{id:'guide-old',result_kind:'guide',is_archived:true,public_title:'지난 안내'}],{query:'지난',title:'검색 결과'});
  assert.equal(h.elements.results.querySelectorAll('.relevance-badge').length,0);
});
process.stdout.write(JSON.stringify({passed: cases.length, failed: 0, cases, realSmsSent: 0}));
