/* Official vaccination guidance and dated source/facility records. */
(() => {
  'use strict';
  const root = document.getElementById('vaccination-results');
  if (!root) return;
  let generation = 0;
  let found = false;
  const node = (tag, cls, text) => {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (text) element.textContent = text;
    return element;
  };
  function link(label, url) {
    const a = node('a', 'vx-link', label);
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:' || !['www.hscity.go.kr', 'nip.kdca.go.kr', 'nqs.kdca.go.kr', 'www.kdca.go.kr'].includes(parsed.hostname)) return node('span', '', label);
      a.href = parsed.href;
    } catch (_) { return node('span', '', label); }
    a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', `${label} (공식 사이트, 새 창)`);
    return a;
  }
  function phone(value) {
    const a = node('a', 'vx-phone', value);
    a.href = `tel:${value.replace(/[^0-9]/g, '')}`;
    return a;
  }
  function reset() { generation++; found = false; root.replaceChildren(); root.hidden = true; }
  function render(data, query, openTask) {
    reset();
    if (!data) return;
    found = Boolean(data.source_counts.current || data.source_counts.archive || data.facility_counts.all);
    if (!found) return;
    const version = generation;
    root.hidden = false;
    root.append(node('h3', 'vx-heading', '관련 의료기관·참고자료'));
    root.append(node('p', 'vx-updated', `${data.checked_on} 확인 · 아래 자료는 검색 결과 건수에 포함되지 않습니다.`));

    function directory(kind, title, description) {
      const section = node('details', 'vx-directory');
      let selected = kind === 'facilities' ? data.region : data.source_scope;
      let requestNumber = 0;
      const summary = node('summary'); section.append(summary);
      function scopeLabel() { return kind === 'facilities' ? (selected === 'dongtan' ? '동탄' : '화성시 전체') : (selected === 'archive' ? '지난 공고·행정자료' : '공식 웹 안내'); }
      const choices = kind === 'facilities' ? [['dongtan','동탄'],['all','화성시 전체']] : [['current','공식 웹 안내'],['archive','지난 공고·행정자료']];
      const controls = node('div','vx-related'); controls.setAttribute('role','group');
      controls.setAttribute('aria-label',kind === 'facilities' ? '의료기관 지역 선택' : '참고자료 종류 선택');
      const buttons = choices.map(([value,label]) => {
        const count = (kind === 'facilities' ? data.facility_counts : data.source_counts)[value];
        const button = node('button','vx-button',`${label} (${count}${kind === 'facilities' ? '곳' : '건'})`); button.type = 'button';
        button.setAttribute('aria-pressed',String(value === selected));
        button.addEventListener('click',()=>{selected=value; move(1);}); controls.append(button); return button;
      });
      section.append(controls);
      section.append(node('p', 'vx-directory-note', description));
      const list = node('div', 'vx-list'); section.append(list);
      const nav = node('div', 'vx-nav'); section.append(nav);
      const status = node('p', 'vx-page-status'); status.setAttribute('role','status'); section.append(status);
      function draw(part) {
        list.replaceChildren(); nav.replaceChildren(); status.textContent = '';
        summary.textContent = `${title} · ${scopeLabel()} ${part.total.toLocaleString()}${kind === 'facilities' ? '곳' : '건'}`;
        buttons.forEach((b,i)=>{b.disabled=false;b.setAttribute('aria-pressed',String(choices[i][0]===selected));});
        if (!part.total) list.append(node('p', '', '이 검색어와 일치하는 자료가 없습니다.'));
        part.results.forEach(item => {
          const row = node('article', 'vx-record'); row.dataset.recordId = item.id;
          if (kind === 'sources') {
            row.append(link(item.title, item.url));
            row.append(node('p', 'vx-meta', `${item.published_date || '게시일 미표시'} · ${item.category} · ${item.period_label}`));
          } else {
            row.append(node('h4', '', item.title), phone(item.phone), node('p', 'vx-address', item.address));
            const programs = node('ul', 'vx-programs');
            item.programs.forEach(p => {
              const li = node('li', '', `${p.name} · ${p.as_of} 명단 `);
              li.append(link('근거 공고', p.reference.url)); programs.append(li);
              if (p.phone && p.phone !== item.phone) li.append(document.createTextNode(' · 사업별 문의 '), phone(p.phone));
            });
            row.append(programs);
          }
          list.append(row);
        });
        const pages = Math.max(1, Math.ceil(part.total / part.page_size));
        const previous = node('button', 'vx-button', '이전'); previous.type = 'button'; previous.disabled = part.page <= 1;
        const next = node('button', 'vx-button', '다음'); next.type = 'button'; next.disabled = part.page >= pages;
        nav.append(previous, node('span', '', `${part.page} / ${pages} 페이지`), next);
        previous.addEventListener('click',()=>move(part.page-1)); next.addEventListener('click',()=>move(part.page+1));
      }
      async function move(page) {
        const request = ++requestNumber;
        buttons.forEach(b=>{b.disabled=true;});
        nav.querySelectorAll('button').forEach(b=>{b.disabled=true;});
        status.textContent = '자료를 불러오는 중입니다.';
        try {
          const options = {query,kind,page,region:kind === 'facilities' ? selected : data.region,source_scope:kind === 'sources' ? selected : data.source_scope};
          const response = await fetch('/api/vaccination/search', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(options)});
          if (!response.ok) throw new Error('lookup');
          const result = await response.json();
          if (version !== generation || request !== requestNumber) return;
          draw(result[kind]);
          status.textContent = `${scopeLabel()} ${page}페이지를 표시했습니다.`;
        } catch (_) {
          if (version !== generation || request !== requestNumber) return;
          status.textContent = '자료를 불러오지 못했습니다. 지역 또는 자료 종류를 선택해 다시 시도해 주세요.';
          buttons.forEach(b=>{b.disabled=false;});
        }
      }
      draw(data[kind]); root.append(section);
    }
    if (data.facility_counts.all) directory('facilities','접종 위탁의료기관','기본 범위는 동탄입니다. 화성시 전체 명단으로 전환할 수 있습니다. 각 명단의 기준일을 확인하고 현재 참여·백신 보유 여부는 해당 기관에 문의하세요.');
    if (data.source_counts.current || data.source_counts.archive) directory('sources','공식 참고자료','공식 웹 안내와 게시일이 있는 공고·행정자료를 구분했습니다. 지난 공고의 대상·기간을 현재 이용 조건으로 적용하지 마세요.');
  }
  window.VaccinationView = Object.freeze({render, reset, hasResults:()=>found});
})();
