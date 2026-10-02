/* HOME navigation only. Search, detail maps and SMS remain owned by app.js. */
(() => {
  'use strict';

  const byId = (id) => document.getElementById(id);
  const input = byId('query');
  const workspace = byId('search-workspace');
  const results = byId('results');
  const heading = byId('results-heading');
  const status = byId('status');
  const quickServices = byId('quick-services');
  const clearButton = byId('clear-button');
  const locationDialog = byId('location-dialog');
  if (!input || !workspace || !results || !heading || !status || !clearButton
      || typeof runSearch !== 'function' || typeof renderResults !== 'function'
      || typeof resetSearchView !== 'function' || typeof getJson !== 'function') return;

  // Reviewed public task IDs, not words found in editable/public-facing titles.
  // New services always appear in All services; update these sets deliberately
  // when their service category has been reviewed.
  const categories = Object.freeze({
    certificate: {
      title: '증명서 발급 안내',
      ids: new Set(['A003', 'A017'])
    },
    vaccination: {
      title: '예방접종·검사 안내',
      query: '접종'
    },
    family: {
      title: '임신·출산 지원 안내',
      ids: new Set(['A005', 'M002', 'M003', 'M004', 'M005', 'M006', 'M007', 'M008'])
    },
    location: {
      title: '층별 시설 위치 안내',
      matches: (task) => /^F\d{3}$/.test(task.id)
    }
  });
  const validCategory = (name) => Object.prototype.hasOwnProperty.call(categories, name);
  const collator = new Intl.Collator('ko');
  let catalog = null;
  let catalogController = null;
  let catalogVersion = 0;
  let catalogPending = false;
  let locationTrigger = null;
  let skipLocationRestore = false;

  function syncHomeVisibility() {
    if (quickServices) quickServices.hidden = !workspace.hidden;
    document.body.classList.toggle('home-has-results', !workspace.hidden);
  }

  new MutationObserver(syncHomeVisibility).observe(workspace, {
    attributes: true, attributeFilter: ['hidden']
  });
  syncHomeVisibility();

  function updateUrl(mode, value = '') {
    const url = new URL(window.location.href);
    ['q', 'category', 'services'].forEach((key) => url.searchParams.delete(key));
    if (mode === 'search' && value.length >= 2 && value.length <= 80) url.searchParams.set('q', value);
    if (mode === 'category') url.searchParams.set('category', value);
    if (mode === 'all') url.searchParams.set('services', 'all');
    // Preserve revision/testing parameters; do not cause a network navigation.
    try { window.history.replaceState(window.history.state, '', url); } catch (_) { /* Optional URL state. */ }
  }

  function cancelCatalog() {
    catalogVersion += 1;
    catalogController?.abort();
    catalogController = null;
    catalogPending = false;
  }

  function cancelExistingRequests() {
    if (typeof state === 'undefined') return;
    state.searchController?.abort();
    state.suggestionController?.abort();
    window.clearTimeout(state.suggestionTimer);
    state.suggestionTimer = null;
  }

  function clearSuggestions() {
    const suggestions = byId('suggestions');
    if (suggestions) suggestions.replaceChildren();
  }

  function updateCategoryControls(category = '', all = false) {
    document.querySelectorAll('[data-home-category]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.homeCategory === category));
    });
    document.querySelectorAll('#browse-services, [data-home-browse]').forEach((button) => {
      button.setAttribute('aria-pressed', String(all));
    });
  }

  function focusResults() {
    heading.setAttribute('tabindex', '-1');
    heading.focus({preventScroll: true});
    workspace.scrollIntoView({block: 'start', behavior: 'auto'});
  }

  function closeLocationForNavigation() {
    if (!locationDialog?.open) return;
    skipLocationRestore = true;
    locationDialog.close();
  }

  async function showCatalog(category = '', {writeUrl = true} = {}) {
    if (category && !validCategory(category)) return;
    cancelCatalog();
    cancelExistingRequests();
    closeLocationForNavigation();
    if (category && categories[category].query) {
      const query = categories[category].query;
      input.value = query;
      clearSuggestions();
      updateCategoryControls();
      updateUrl('search', query);
      void runSearch(query);
      syncHomeVisibility();
      return;
    }
    input.value = '';
    clearSuggestions();
    resetSearchView('업무 목록을 불러오는 중입니다.');
    workspace.hidden = false;
    syncHomeVisibility();
    heading.textContent = category ? categories[category].title : '전체 업무 안내';
    status.textContent = '업무 목록을 불러오는 중입니다...';
    updateCategoryControls(category, !category);
    if (writeUrl) updateUrl(category ? 'category' : 'all', category);
    focusResults();

    const version = catalogVersion;
    const controller = new AbortController();
    catalogController = controller;
    catalogPending = true;
    try {
      let tasks = catalog;
      if (!tasks) {
        const data = await getJson('/api/services', {signal: controller.signal});
        if (version !== catalogVersion) return;
        const ids = new Set();
        if (!Array.isArray(data.results) || !data.results.every((task) => {
          if (!task || typeof task.id !== 'string' || !task.id || ids.has(task.id)
              || !(typeof task.public_title === 'string' && task.public_title.trim()
                || typeof task.name === 'string' && task.name.trim())) return false;
          ids.add(task.id);
          return true;
        })) throw new Error('Invalid public service catalog');
        tasks = [...data.results].sort((a, b) => collator.compare(
          a.name || a.public_title, b.name || b.public_title
        ));
        catalog = tasks;
      }
      if (version !== catalogVersion) return;
      const definition = category ? categories[category] : null;
      const items = definition ? tasks.filter((task) => definition.ids
        ? definition.ids.has(task.id) : definition.matches(task)) : tasks;
      renderResults(items);
      // A catalog is not a ranked search. Keep the original renderer/handlers,
      // but do not claim that its first item has higher relevance.
      results.querySelectorAll('.relevance-badge').forEach((badge) => {
        badge.textContent = '업무 안내';
      });
      if (!items.length) {
        resetSearchView('등록된 업무 안내가 없습니다. 검색어로 다시 찾아보세요.', true);
      }
      status.textContent = `등록된 업무 ${items.length}건`;
    } catch (error) {
      if (version !== catalogVersion || error.name === 'AbortError') return;
      resetSearchView('업무 목록을 불러오지 못했습니다. 잠시 후 다시 선택하거나 검색어로 찾아보세요.', true);
      status.textContent = '업무 목록을 불러오지 못했습니다.';
    } finally {
      if (version === catalogVersion) {
        catalogController = null;
        catalogPending = false;
      }
    }
  }

  function resetHome({writeUrl = true} = {}) {
    cancelCatalog();
    cancelExistingRequests();
    closeLocationForNavigation();
    // Reuse app.js's clear/reset routine, including map state and focus policy.
    clearButton.click();
    updateCategoryControls();
    if (writeUrl) updateUrl('home');
    syncHomeVisibility();
  }

  function onSearchIntent() {
    cancelCatalog();
    updateCategoryControls();
    // Quick suggestions update the input in app.js's own click listener first.
    queueMicrotask(() => {
      updateUrl('search', input.value.trim());
      syncHomeVisibility();
    });
  }

  document.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) return;
    const target = event.target;
    const reset = target.closest('#home-reset, [data-home-reset]');
    if (reset) {
      event.preventDefault();
      resetHome();
      return;
    }
    const category = target.closest('[data-home-category]');
    if (category && validCategory(category.dataset.homeCategory)) {
      event.preventDefault();
      void showCatalog(category.dataset.homeCategory);
      return;
    }
    if (target.closest('#browse-services, [data-home-browse]')) {
      event.preventDefault();
      void showCatalog();
      return;
    }
    const location = target.closest('[data-home-location]');
    if (location && locationDialog) {
      event.preventDefault();
      locationTrigger = location;
      skipLocationRestore = false;
      if (!locationDialog.open) locationDialog.showModal();
      return;
    }
    if (target.closest('#search-button, .quick-suggestion, #suggestions button')) onSearchIntent();
  }, true);

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') onSearchIntent();
  }, true);
  input.addEventListener('input', () => {
    if (!catalogPending) return;
    cancelCatalog();
    resetSearchView('검색어를 입력한 뒤 안내 찾기를 눌러 주세요.');
    updateCategoryControls();
    updateUrl('home');
    status.textContent = '검색어를 입력한 뒤 안내 찾기를 눌러 주세요.';
  });
  clearButton.addEventListener('click', () => {
    cancelCatalog();
    cancelExistingRequests();
    updateCategoryControls();
    updateUrl('home');
    syncHomeVisibility();
  });

  byId('close-location')?.addEventListener('click', () => locationDialog?.close());
  locationDialog?.addEventListener('click', (event) => {
    if (event.target !== locationDialog) return;
    const bounds = locationDialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right
        || event.clientY < bounds.top || event.clientY > bounds.bottom) locationDialog.close();
  });
  locationDialog?.addEventListener('close', () => {
    if (skipLocationRestore) {
      skipLocationRestore = false;
      return;
    }
    if (locationTrigger?.isConnected) locationTrigger.focus({preventScroll: true});
    locationTrigger = null;
  });

  function prepareUrlRestore() {
    // Browser Back/Forward must never dismiss an active send or reset its
    // transaction state. The existing SMS handler remains its sole owner.
    if (typeof smsBusy !== 'undefined' && smsBusy) return false;
    const smsDialog = byId('sms-dialog');
    if (smsDialog?.open) {
      // A pending preview is read-only, but its late response must not populate
      // a dismissed dialog after the selected task has changed.
      if (typeof smsPreviewVersion === 'number') smsPreviewVersion += 1;
      if (typeof smsPreviewReady === 'boolean') smsPreviewReady = false;
      smsDialog.close();
    }
    const smsResult = byId('sms-result-dialog');
    if (smsResult?.open) smsResult.close();
    if (typeof state !== 'undefined') state.detailTrigger = null;
    const detailDialog = byId('detail-dialog');
    if (detailDialog?.open) detailDialog.close();
    closeLocationForNavigation();
    resetSearchView();
    return true;
  }

  function restoreUrl({initial = false} = {}) {
    if (!initial && !prepareUrlRestore()) return;
    const params = new URL(window.location.href).searchParams;
    const category = params.get('category') || '';
    const query = (params.get('q') || '').trim();
    if (validCategory(category)) {
      void showCatalog(category, {writeUrl: false});
    } else if (params.get('services') === 'all') {
      void showCatalog('', {writeUrl: false});
    } else if (query.length >= 2 && query.length <= 80) {
      cancelCatalog();
      cancelExistingRequests();
      updateCategoryControls();
      input.value = query;
      clearSuggestions();
      void runSearch(query);
      syncHomeVisibility();
    } else if (!initial) {
      resetHome({writeUrl: false});
    }
  }
  window.addEventListener('popstate', () => restoreUrl());
  restoreUrl({initial: true});
})();
