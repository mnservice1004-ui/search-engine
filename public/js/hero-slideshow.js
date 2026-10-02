/* Homepage photos only; no dependency on search, map or contact handlers. */
(() => {
  'use strict';
  const root = document.getElementById('hero-slideshow');
  if (!root) return;
  const slides = Array.from(root.querySelectorAll('.hero-slide'));
  const controls = root.querySelector('.hero-slide-controls');
  const previous = document.getElementById('hero-photo-prev');
  const next = document.getElementById('hero-photo-next');
  const toggle = document.getElementById('hero-photo-toggle');
  const count = document.getElementById('hero-photo-count');
  const caption = document.getElementById('hero-photo-caption');
  if (slides.length < 2 || !controls || !previous || !next || !toggle || !count || !caption) return;
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const pending = new Map();
  let current = 0, timer = null, request = 0;
  let paused = motion.matches, hovering = false, busy = false, toggleIntent = null;
  const mobile = window.matchMedia('(max-width: 820px)');
  const hidden = () => mobile.matches || document.hidden || document.body.classList.contains('home-has-results');
  const load = (index) => {
    const photo = slides[index];
    if (photo.complete && photo.naturalWidth > 0) return Promise.resolve(true);
    if (pending.has(index)) return pending.get(index);
    const promise = new Promise(resolve => {
      const finish = (ok) => {
        photo.removeEventListener('load', success);
        photo.removeEventListener('error', failure);
        resolve(ok);
      };
      const success = () => finish(true);
      const failure = () => finish(false);
      photo.addEventListener('load', success, { once: true });
      photo.addEventListener('error', failure, { once: true });
      if (photo.dataset.src && !photo.getAttribute('src')) photo.src = photo.dataset.src;
      else if (photo.complete) finish(photo.naturalWidth > 0);
    });
    pending.set(index, promise);
    return promise;
  };
  const stop = () => { clearTimeout(timer); timer = null; };
  const schedule = () => {
    stop();
    if (!paused && !hovering && !busy && !hidden()) timer = setTimeout(() => show(current + 1), 6000);
  };
  const updateToggle = () => {
    toggle.classList.toggle('is-paused', paused);
    toggle.setAttribute('aria-label', paused ? '사진 자동 전환 시작' : '사진 자동 전환 일시정지');
  };
  const show = async (target) => {
    const index = (target + slides.length) % slides.length;
    const token = ++request;
    stop(); busy = true;
    const ready = await load(index);
    if (token !== request) return;
    busy = false;
    if (ready) {
      slides.forEach((photo, i) => {
        photo.classList.toggle('is-active', i === index);
        photo.setAttribute('aria-hidden', String(i !== index));
      });
      current = index;
      count.textContent = `${index + 1} / ${slides.length}`;
      count.setAttribute('aria-label', `전체 ${slides.length}장 중 ${index + 1}번째 사진`);
      caption.textContent = slides[index].dataset.caption;
      load((current + 1) % slides.length);
    } else {
      // A failed photo must not replace the last successfully displayed one.
      paused = true;
      updateToggle();
    }
    schedule();
  };
  const pause = () => {
    paused = true; ++request; busy = false; stop(); updateToggle();
  };
  const manual = (direction) => { pause(); show(current + direction); };
  previous.addEventListener('click', () => manual(-1));
  next.addEventListener('click', () => manual(1));
  // Pointer focus pauses the carousel before click; retain the user's original intent.
  toggle.addEventListener('pointerdown', () => { toggleIntent = !paused; });
  toggle.addEventListener('pointercancel', () => { toggleIntent = null; });
  toggle.addEventListener('click', () => {
    const shouldPause = toggleIntent === null ? !paused : toggleIntent;
    toggleIntent = null;
    if (shouldPause) pause();
    else { paused = false; updateToggle(); schedule(); }
  });
  root.addEventListener('pointerenter', event => {
    if (event.pointerType === 'mouse') { hovering = true; ++request; busy = false; stop(); }
  });
  root.addEventListener('pointerleave', event => {
    if (event.pointerType === 'mouse') { hovering = false; schedule(); }
  });
  root.addEventListener('focusin', event => {
    if (!root.contains(event.relatedTarget)) pause();
  });
  root.addEventListener('keydown', event => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault(); manual(event.key === 'ArrowLeft' ? -1 : 1);
    }
  });
  const visibilityChanged = () => {
    if (hidden()) { ++request; busy = false; stop(); }
    else schedule();
  };
  document.addEventListener('visibilitychange', visibilityChanged);
  mobile.addEventListener('change', visibilityChanged);
  new MutationObserver(visibilityChanged).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  motion.addEventListener('change', () => { if (motion.matches) pause(); });
  controls.hidden = false;
  updateToggle();
  load(0).then(() => { if (!hidden()) load(1); schedule(); });
})();
