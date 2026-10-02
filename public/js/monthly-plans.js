/* Dated plan data stays separate from the permanent tasks/contact catalog. */
(() => {
  'use strict';
  const DATA_URL = '/data/monthly-plan-2026-10.json';
  const PLAN_SEARCH_CONTEXT = '2026년 10월 월간 일정 프로그램 월간업무계획';
  const normalize = (text) => String(text || '').normalize('NFKC').toLocaleLowerCase('ko').replace(/[\s·ㆍ,「」『』()\-]/g, '');
  function matches(item, query) {
    const words = String(query || '').trim().split(/\s+/).map(normalize).filter(Boolean);
    const haystack = normalize([PLAN_SEARCH_CONTEXT, item.title, item.team, item.location, item.audience,
      item.content, ...item.related_tasks.map((task) => task.title)].join(' '));
    return words.every((word) => haystack.includes(word));
  }
  function koreaDate(now = new Date()) {
    const parts = new Intl.DateTimeFormat('en', {timeZone:'Asia/Seoul', year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
    const get = (key) => parts.find((part) => part.type === key).value;
    return `${get('year')}-${get('month')}-${get('day')}`;
  }
  function planStatus(item, today) {
    if (item.schedule_review) return {text:'일정 확인 필요',kind:'review'};
    if (item.period.end && today > item.period.end) return {text:'지난 계획',kind:'ended'};
    if (item.period.start && today < item.period.start) return {text:'예정',kind:'planned'};
    return {text:'진행중',kind:'ongoing'};
  }
  function safeRelated(link) {
    if (typeof link.href !== 'string' || !/^\/\?/.test(link.href)) return false;
    const url = new URL(link.href, 'https://local.invalid');
    return url.origin === 'https://local.invalid' && url.pathname === '/'
      && [...url.searchParams.keys()].every((key) => ['q','task'].includes(key))
      && /^[A-Z]\d{3}$/.test(link.task_id);
  }
  function validate(data) {
    if (data.schema_version !== 1 || data.month !== '2026-10' || !Array.isArray(data.items)) throw new Error('Invalid plan data');
    const seen = new Set();
    for (const item of data.items) {
      if (!/^MP202610-\d{2}$/.test(item.id) || seen.has(item.id)) throw new Error('Invalid plan ID');
      seen.add(item.id);
      for (const field of ['title','department','team','schedule_text','location','audience','content']) {
        if (typeof item[field] !== 'string') throw new Error('Invalid plan text');
      }
      if (!Array.isArray(item.notes) || !item.notes.every((x) => typeof x === 'string')
        || !Array.isArray(item.related_tasks) || !item.related_tasks.every(safeRelated)) throw new Error('Invalid plan links');
      if (!item.period || !['start','end'].every((key) => item.period[key] === null || /^\d{4}-\d{2}-\d{2}$/.test(item.period[key]))) throw new Error('Invalid plan dates');
    }
    return data;
  }
  const helpers = {matches, koreaDate, planStatus, validate};
  if (typeof module !== 'undefined' && module.exports) { module.exports = helpers; return; }
  const byId = (id) => document.getElementById(id);
  const node = (tag, className = '', text = '') => {
    const result = document.createElement(tag); result.className = className; result.textContent = text; return result;
  };
  async function load() {
    const response = await fetch(DATA_URL, {credentials:'same-origin'});
    if (!response.ok) throw new Error('Unable to load plan');
    return validate(await response.json());
  }
  function separateTopics(text) {
    return text.replace(/\s*(\[(?:구강|영양)\])/g, '\n\n$1').trim();
  }
  function renderItem(item, today) {
    const details = node('details','mp-item'); details.id = item.id;
    const summary = node('summary'), kicker = node('div','mp-kicker');
    const status = planStatus(item,today);
    kicker.append(node('span','mp-badge mp-badge-'+status.kind,status.text),node('span','',item.team));
    summary.append(kicker,node('h3','',item.title),node('span','mp-brief',separateTopics(item.location)));
    const body = node('div','mp-body'), list = node('dl');
    for (const [label,value] of [['일 정',item.schedule_text],['장 소',item.location],
      ['대 상',item.audience],['내 용',item.content]]) list.append(node('dt','',label),node('dd','',separateTopics(value)));
    body.append(list);
    if (item.notes.length) {
      const notes = node('div','mp-notes'); notes.append(node('strong','','확인해 주세요'));
      item.notes.forEach((text) => notes.append(node('p','',text))); body.append(notes);
    }
    if (item.related_tasks.length) {
      const related = node('div','mp-related'); related.append(node('strong','','관련 상시 안내·문의전화'),document.createElement('br'));
      for (const link of item.related_tasks) { const a=node('a','',link.title);a.href=link.href;related.append(a); }
      body.append(related);
    }
    details.append(summary,body); return details;
  }
  async function startPage() {
    if (!byId('plan-list')) return;
    try {
      const data = await load(), today = koreaDate();
      const input=byId('plan-query'),team=byId('plan-team');
      const params = new URL(window.location.href).searchParams;
      input.value = (params.get('q') || '').slice(0,80);
      const taskId = params.get('task');
      let selectedTask = /^[A-Z]\d{3}$/.test(taskId || '') ? taskId : null;
      function render() {
        const items = data.items.filter((item) => matches(item,input.value)
          && (!team.value || item.team === team.value)
          && (!selectedTask || item.related_tasks.some((t) => t.task_id === selectedTask)));
        byId('plan-list').replaceChildren(...items.map((item) => renderItem(item,today)));
        byId('plan-count').textContent = `${items.length}건 / 전체 ${data.items.length}건`;
        byId('plan-empty').hidden = items.length > 0;
      }
      function update(event) {
        event?.preventDefault();
        const url=new URL(window.location.href);url.searchParams.delete('task');selectedTask=null;
        if (input.value.trim()) url.searchParams.set('q',input.value.trim());else url.searchParams.delete('q');
        history.replaceState(null,'',url.pathname+url.search); render();
      }
      byId('plan-search').addEventListener('submit',update);
      input.addEventListener('input',update);team.addEventListener('change',update);
      byId('plan-reset').addEventListener('click',() => {input.value='';team.value='';update();input.focus();});
      render();
    } catch (_) {byId('plan-error').hidden=false;byId('plan-count').textContent='불러오기 실패';}
  }
  async function startDiscovery() {
    if (!byId('monthly-discovery')) return;
    try {
      const data=await load();const link=byId('monthly-query-link');const input=byId('query');
      byId('monthly-all-link').textContent=`10월 계획 ${data.items.length}건 보기`;
      function update() {
        const query=(input?.value || '').trim();
        const count=query ? data.items.filter((item)=>matches(item,query)).length : 0;
        link.hidden=!query;
        link.textContent=`“${query}” 월간 계획 ${count}건 찾아보기`;
        link.href='/monthly-plans.html?q='+encodeURIComponent(query);
      }
      input?.addEventListener('input',update);
      const heading=byId('results-heading');
      if (heading) new MutationObserver(update).observe(heading,{childList:true,subtree:true,characterData:true});
      byId('clear-button')?.addEventListener('click',update);update();
    } catch (_) {byId('monthly-all-link').textContent='10월 월간 계획 보기';}
  }
  startPage();startDiscovery();
})();
