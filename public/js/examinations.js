/* Official guidance collections use the established result-card renderer. */
(() => {
  'use strict';
  const dialog = document.getElementById('service-guide-dialog');
  const body = document.getElementById('service-guide-body');
  const title = document.getElementById('service-guide-title');
  if (!dialog || !body || !title) return;
  let trigger = null;
  const labels = {A002:'검사 접수',F104:'검사실 위치',A003:'제증명 발급',A004:'익명 HIV 업무',A005:'임산부 안내',A008:'성매개감염병 상담',A009:'성매개감염병 검사',A011:'결핵 상담',A012:'결핵 검사',A019:'골다공증 업무',F102:'영상의학실 위치',F109:'모자보건실·예방접종실 위치',M002:'선천성대사이상 지원',M007:'태아 검사비 지원',M009:'예방접종 업무',A018:'예방접종 수납',D001:'치매 업무',F105:'치매안심센터 위치'};
  function node(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text) el.textContent = text;
    return el;
  }
  function reset() { trigger = null; if (dialog.open) dialog.close(); body.replaceChildren(); }
  document.getElementById('service-guide-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{ if (trigger?.isConnected) trigger.focus({preventScroll:true}); });
  dialog.addEventListener('click',event=>{
    if (event.target !== dialog) return;
    const r = dialog.getBoundingClientRect();
    if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close();
  });
  function open(item, data, button, openTask) {
    trigger = button; body.replaceChildren(); title.textContent = item.title;
    body.append(node('p','service-guide-summary',item.summary));
    body.append(node('p','vx-updated',`${data.checked_on} 공식 페이지 확인`));
    if (item.expired) body.append(node('p','vx-caution',`기간 종료 · ${item.valid_until}까지의 안내입니다.`));
    if (item.confirmation) body.append(node('p','vx-caution',`확인 필요: ${item.confirmation}`));
    else if (item.needs_confirmation) body.append(node('p','vx-caution','추가 확인이 필요한 안내입니다.'));
    if (item.fee) body.append(node('p','ex-fee',`비용: ${item.fee}`));
    if (item.result_time) body.append(node('p','',`결과·처리: ${item.result_time}`));
    const list = node('ul'); item.details.forEach(text=>list.append(node('li','',text))); body.append(list);
    if (item.caution) body.append(node('p','vx-caution',item.caution));
    if (item.general_preparation) {
      body.append(node('h3','','일반 검사 준비사항'));
      const prep = node('ul'); data.preparation.forEach(text=>prep.append(node('li','',text))); body.append(prep);
    }
    const contacts = item.contacts || [{label:item.phone === '1339' ? '질병관리청 문의' : '동탄구보건소 문의',phone:item.phone}];
    const contactList = node('div','ex-contacts');
    contacts.forEach(contact=>{
      const p = node('p','vx-contact',`${contact.label} `);
      const tel = node('a','vx-phone',contact.phone); tel.href = `tel:${contact.phone.replace(/\D/g,'')}`;
      p.append(tel); contactList.append(p);
    }); body.append(contactList);
    const refs = node('div','vx-refs');
    (item.references || item.sources).forEach(ref=>{
      try {
        const url = new URL(ref.url);
        if (url.protocol !== 'https:' || !['www.hscity.go.kr','chronic.hscity.go.kr','nip.kdca.go.kr','nqs.kdca.go.kr','www.kdca.go.kr','hsmind.or.kr','www.hsmind.or.kr','www.hsalcohol.kr','www.hsmindstep.or.kr'].includes(url.hostname)) return;
        const a = node('a','vx-link',`${ref.title} 원문`); a.href=url.href; a.target='_blank'; a.rel='noopener noreferrer';
        a.setAttribute('aria-label',`${ref.title} 원문 (공식 사이트, 새 창)`); refs.append(a);
      } catch (_) { /* Invalid external URLs are not interactive. */ }
    }); body.append(refs);
    const related = node('div','vx-related');
    item.related_task_ids.forEach(id=>{
      if (!openTask) return;
      const link = node('button','vx-button',item.related_task_labels?.[id] || labels[id] || '관련 업무 보기'); link.type='button';
      link.addEventListener('click',async()=>{
        link.disabled=true;
        try {
          await openTask(id,button);
          if (document.getElementById('detail-dialog')?.open) { trigger=null; dialog.close(); }
        } catch (_) { related.append(node('p','vx-caution','업무 상세를 불러오지 못했습니다. 다시 시도해 주세요.')); }
        finally { link.disabled=false; }
      }); related.append(link);
    }); body.append(related);
    if (!dialog.open) dialog.showModal();
  }
  function entries(response, query, openTask) {
    const result = [];
    const seen = new Set();
    for (const [kind,data] of [['vaccination',response.vaccination],['examinations',response.examinations],['services',response.services]]) {
      for (const item of data?.guides || []) {
        if (seen.has(item.id)) continue;
        seen.add(item.id);
        result.push({id:`guide-${item.id}`,result_kind:'guide',result_category:item.result_category || 'business',
          related_task_ids:item.related_task_ids || [],
          public_title:item.title,public_summary:item.summary,show_map:false,
          department:kind === 'vaccination' ? '예방접종 안내' : kind === 'services' ? '보건사업·민원 안내' : '검사·검진 안내',
          result_meta:[item.fee,item.result_time && `결과·처리 ${item.result_time}`,
            item.expired ? '기간 종료' : (item.confirmation || item.needs_confirmation) ? '확인 필요' : ''].filter(Boolean),
          is_archived:Boolean(item.expired),
          open:button=>open(item,data,button,openTask)});
      }
    }
    return result.sort((a,b)=>Number(a.is_archived)-Number(b.is_archived));
  }
  function compose(guides, tasks) {
    // The current guide already provides buttons to these tasks and locations.
    // Distinct programs sharing a room remain distinct; expired guides cannot
    // replace a current task. Location-only queries still show location cards.
    const linked = new Set(guides.filter(g=>!g.is_archived).flatMap(g=>g.related_task_ids || []));
    const seen = new Set();
    return [...guides,...tasks.filter(t=>!linked.has(t.id))].filter(item=>{
      if (seen.has(item.id)) return false;
      seen.add(item.id); return true;
    });
  }
  window.ServiceGuidanceView = Object.freeze({entries,compose,reset});
})();
