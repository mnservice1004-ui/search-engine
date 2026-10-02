'use strict';

// Synthetic DOM and deferred promises only. No HTTP, DB, clipboard, printer,
// or SMS service is contacted by this executable contract suite.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../public/js/detail-v2.js'), 'utf8');
const appSource = fs.readFileSync(path.resolve(__dirname, '../public/js/app.js'), 'utf8');
const actualDetailSource = appSource.slice(appSource.indexOf('function addDetailRow('), appSource.indexOf('function renderResults('));
const catalog = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../data/deployment_catalog.json'), 'utf8')).tasks;
const guidance = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../data/public_guidance.json'), 'utf8')).tasks;
const guidanceById = new Map(guidance.map((row) => [row.task_id, row]));
const cases = [];

class Node {
  constructor(tag = 'div', text = '') {
    Object.assign(this, {tagName: tag, children: [], ownText: text, attrs: {}, dataset: {},
      listeners: {}, hidden: false, disabled: false, value: '', className: '', id: '',
      parent: null, open: false, clientWidth: 700, scrollLeft: 0, scrollTop: 0,
      naturalWidth: 2560, naturalHeight: 1709, complete: true, isConnected: true});
    this.style = {setProperty(name, value) { this[name] = String(value); }, getPropertyValue(name) { return this[name] || ''; }, removeProperty(name) {
      delete this[name.startsWith('--') ? name : name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())];
    }};
    this.classList = {
      contains: (name) => this.className.split(/\s+/).includes(name),
      add: (...names) => { this.className = [...new Set([...this.className.split(/\s+/), ...names])].filter(Boolean).join(' '); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter((name) => !names.includes(name)).join(' '); },
      toggle: (name, on = !this.classList.contains(name)) => {
        if (on) this.classList.add(name); else this.classList.remove(name);
      }
    };
  }
  set textContent(value) { this.replaceChildren(); this.ownText = String(value); }
  get textContent() { return this.ownText + this.children.map((node) => node.textContent).join(''); }
  set innerHTML(_) { throw new Error('HTML injection is forbidden'); }
  appendChild(node) {
    if (node.parent) node.parent.children = node.parent.children.filter((child) => child !== node);
    node.parent = this; this.children.push(node); return node;
  }
  append(...nodes) { nodes.forEach((node) => this.appendChild(node)); }
  prepend(node) { this.appendChild(node); this.children = [node, ...this.children.filter((child) => child !== node)]; }
  replaceChildren(...nodes) {
    this.children.forEach((node) => { node.parent = null; }); this.children = []; this.ownText = '';
    this.append(...nodes);
  }
  setAttribute(key, value) {
    this.attrs[key] = String(value);
    if (key === 'class') this.className = String(value);
  }
  getAttribute(key) { return this.attrs[key] ?? null; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  emit(type, values = {}) { return (this.listeners[type] || []).map((fn) => fn({target: this, ...values})); }
  click() { return this.disabled ? Promise.resolve() : Promise.all(this.emit('click')); }
  showModal() { this.open = true; this.openCount = (this.openCount || 0) + 1; }
  close() { this.open = false; this.emit('close'); }
  focus() { this.focused = true; }
  select() { this.selected = true; }
  getBoundingClientRect() {
    const height = this.clientHeight ?? this.clientWidth * 2000 / 2560;
    return {left: 0, top: 0, width: this.clientWidth, height, right: this.clientWidth, bottom: height};
  }
  matches(selector) {
    if (selector.includes(' > ')) {
      const [parent, child] = selector.split(' > ');
      return this.matches(child) && Boolean(this.parent?.matches(parent));
    }
    if (selector[0] === '.') return this.classList.contains(selector.slice(1));
    if (selector[0] === '#') return this.id === selector.slice(1);
    return this.tagName === selector;
  }
  querySelectorAll(selector) {
    return this.children.flatMap((node) => [...(node.matches(selector) ? [node] : []), ...node.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function deepFreeze(value) {
  Object.values(value).filter((item) => item && typeof item === 'object').forEach(deepFreeze);
  return Object.freeze(value);
}

function harness({url = 'https://example.test/?q=private&recipient=01000000000#old', missingViewport = false} = {}) {
  const names = ['detail-dialog', 'detail', 'detail-dialog-title', 'detail-context', 'detail-subtitle',
    'detail-map-label', 'detail-map-status', 'detail-zoom-reset', 'detail-zoom-in', 'detail-zoom-out',
    'detail-map-expand', 'floor-image', 'map-route', 'map-route-line', 'map-marker', 'query', 'search-workspace', 'results-heading', 'status'];
  const ids = Object.fromEntries(names.map((id) => {
    const element = new Node(); element.id = id; return [id, element];
  }));
  const body = new Node('body');
  const dialog = ids['detail-dialog']; dialog.className = 'detail-dialog detail-v2';
  const panel = new Node(); panel.className = 'map-panel';
  const viewport = new Node(); viewport.className = 'detail-map-viewport';
  const stage = new Node(); stage.className = 'map-stage';
  const legend = new Node(); legend.className = 'detail-map-legend';
  const location = new Node(); location.className = 'detail-location-pill'; location.append(new Node('span'));
  body.append(dialog);
  dialog.append(panel, ids.detail);
  panel.append(...(missingViewport ? [] : [viewport]), legend, location);
  viewport.append(stage); stage.append(ids['floor-image'], ids['map-route'], ids['map-marker']);
  ids['map-route'].append(ids['map-route-line']);
  ids['map-route-line'].setAttribute('d', 'M 68.59 89.82 L 68.59 50.03 L 66.80 50.03');
  const events = {document: {}, window: {}};
  const requests = [], writes = [], shown = [], resets = [], observers = [];
  let printCalls = 0, smsOpens = 0;
  const document = {
    body,
    getElementById: (id) => ids[id] || body.querySelector('#' + id),
    createElement: (tag) => new Node(tag),
    createElementNS: (_namespace, tag) => new Node(tag),
    addEventListener: (type, callback) => { (events.document[type] ||= []).push(callback); }
  };
  const window = {
    location: {href: url},
    history: {replaceState(_state, _title, location) {
      window.location.href = new URL(location, window.location.href).href;
    }},
    addEventListener: (type, callback) => { (events.window[type] ||= []).push(callback); },
    print() { printCalls++; }
  };
  const context = {window, document, URL, navigator: {clipboard: {writeText: async (text) => { writes.push(text); }}},
    smsBusy: false, state: {}, requestAnimationFrame(callback) { callback(); },
    getComputedStyle: (element) => ({height: element.id === 'map-marker' ? '84px' : '400px', paddingTop: '12px'}),
    MutationObserver: class { constructor(callback) { this.callback = callback; } observe(target) { observers.push({target, callback: this.callback}); } },
    ResizeObserver: class { constructor(callback) { this.callback = callback; } observe(target) { observers.push({target, callback: this.callback, resize: true}); } },
    getJson: (requestUrl) => new Promise((resolve, reject) => { requests.push({url: requestUrl, resolve, reject}); }),
    showDetail: (task) => { shown.push(task); render(task); },
    resetSearchView: (message) => { resets.push(message); }
  };
  vm.createContext(context);
  vm.runInContext(source, context, {filename: 'detail-v2.js'});
  function render(task, options = {}) {
    const rows = [
      ['어떤 업무인가요?', task.public_summary], ['누가 이용할 수 있나요?', task.eligibility],
      ['어디로 가나요?', task.route], ['무엇을 준비하나요?', task.documents], ['비용은 얼마인가요?', task.fee],
      ['언제 이용하나요?', task.operating_hours], ['어떻게 이용하나요?', task.visit_steps],
      ['추가 안내', !options.isLocationGuide && task.primary_action !== task.visit_steps ? task.primary_action : null],
      ['문의전화', options.primaryContact?.display_phone || options.primaryContact?.phone],
      ['꼭 알아두세요', task.public_caution]
    ];
    ids.detail.replaceChildren();
    rows.forEach(([label, text]) => {
      if (!text || options.isLocationGuide && ['어떤 업무인가요?', '누가 이용할 수 있나요?'].includes(label)) return;
      const row = new Node(); row.className = 'detail-row';
      row.append(new Node('strong', label), new Node('span', text)); ids.detail.append(row);
    });
    const sms = new Node('button', '이 안내를 문자메시지로 받기'); sms.className = 'contact-button';
    sms.addEventListener('click', () => { smsOpens++; }); ids.detail.append(sms);
    panel.hidden = task.show_map === false;
    ids['map-route'].classList.toggle('show', !panel.hidden);
    window.DetailView.render(task, options);
    return {sms};
  }
  let actualDetailLoaded = false;
  function renderActual(input) {
    if (!actualDetailLoaded) {
      context.detailEl = ids.detail;
      context.clearChildren = (element) => element.replaceChildren();
      context.createText = (tag, className, text) => { const result = new Node(tag, text || ''); result.className = className; return result; };
      context.openSmsDialog = () => { smsOpens++; };
      context.showMap = (value) => {
        panel.hidden = value.show_map === false;
        ids['map-route'].classList.toggle('show', !panel.hidden);
      };
      vm.runInContext(actualDetailSource, context, {filename: 'app-actual-detail.js'});
      actualDetailLoaded = true;
    }
    context.showDetail(input);
  }
  function emit(where, type) { return (events[where][type] || []).map((callback) => callback()); }
  return {context, ids, body, dialog, panel, viewport, stage, legend, render, renderActual, requests, writes, shown, resets, emit, observers,
    get: (id) => document.getElementById(id), smsOpens: () => smsOpens, printCalls: () => printCalls};
}

const task = (changes = {}) => deepFreeze({id: 'A001', name: '원래 이름', public_title: '등록된 업무 안내',
  public_summary: '검토된 요약 문장입니다.', department: '담당 과', team: '담당 팀', floor: '1층', room: '민원실',
  show_map: true, eligibility: '등록된 대상', route: '1층 민원실로 가세요.', documents: '등록된 준비물',
  fee: '등록된 비용', operating_hours: '등록된 운영시간', visit_steps: '먼저 접수하세요. 다음 절차를 확인하세요.',
  public_caution: '등록된 유의사항', ...changes});
const settle = () => new Promise((resolve) => setImmediate(resolve));
async function test(name, callback) { await callback(); cases.push(name); }

async function main() {
  await test('reviewed PDF phones and purposes appear in the actual detail renderer', () => {
    const data = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../data/deployment_catalog.json'), 'utf8'));
    const sourceData = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../data/source/dongtan_pdf_contacts_20260930.json'), 'utf8'));
    for (const record of sourceData.records) for (const link of record.links) {
      const raw = data.tasks.find((row) => row.id === link.task_id);
      const guide = guidanceById.get(raw.id);
      const contacts = data.contacts.filter((row) => row.task_id === raw.id).map((row) => ({
        phone: row.phone, display_phone: row.display_phone, purpose: row.label,
        role: row.contact_role, condition: row.condition_text, is_primary: Boolean(row.is_primary)
      }));
      const input = task({...raw, ...(guide || {}), public_title: guide?.public_title || null,
        contacts, primary_contact: contacts.find((row) => row.is_primary) || null});
      const h = harness(); h.renderActual(input);
      const phone = '031-5189-' + link.extension;
      assert.ok(h.ids.detail.textContent.includes(phone), raw.id + '/' + phone);
      assert.ok(h.ids.detail.textContent.includes(link.label), raw.id + '/' + link.label);
      const links = h.ids.detail.querySelectorAll('.contact-link');
      assert.equal(links.filter((node) => node.href === 'tel:' + phone.replace(/\D/g, '')).length, 1);
      if (!input.primary_contact) {
        assert.equal(h.ids.detail.querySelector('.detail-secondary-actions').children[0].title,
          '위 문의전화에서 필요한 업무의 번호를 선택해 주세요.');
      }
    }
  });
  await test('detail contact list is safe and duplicate primary is rendered once', () => {
    const contact = {phone: '031-555-1234', display_phone: '031-555-1234',
      purpose: '<img src=x>', is_primary: true};
    const input = task({primary_contact: contact, contacts: [contact, {...contact, is_primary: false}]});
    const h = harness(); h.renderActual(input);
    assert.equal(h.ids.detail.querySelectorAll('.contact-link').length, 1);
    assert.ok(h.ids.detail.textContent.includes('<img src=x>'));
    assert.equal(h.ids.detail.querySelectorAll('img').length, 0);
  });
  await test('legacy markup without viewport stays untouched', () => {
    assert.equal(harness({missingViewport: true}).context.window.DetailView, undefined);
  });
  await test('initialization does not call API SMS clipboard or printer', () => {
    const h = harness(); assert.equal(h.requests.length + h.writes.length + h.smsOpens() + h.printCalls(), 0);
  });
  await test('render uses exact registered title summary department and destination without mutating task', () => {
    const h = harness(), input = task(); const original = JSON.stringify(input); h.render(input);
    assert.equal(h.ids['detail-dialog-title'].textContent, input.public_title);
    assert.equal(h.ids['detail-subtitle'].textContent, input.public_summary);
    assert.equal(h.ids['detail-context'].textContent, input.department);
    assert.equal(h.ids['detail-map-label'].textContent, '1층 · 민원실');
    assert.equal(JSON.stringify(input), original);
    assert.deepEqual(h.ids.detail.querySelectorAll('.detail-row').map((row) => row.dataset.detailKind),
      ['location', 'hours', 'department', 'eligibility', 'documents', 'fee', 'steps', 'caution']);
  });
  for (const scenario of [
    {name: 'ordinary service', changes: {}, options: {}, subtitle: '검토된 요약 문장입니다.'},
    {name: 'location-only guide', changes: {id: 'F109'}, options: {isLocationGuide: true}, subtitle: '1층 민원실로 가세요.'},
    {name: 'service without summary', changes: {public_summary: null}, options: {}, subtitle: '등록된 방문 장소와 이용 안내를 확인해 주세요.'}
  ]) {
    await test(`${scenario.name} removes duplicate card intro but preserves header rows SMS and source data`, async () => {
      const h = harness(), input = task(scenario.changes), before = JSON.stringify(input);
      const {sms} = h.render(input, scenario.options);
      assert.equal(h.ids.detail.querySelectorAll('.detail-intro').length, 0);
      assert.equal(h.ids['detail-dialog-title'].textContent, input.public_title);
      assert.equal(h.ids['detail-subtitle'].textContent, scenario.subtitle);
      assert.equal(h.ids.detail.querySelector('.detail-service-title').textContent, input.public_title);
      const rows = new Map(h.ids.detail.querySelectorAll('.detail-row').map((row) => [row.dataset.detailKind, row]));
      for (const [kind, field] of [['location', 'route'], ['hours', 'operating_hours'],
        ['documents', 'documents'], ['fee', 'fee'], ['steps', 'visit_steps'], ['caution', 'public_caution']]) {
        assert.equal(rows.get(kind)?.querySelector('span').textContent, input[field], kind);
      }
      assert.equal(rows.has('eligibility'), !scenario.options.isLocationGuide);
      assert.equal(h.ids.detail.querySelector('.contact-button'), sms);
      assert.equal(h.smsOpens() + h.requests.length + h.writes.length + h.printCalls(), 0);
      await sms.click(); assert.equal(h.smsOpens(), 1);
      assert.equal(h.requests.length + h.writes.length + h.printCalls(), 0);
      assert.equal(JSON.stringify(input), before);
    });
  }
  await test('text markup is literal not HTML and original SMS button identity listener are preserved', async () => {
    const h = harness(), title = '<img src=x onerror=alert(1)>', input = task({public_title: title, public_summary: '<script>boom</script>'});
    const rendered = h.render(input);
    assert.equal(h.ids['detail-dialog-title'].textContent, title);
    assert.equal(h.ids.detail.querySelectorAll('script').length + h.ids.detail.querySelectorAll('img').length, 0);
    assert.equal(h.ids.detail.querySelector('.contact-button'), rendered.sms);
    assert.equal(h.smsOpens(), 0); await rendered.sms.click(); assert.equal(h.smsOpens(), 1);
  });
  await test('location-only guides omit service eligibility but preserve cautions separately', () => {
    const h = harness(), input = task(); h.render(input, {isLocationGuide: true});
    assert.equal(h.ids['detail-subtitle'].textContent, input.route);
    assert.equal(h.ids.detail.querySelector('.detail-service-tag').textContent, '위치 안내');
    const kinds = h.ids.detail.querySelectorAll('.detail-row').map((row) => row.dataset.detailKind);
    assert.ok(!kinds.includes('eligibility') && kinds.includes('caution'));
    assert.equal(h.ids.detail.querySelectorAll('.detail-row').find((row) => row.dataset.detailKind === 'caution').querySelector('span').textContent, input.public_caution);
  });
  await test('punctuation does not create numbered instructions for unreviewed steps', () => {
    const h = harness(); const texts = [...h.context.window.DetailView.splitSteps('접수 1.5번. 다음 단계!\n문의하세요?')];
    assert.deepEqual(texts, ['접수 1.5번. 다음 단계!', '문의하세요?']);
    h.render(task()); assert.equal(h.ids.detail.querySelectorAll('li').length, 0);
    const steps = h.ids.detail.querySelectorAll('.detail-row').find((row) => row.dataset.detailKind === 'steps');
    assert.equal(steps.querySelector('span').textContent, task().visit_steps);
    assert.equal(steps.querySelector('strong').textContent, '이용 절차');
  });
  await test('all 63 actual catalog items separate directions cautions and extra guidance without source mutation', () => {
    const h = harness(); let locations = 0, others = 0, unregistered = 0;
    for (const raw of catalog) {
      const reviewed = guidanceById.get(raw.id);
      const location = reviewed?.location || {};
      const input = deepFreeze({...raw, ...reviewed, id: raw.id, route: location.route_text || raw.route,
        floor: location.floor || raw.floor, room: location.room || raw.place,
        show_map: location.show_map !== false});
      const before = JSON.stringify(input); h.renderActual(input);
      const isLocation = h.context.isLocationOnlyGuide(input);
      assert.equal(h.ids.detail.querySelectorAll('.detail-intro').length, 0, raw.id);
      assert.equal(h.ids['detail-subtitle'].textContent,
        (isLocation ? input.route : input.public_summary) || '등록된 방문 장소와 이용 안내를 확인해 주세요.', raw.id);
      assert.equal(Boolean(h.ids.detail.querySelector('.contact-button')), Boolean(reviewed), raw.id);
      if (isLocation) locations++; else others++;
      const rows = new Map(h.ids.detail.querySelectorAll('.detail-row').map((row) => [row.dataset.detailKind, row]));
      if (!reviewed) {
        unregistered++;
        assert.ok(!rows.has('steps') && !rows.has('caution') && !rows.has('note'), raw.id);
        assert.equal(h.ids.detail.querySelectorAll('ol').length, 0);
      } else {
        if (reviewed.visit_steps) {
          const steps = rows.get('steps'); assert.ok(steps, raw.id);
          assert.equal(steps.querySelector('strong').textContent, isLocation ? '찾아가는 방법' : '이용 절차');
          if (raw.id === 'F109') {
            assert.deepEqual(steps.querySelectorAll('li').map((item) => item.textContent), reviewed.visit_steps.split('\n'));
          } else {
            assert.equal(steps.querySelector('span').textContent, reviewed.visit_steps, raw.id);
            assert.equal(steps.querySelectorAll('ol').length, 0, raw.id);
          }
        }
        if (reviewed.public_caution) {
          assert.equal(rows.get('caution')?.querySelector('span').textContent, reviewed.public_caution, raw.id);
          assert.equal(rows.get('caution').querySelectorAll('ol').length, 0, raw.id);
        }
        const extra = !isLocation && reviewed.primary_action && reviewed.primary_action !== reviewed.visit_steps;
        if (extra) {
          assert.equal(rows.get('note')?.querySelector('strong').textContent, '추가 안내');
          assert.equal(rows.get('note').querySelector('span').textContent, reviewed.primary_action, raw.id);
          assert.equal(rows.get('note').querySelectorAll('ol').length, 0, raw.id);
        } else assert.ok(!rows.has('note'), raw.id);
      }
      for (const list of h.ids.detail.querySelectorAll('ol')) {
        assert.equal(raw.id, 'F109');
        assert.ok(!reviewed.public_caution || !list.textContent.includes(reviewed.public_caution));
      }
      assert.equal(JSON.stringify(input), before, raw.id);
    }
    assert.equal(locations, 19); assert.equal(others, 44); assert.equal(unregistered, 13);
    assert.equal(h.smsOpens() + h.requests.length + h.writes.length + h.printCalls(), 0);
  });
  await test('F109 has exactly the two reviewed route steps with previsit reservation caveats outside the list', () => {
    const h = harness(); const reviewed = guidanceById.get('F109');
    h.renderActual(deepFreeze({...reviewed, id: 'F109', floor: '1층', room: '모자보건실 예방접종실', route: reviewed.location.route_text}));
    const lists = h.ids.detail.querySelectorAll('ol'); assert.equal(lists.length, 1);
    assert.deepEqual(lists[0].querySelectorAll('li').map((row) => row.textContent), [
      '보건소 1층 정문으로 들어오세요.', '지도에 표시된 경로를 따라 모자보건실·예방접종실로 이동하세요.'
    ]);
    assert.ok(!lists[0].textContent.includes('방문 전에') && !lists[0].textContent.includes('예약'));
    const caution = h.ids.detail.querySelectorAll('.detail-row').find((row) => row.dataset.detailKind === 'caution');
    assert.equal(caution.querySelector('span').textContent, reviewed.public_caution);
    assert.equal(caution.querySelectorAll('li').length, 0);
  });
  await test('unreviewed multiline directions remain text and duplicate extra guidance is omitted', () => {
    const h = harness(); const steps = '안내 문장입니다. 주의 문장인가요?\n아직 순서가 검토되지 않았습니다.';
    h.renderActual(task({visit_steps: steps, primary_action: steps}));
    assert.equal(h.ids.detail.querySelectorAll('ol').length, 0);
    const rows = new Map(h.ids.detail.querySelectorAll('.detail-row').map((row) => [row.dataset.detailKind, row]));
    assert.equal(rows.get('steps').querySelector('span').textContent, steps);
    assert.equal(rows.has('note'), false);
    assert.equal(rows.get('caution').querySelector('span').textContent, task().public_caution);
  });
  await test('withheld map stays hidden with disabled map controls and no route claim', () => {
    const h = harness(); h.render(task({show_map: false}));
    assert.equal(h.panel.hidden, true); assert.equal(h.legend.hidden, true);
    assert.equal(h.ids['detail-map-status'].textContent, '');
    for (const id of ['detail-zoom-in', 'detail-zoom-out', 'detail-zoom-reset', 'detail-map-expand']) assert.equal(h.ids[id].disabled, true);
  });
  await test('unloaded map disables controls and map load restores verified route status', () => {
    const h = harness(); h.ids['floor-image'].complete = false; h.render(task());
    assert.equal(h.ids['detail-zoom-in'].disabled, true);
    h.ids['floor-image'].complete = true; h.ids['floor-image'].emit('load');
    assert.equal(h.ids['detail-zoom-in'].disabled, false);
    assert.match(h.ids['detail-map-status'].textContent, /1층 정문/);
    assert.match(h.ids['detail-map-status'].textContent, /실시간 현재 위치는 표시하지 않습니다/);
  });
  await test('route unavailable does not claim a connected route', () => {
    const h = harness(); h.render(task()); h.ids['map-route'].classList.remove('show');
    h.observers.find((entry) => entry.target === h.ids['map-route']).callback();
    assert.equal(h.legend.hidden, true); assert.match(h.ids['detail-map-status'].textContent, /연결 경로가 없는 경우/);
  });
  await test('start marker reads existing route first point without changing verified path', () => {
    const h = harness(); const original = h.ids['map-route-line'].getAttribute('d'); h.render(task());
    const start = h.get('detail-route-start');
    assert.equal(start.getAttribute('cx'), '68.59'); assert.equal(start.getAttribute('cy'), '89.82');
    assert.equal(h.ids['map-route-line'].getAttribute('d'), original);
    h.context.window.DetailView.resetZoom(175);
    assert.equal(h.ids['map-route-line'].getAttribute('d'), original);
    assert.equal(start.getAttribute('cx'), '68.59');
  });
  await test('print marker anchors use source image fractions for every floor regardless of zoom', () => {
    for (const height of [1709, 2000, 1933]) {
      const h = harness(); h.ids['floor-image'].naturalHeight = height;
      h.context.visibleMarkerPoint = deepFreeze({label_bbox: {left: 1024, width: 256, top: height / 4, height: 40}});
      h.render(task());
      assert.equal(Number(h.stage.style.getPropertyValue('--detail-marker-x')), 0.45);
      assert.equal(Number(h.stage.style.getPropertyValue('--detail-marker-y')), 0.25);
      h.context.window.DetailView.resetZoom(175); h.dialog.open = true; h.emit('window', 'beforeprint');
      assert.equal(Number(h.stage.style.getPropertyValue('--detail-marker-x')), 0.45);
      assert.equal(Number(h.stage.style.getPropertyValue('--detail-marker-y')), 0.25);
      h.emit('window', 'afterprint'); assert.equal(h.stage.style.width, '175%');
    }
  });
  await test('top-edge dance clearance stays inside map viewport and recalculates on image resize', () => {
    const h = harness(); h.ids['floor-image'].naturalHeight = 1933; h.ids['floor-image'].clientHeight = 300;
    h.context.visibleMarkerPoint = deepFreeze({label_bbox: {left: 1000, width: 120, top: 100, height: 50}});
    h.render(task({floor: '3층'}));
    const expected = 84 * 1.15 + 10 - 12 - 100 * 300 / 1933;
    assert.ok(Math.abs(parseFloat(h.viewport.style.getPropertyValue('--detail-marker-clearance')) - expected) < 1e-8);
    const resize = h.observers.find((entry) => entry.resize && entry.target === h.ids['floor-image']);
    assert.ok(resize, 'Live image resizing must remeasure the dance envelope');
    h.ids['floor-image'].clientHeight = 600; resize.callback();
    const enlarged = parseFloat(h.viewport.style.getPropertyValue('--detail-marker-clearance'));
    assert.ok(enlarged >= 0 && enlarged < expected);
    h.context.visibleMarkerPoint = null; resize.callback();
    assert.equal(h.viewport.style.getPropertyValue('--detail-marker-clearance'), '');
  });
  await test('physical zoom is clamped 100 to 200 without transforming route or marker', async () => {
    const h = harness(); h.render(task());
    for (let index = 0; index < 8; index++) await h.ids['detail-zoom-in'].click();
    assert.equal(h.stage.style.width, '200%'); assert.equal(h.ids['detail-zoom-in'].disabled, true);
    assert.equal(h.stage.style.transform, undefined); assert.equal(h.ids['map-route'].style.transform, undefined);
    for (let index = 0; index < 8; index++) await h.ids['detail-zoom-out'].click();
    assert.equal(h.stage.style.width, '100%'); assert.equal(h.ids['detail-zoom-out'].disabled, true);
    h.context.window.DetailView.resetZoom(-10); assert.equal(h.stage.style.width, '100%');
    h.context.window.DetailView.resetZoom(900); assert.equal(h.stage.style.width, '200%');
  });
  await test('zoom reset restores scroll and a newly selected task resets map expansion', async () => {
    const h = harness(); h.render(task()); h.context.window.DetailView.resetZoom(175);
    h.viewport.scrollLeft = 123; h.viewport.scrollTop = 456; await h.ids['detail-zoom-reset'].click();
    assert.equal(h.viewport.scrollLeft + h.viewport.scrollTop, 0); assert.equal(h.viewport.style.maxHeight, undefined);
    await h.ids['detail-map-expand'].click(); assert.equal(h.dialog.classList.contains('is-map-expanded'), true);
    h.render(task({id: 'A002'})); assert.equal(h.dialog.classList.contains('is-map-expanded'), false);
    assert.equal(h.ids['detail-map-expand'].getAttribute('aria-expanded'), 'false');
  });
  await test('phone actions use only the selected task registered contact without representative fallback', () => {
    const h = harness(); h.render(task(), {primaryContact: {phone: '031-5555-1234', display_phone: '031-5555-1234'}});
    assert.equal(h.ids.detail.querySelector('.detail-secondary-actions').children[0].href, 'tel:03155551234');
    h.render(task({id: 'A002'})); const phone = h.ids.detail.querySelector('.detail-secondary-actions').children[0];
    assert.equal(phone.tagName, 'button'); assert.equal(phone.disabled, true); assert.equal(phone.href, undefined);
    assert.ok(!h.ids.detail.textContent.includes('031-5189-5175'));
  });
  await test('shared URL has exactly task id and drops query recipient hash and internal path', () => {
    const h = harness(); const api = h.context.window.DetailView;
    assert.equal(api.sharedUrl('A001'), 'https://example.test/?task=A001');
    for (const id of ['', '../A001', 'A001&recipient=010', 'a001', 'A1234', '<img>']) assert.equal(api.sharedUrl(id), null);
    assert.equal(api.sharedUrl('F302', 'https://other.test/private?q=secret'), 'https://other.test/?task=F302');
  });
  await test('copy clipboard is invoked only by user click and copies no recipient', async () => {
    const h = harness(); h.render(task()); assert.equal(h.writes.length, 0);
    await h.get('detail-copy-link').click(); assert.deepEqual(h.writes, ['https://example.test/?task=A001']);
    assert.match(h.get('detail-action-status').textContent, /복사했습니다/);
  });
  await test('clipboard rejection offers a selected readonly manual link without automatic navigation', async () => {
    const h = harness(); h.context.navigator.clipboard = {}; h.render(task());
    await h.get('detail-copy-link').click(); const fallback = h.ids.detail.querySelector('.detail-share-fallback');
    assert.equal(fallback.value, 'https://example.test/?task=A001');
    assert.equal(fallback.readOnly && fallback.focused && fallback.selected, true);
    assert.equal(h.requests.length + h.smsOpens(), 0);
  });
  await test('printing is user initiated and before after events restore zoom and expansion', async () => {
    const h = harness(); h.render(task()); h.dialog.open = true;
    await h.ids['detail-map-expand'].click(); h.context.window.DetailView.resetZoom(150);
    assert.equal(h.printCalls(), 0); await h.get('detail-print').click();
    assert.equal(h.printCalls(), 1); assert.equal(h.body.classList.contains('detail-printing'), true);
    assert.equal(h.stage.style.width, '100%'); assert.equal(h.dialog.classList.contains('is-map-expanded'), false);
    h.emit('window', 'afterprint'); assert.equal(h.body.classList.contains('detail-printing'), false);
    assert.equal(h.stage.style.width, '150%'); assert.equal(h.dialog.classList.contains('is-map-expanded'), true);
  });
  await test('ordinary page print does not activate detail print mode and closing restores state', () => {
    const h = harness(); h.render(task()); h.emit('window', 'beforeprint');
    assert.equal(h.body.classList.contains('detail-printing'), false);
    h.dialog.open = true; h.context.window.DetailView.resetZoom(175); h.emit('window', 'beforeprint'); h.dialog.close();
    assert.equal(h.body.classList.contains('detail-printing'), false); assert.equal(h.stage.style.width, '100%');
  });
  await test('valid deep link fetches one registered task opens before rendering and sends no SMS', async () => {
    const h = harness({url: 'https://example.test/?task=A001'}); h.emit('document', 'DOMContentLoaded');
    assert.equal(h.requests.length, 1); assert.equal(h.requests[0].url, '/api/tasks/A001');
    h.requests[0].resolve(task()); await settle();
    assert.equal(h.dialog.open, true); assert.equal(h.shown.length, 1); assert.equal(h.shown[0].id, 'A001');
    assert.equal(h.context.state.detailTrigger, h.ids.query); assert.equal(h.smsOpens() + h.writes.length, 0);
    h.dialog.close(); assert.equal(new URL(h.context.window.location.href).searchParams.has('task'), false);
  });
  await test('malformed and duplicate task query values do not trigger a request', () => {
    for (const search of ['?task=../A001', '?task=A001%26recipient%3D010', '?task=A001&task=A002', '?task=']) {
      const h = harness({url: 'https://example.test/' + search}); h.emit('document', 'DOMContentLoaded');
      assert.equal(h.requests.length, 0, search);
    }
  });
  await test('unknown or mismatched returned task shows a graceful visible error without opening dialog', async () => {
    for (const response of [task({id: 'A002'}), {id: 'A001'}, null]) {
      const h = harness({url: 'https://example.test/?task=A001'}); h.emit('document', 'DOMContentLoaded');
      h.requests[0].resolve(response); await settle();
      assert.equal(h.dialog.open, false); assert.equal(h.ids['search-workspace'].hidden, false); assert.equal(h.resets.length, 1);
    }
  });
  await test('newer shared task wins regardless of old response order', async () => {
    const h = harness({url: 'https://example.test/?task=A001'}); h.emit('document', 'DOMContentLoaded');
    h.context.window.location.href = 'https://example.test/?task=A002'; h.emit('window', 'popstate');
    h.requests[1].resolve(task({id: 'A002'})); await settle();
    h.requests[0].resolve(task()); await settle(); assert.deepEqual(h.shown.map((item) => item.id), ['A002']);
  });
  await test('navigating away ignores a pending shared-link success or failure', async () => {
    for (const fail of [false, true]) {
      const h = harness({url: 'https://example.test/?task=A001'}); h.emit('document', 'DOMContentLoaded');
      h.context.window.location.href = 'https://example.test/?q=새검색';
      if (fail) h.requests[0].reject(new Error('Not found')); else h.requests[0].resolve(task());
      await settle(); assert.equal(h.shown.length + h.resets.length, 0, 'stale shared link replaced current search');
    }
  });
  await test('busy SMS blocks shared-link requests and response-side navigation', async () => {
    const busy = harness({url: 'https://example.test/?task=A001'}); busy.context.smsBusy = true;
    busy.emit('document', 'DOMContentLoaded'); assert.equal(busy.requests.length, 0);
    for (const fail of [false, true]) {
      const h = harness({url: 'https://example.test/?task=A001'}); h.emit('document', 'DOMContentLoaded'); h.context.smsBusy = true;
      if (fail) h.requests[0].reject(new Error('Unavailable')); else h.requests[0].resolve(task());
      await settle(); assert.equal(h.shown.length + h.resets.length, 0);
    }
  });
  console.log(JSON.stringify({passed: cases.length, failed: 0, realSmsSent: 0, externalRequests: 0, cases}));
}
main().catch((error) => { console.error(error.stack); process.exitCode = 1; });
