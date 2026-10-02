'use strict';

// No browser, server, credentials or outbound requests: only the HOME adapter
// and public catalog fixture are read. Actual browser integration is separate.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'public/js/home-v2.js'), 'utf8');
const appSource = fs.readFileSync(path.join(root, 'public/js/app.js'), 'utf8');
const tasks = JSON.parse(fs.readFileSync(path.join(root, 'data/deployment_catalog.json'), 'utf8')).tasks;
const passed = [];

class Element {
  constructor(id = '', selector = '') {
    Object.assign(this, {
      id, selector, hidden: false, value: '', textContent: '', open: false,
      dataset: {}, listeners: {}, attrs: {}, isConnected: true,
      classList: {toggle() {}, contains() { return false; }}
    });
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  setAttribute(key, value) { this.attrs[key] = value; }
  replaceChildren() {}
  focus() { this.focused = true; }
  scrollIntoView() {}
  querySelectorAll() { return this.badges || []; }
  closest(selectors) {
    return selectors.split(',').some((selector) => selector.trim() === this.selector
      || selector.trim() === `#${this.id}`) ? this : null;
  }
  click() { this.emit('click'); }
  emit(type, extra = {}) {
    for (const callback of this.listeners[type] || []) {
      callback({target: this, preventDefault() {}, ...extra});
    }
  }
  showModal() { this.open = true; }
  close() {
    this.open = false;
    queueMicrotask(() => this.emit('close'));
  }
  getBoundingClientRect() { return {left: 0, right: 100, top: 0, bottom: 100}; }
}

function harness(url = 'https://example.test/?revision=preserved') {
  const elements = Object.fromEntries([
    'query', 'search-workspace', 'results', 'results-heading', 'status',
    'quick-services', 'clear-button', 'location-dialog', 'close-location', 'suggestions',
    'detail-dialog', 'sms-dialog', 'sms-result-dialog'
  ].map((id) => [id, new Element(id)]));
  elements['search-workspace'].hidden = true;
  const categories = ['certificate', 'vaccination', 'family', 'location'].map((name) => {
    const element = new Element('', '[data-home-category]');
    element.dataset.homeCategory = name;
    return element;
  });
  const browse = new Element('browse-services');
  const events = {};
  const requests = [];
  const searches = [];
  let rendered = [];
  const window = {
    location: {href: url},
    history: {
      state: null,
      replaceState(state, title, nextUrl) { window.location.href = String(nextUrl); }
    },
    clearTimeout,
    addEventListener(type, callback) { events[`window-${type}`] = callback; }
  };
  const document = {
    body: new Element('body'),
    getElementById: (id) => elements[id],
    querySelectorAll: (selector) => selector.includes('data-home-category')
      ? categories : selector.includes('browse-services') ? [browse] : [],
    addEventListener(type, callback) { events[type] = callback; }
  };
  const context = {
    window, document, Element, URL, AbortController, Intl, queueMicrotask,
    MutationObserver: class { observe() {} },
    smsBusy: false,
    smsPreviewVersion: 1,
    smsPreviewReady: true,
    state: {
      searchController: new AbortController(),
      suggestionController: new AbortController()
    },
    getJson: (requestUrl, options) => new Promise((resolve, reject) => {
      requests.push({url: requestUrl, options, resolve, reject});
    }),
    resetSearchView: (message, preserveHeading) => {
      rendered = [];
      if (!preserveHeading) elements['results-heading'].textContent = '민원 검색 결과';
      elements.results.textContent = message || '';
    },
    renderResults: (items) => {
      rendered = items;
      elements.results.badges = items.map(() => new Element());
    },
    runSearch: (query) => {
      searches.push(query);
      elements['search-workspace'].hidden = false;
    }
  };
  // Existing app.js owns the clear button; the adapter adds only its own state.
  elements['clear-button'].addEventListener('click', () => {
    elements.query.value = '';
    elements['search-workspace'].hidden = true;
    context.resetSearchView();
  });
  vm.createContext(context);
  vm.runInContext(source, context, {filename: 'home-v2.js'});
  return {
    elements, categories, browse, events, requests, searches, window, context,
    click: (target) => events.click({target, preventDefault() {}}),
    get rendered() { return rendered; }
  };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));
const urlParams = (test) => new URL(test.window.location.href).searchParams;

async function main() {
  assert.match(appSource, /createText\('span', 'relevance-badge',/);
  assert.match(source, /querySelectorAll\('\.relevance-badge'\)/);
  passed.push('existing_renderer_badge_selector');

  let test = harness();
  assert.equal(test.requests.length, 0);
  assert.equal(test.elements['quick-services'].hidden, false);
  passed.push('initial_home_has_no_catalog_request');

  test.click(test.browse);
  assert.equal(test.requests.length, 1);
  assert.equal(test.requests[0].url, '/api/services');
  assert.equal(test.elements['quick-services'].hidden, true);
  test.requests[0].resolve({results: tasks, total: tasks.length});
  await settle();
  assert.equal(test.rendered.length, 63);
  assert.ok(test.elements.results.badges.every((badge) => badge.textContent === '업무 안내'));
  assert.equal(urlParams(test).get('revision'), 'preserved');
  passed.push('all_63_services_reuse_renderer_preserve_revision');

  for (const [name, count] of [
    ['certificate', 2], ['family', 8], ['location', 23]
  ]) {
    test.click(test.categories.find((category) => category.dataset.homeCategory === name));
    await settle();
    assert.equal(test.rendered.length, count, name);
    assert.equal(test.requests.length, 1, 'The full catalog is reused.');
    passed.push(`category_${name}_uses_cached_catalog`);
  }

  test.click(new Element('home-reset'));
  await settle();
  assert.equal(test.elements['search-workspace'].hidden, true);
  assert.equal(test.elements['quick-services'].hidden, false);
  assert.equal(urlParams(test).get('category'), null);
  passed.push('home_reset_restores_quick_services');

  test = harness();
  test.click(test.browse);
  test.click(test.categories[0]);
  assert.equal(test.requests[0].options.signal.aborted, true);
  test.requests[1].resolve({results: tasks});
  await settle();
  test.requests[0].resolve({results: tasks});
  await settle();
  assert.equal(test.rendered.length, 2);
  passed.push('stale_catalog_response_cannot_replace_latest_category');

  test = harness();
  test.click(test.browse);
  test.elements.query.value = '예방접종';
  test.elements.query.emit('keydown', {key: 'Enter'});
  test.requests[0].resolve({results: tasks});
  await settle();
  assert.equal(test.rendered.length, 0);
  assert.equal(test.requests[0].options.signal.aborted, true);
  assert.equal(urlParams(test).get('q'), '예방접종');
  passed.push('search_intent_cancels_catalog_and_sets_query_url');

  test = harness();
  test.click(test.browse);
  test.elements.query.value = '검사';
  test.elements.query.emit('input');
  test.requests[0].resolve({results: tasks});
  await settle();
  assert.equal(test.rendered.length, 0);
  assert.ok(test.elements.results.textContent.includes('검색어'));
  passed.push('typing_cancels_pending_catalog_without_stuck_loading');

  test = harness('https://example.test/?category=certificate&revision=unchanged');
  test.requests[0].resolve({results: tasks.map((task) => ({
    ...task, name: '변경된 업무 제목', public_title: '변경된 공개 제목'
  }))});
  await settle();
  assert.equal(test.rendered.map((task) => task.id).sort().join(','), 'A003,A017');
  passed.push('category_uses_ids_despite_changed_titles');

  test = harness('https://example.test/?q=%EC%98%88%EB%B0%A9%EC%A0%91%EC%A2%85');
  assert.equal(test.searches.join(','), '예방접종');
  passed.push('initial_query_url_uses_existing_search');

  test = harness();
  test.click(test.categories.find((category) => category.dataset.homeCategory === 'vaccination'));
  await settle();
  assert.equal(test.searches.join(','), '접종');
  assert.equal(test.requests.length, 0);
  assert.equal(test.elements.query.value, '접종');
  assert.equal(urlParams(test).get('q'), '접종');
  assert.equal(urlParams(test).get('category'), null);
  assert.equal(test.elements['quick-services'].hidden, true);
  passed.push('vaccination_card_uses_existing_search_with_query');

  test = harness('https://example.test/?category=vaccination');
  await settle();
  assert.equal(test.searches.join(','), '접종');
  assert.equal(test.requests.length, 0);
  assert.equal(urlParams(test).get('q'), '접종');
  passed.push('legacy_vaccination_category_restores_same_search');

  test = harness();
  test.click(test.browse);
  test.click(test.categories.find((category) => category.dataset.homeCategory === 'vaccination'));
  assert.equal(test.requests[0].options.signal.aborted, true);
  test.requests[0].resolve({results: tasks});
  await settle();
  assert.equal(test.searches.join(','), '접종');
  assert.equal(test.rendered.length, 0);
  assert.equal(urlParams(test).get('q'), '접종');
  passed.push('stale_catalog_does_not_replace_vaccination_search');

  test = harness('https://example.test/?category=__proto__');
  assert.equal(test.requests.length, 0);
  passed.push('prototype_property_is_not_a_category');

  test = harness();
  test.click(test.browse);
  test.requests[0].resolve({results: [
    {id: 'A003', name: '복제'}, {id: 'A003', name: '복제'}
  ]});
  await settle();
  assert.equal(test.rendered.length, 0);
  assert.ok(test.elements.status.textContent.includes('불러오지'));
  passed.push('duplicate_catalog_ids_fail_closed');

  test = harness();
  const location = new Element('', '[data-home-location]');
  test.click(location);
  assert.equal(test.elements['location-dialog'].open, true);
  test.click(test.categories[3]);
  assert.equal(test.elements['location-dialog'].open, false);
  test.requests[0].resolve({results: tasks});
  await settle();
  assert.equal(test.rendered.length, 23);
  assert.equal(test.elements['results-heading'].focused, true);
  assert.notEqual(location.focused, true);
  passed.push('location_to_facilities_keeps_results_focus');

  test = harness();
  test.click(test.browse);
  test.requests[0].reject(new Error('HTTP failure'));
  await settle();
  assert.ok(test.elements.status.textContent.includes('불러오지'));
  passed.push('catalog_network_failure_has_visible_message');

  test = harness();
  test.click(new Element('', '[data-home-browse]'));
  test.requests[0].resolve({results: tasks});
  await settle();
  assert.equal(test.rendered.length, 63);
  passed.push('secondary_browse_trigger_shows_all');

  test = harness();
  test.click(test.browse);
  test.requests[0].resolve({results: [...tasks, {
    id: 'NEW001', name: '새로운 미분류 업무', public_title: '새로운 안내'
  }]});
  await settle();
  assert.equal(test.rendered.length, 64);
  assert.ok(test.rendered.some((task) => task.id === 'NEW001'));
  test.click(test.categories[0]);
  await settle();
  assert.equal(test.rendered.length, 2);
  passed.push('new_uncategorized_task_remains_in_all_services');

  for (const [route, mode] of [
    ['?revision=retained', 'home'],
    ['?q=%EA%B2%80%EC%82%AC', 'search'],
    ['?category=certificate', 'category']
  ]) {
    test = harness();
    test.elements['detail-dialog'].open = true;
    test.context.state.detailTrigger = new Element('old-result');
    test.window.location.href = `https://example.test/${route}`;
    test.events['window-popstate']();
    assert.equal(test.elements['detail-dialog'].open, false);
    assert.equal(test.context.state.detailTrigger, null);
    if (mode === 'home') assert.equal(test.elements['search-workspace'].hidden, true);
    if (mode === 'search') assert.equal(test.searches.join(','), '검사');
    if (mode === 'category') {
      test.requests[0].resolve({results: tasks});
      await settle();
      assert.equal(test.rendered.length, 2);
    }
    passed.push(`popstate_${mode}_closes_old_detail`);
  }

  test = harness();
  test.elements['detail-dialog'].open = true;
  test.elements['sms-dialog'].open = true;
  test.window.location.href = 'https://example.test/?q=%EA%B2%80%EC%82%AC';
  test.events['window-popstate']();
  assert.equal(test.elements['sms-dialog'].open, false);
  assert.equal(test.elements['detail-dialog'].open, false);
  assert.equal(test.context.smsPreviewVersion, 2);
  assert.equal(test.context.smsPreviewReady, false);
  assert.equal(test.searches.join(','), '검사');
  passed.push('popstate_invalidates_idle_sms_preview_before_closing');

  test = harness();
  test.elements['sms-result-dialog'].open = true;
  test.window.location.href = 'https://example.test/';
  test.events['window-popstate']();
  assert.equal(test.elements['sms-result-dialog'].open, false);
  passed.push('popstate_closes_completed_sms_result');

  test = harness();
  test.context.smsBusy = true;
  test.elements['sms-dialog'].open = true;
  test.elements['detail-dialog'].open = true;
  test.context.state.selectedTask = {id: 'A018'};
  test.window.location.href = 'https://example.test/?services=all';
  test.events['window-popstate']();
  assert.equal(test.requests.length, 0);
  assert.equal(test.elements['sms-dialog'].open, true);
  assert.equal(test.elements['detail-dialog'].open, true);
  assert.equal(test.context.smsPreviewVersion, 1);
  assert.equal(test.context.smsPreviewReady, true);
  assert.equal(test.context.state.selectedTask.id, 'A018');
  passed.push('popstate_never_resets_or_dismisses_active_sms_send');

  console.log(JSON.stringify({passed: passed.length, failed: 0, realSmsSent: 0, cases: passed}));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
