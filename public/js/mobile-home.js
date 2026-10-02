/* Mobile restores the archived pre-redesign view. Desktop nodes are retained and restored. */
(() => {
  'use strict';
  const media = window.matchMedia('(max-width: 820px)');
  const legacy = {"header": "\n    <div class=\"home-brand\">\n      <a class=\"home-city-logo\" href=\"https://www.hscity.go.kr/\" target=\"_blank\" rel=\"noopener noreferrer\" aria-label=\"화성특례시 공식 홈페이지 (새 창)\">\n        <img src=\"/images/hwaseong-special-city-bi.png\" alt=\"화성특례시\">\n      </a>\n      <a id=\"home-reset\" class=\"home-brand-name\" href=\"/\" data-home-reset>동탄구보건소</a>\n      <span class=\"home-pilot-badge\">개인 제작 · 비공식 평가용</span>\n    </div>\n    <nav class=\"home-nav\" aria-label=\"주요 메뉴\">\n      <a href=\"https://www.hscity.go.kr/health/index.do\" target=\"_blank\" rel=\"noopener noreferrer\">보건소 안내<span class=\"sr-only\"> (공식 홈페이지, 새 창)</span></a>\n      <button id=\"browse-services\" type=\"button\">전체 업무</button>\n      <button class=\"home-location-button\" type=\"button\" data-home-location>\n        <svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z\"/><circle cx=\"12\" cy=\"10\" r=\"3\"/></svg>\n        보건소 위치·운영시간\n      </button>\n    </nav>\n  ", "title": "필요한 <span>보건소 업무</span>를<br>바로 찾아보세요", "description": "업무명을 몰라도 괜찮아요.<br>궁금한 내용을 문장으로 입력해 보세요."};
  const header = document.querySelector('.home-header');
  const title = document.getElementById('home-title');
  const description = document.querySelector('.home-description');
  const input = document.getElementById('query');
  if (!header || !title || !description || !input) return;
  let restore = null;
  const activate = () => {
    const undo = [];
    const detach = element => {
      if (!element) return;
      const anchor = document.createComment('desktop original position');
      element.replaceWith(anchor);
      undo.push(() => anchor.replaceWith(element));
    };
    const replaceChildren = (element, html) => {
      const original = Array.from(element.childNodes);
      const template = document.createElement('template');
      template.innerHTML = html;
      element.replaceChildren(template.content);
      undo.push(() => element.replaceChildren(...original));
    };
    // Retain all desktop-only content off-document, without duplicate IDs or tab stops.
    document.querySelectorAll('.portal-home-only').forEach(detach);
    detach(document.querySelector('.portal-utility'));
    detach(document.getElementById('hero-slideshow'));
    detach(document.getElementById('search-examples'));
    replaceChildren(header, legacy.header);
    replaceChildren(title, legacy.title);
    replaceChildren(description, legacy.description);
    const eyebrow = document.createElement('p');
    eyebrow.className = 'home-eyebrow'; eyebrow.textContent = '화성특례시 동탄구보건소';
    title.before(eyebrow); undo.push(() => eyebrow.remove());
    const label = document.querySelector('#search-button > span');
    const originalLabel = label.textContent;
    label.textContent = '안내 찾기'; undo.push(() => { label.textContent = originalLabel; });
    const placeholder = input.getAttribute('placeholder');
    const describedBy = input.getAttribute('aria-describedby');
    input.setAttribute('placeholder', '예: 보건증을 발급받으려면 어디로 가야 하나요?');
    input.setAttribute('aria-describedby', 'search-help home-privacy');
    undo.push(() => { input.setAttribute('placeholder', placeholder); input.setAttribute('aria-describedby', describedBy); });
    document.body.classList.remove('home-v3');
    document.body.classList.add('legacy-mobile');
    restore = () => {
      const focus = document.activeElement;
      const headerFocus = header.contains(focus);
      undo.reverse().forEach(fn => fn());
      document.body.classList.remove('legacy-mobile');
      document.body.classList.add('home-v3');
      if (headerFocus) input.focus({ preventScroll: true });
      restore = null;
    };
  };
  const update = () => {
    if (media.matches && !restore) activate();
    else if (!media.matches && restore) restore();
  };
  media.addEventListener('change', update);
  update();
})();
