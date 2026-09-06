(() => {
  'use strict';
  const DURATION = 180;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const state = { ready: false, playing: !reduced.matches, time: 0, speed: 3.5, layer: 'composite', error: null };
  const renderers = {};
  const $ = (id) => document.getElementById(id);
  const play = $('sunset-play');
  const reset = $('sunset-reset');
  const timeline = $('sunset-timeline');
  const select = $('sunset-layer');
  const status = $('sunset-status');
  let lastTick = null;
  let lastPaint = -Infinity;
  let frameId = 0;
  let lastStatus = '';
  window.sunsetQAReady = false;
  window.sunsetQAError = null;
  window.sunsetQAState = state;
  window.sunsetRenderers = renderers;
  window.sunsetQAMetrics = {};

  function clock(value) {
    const seconds = Math.floor(Math.max(0, Math.min(DURATION, value)));
    return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }
  function updateControls() {
    const ended = state.time >= DURATION;
    play.textContent = state.playing ? 'Ⅱ 일시 정지' : ended ? '▶ 다시 재생' : '▶ 재생';
    play.setAttribute('aria-pressed', String(state.playing));
    play.setAttribute('aria-label', state.playing ? '두 A안 동시에 일시 정지' : '두 A안 동시에 재생');
    timeline.value = String(state.time);
    timeline.setAttribute('aria-valuetext', `${state.time.toFixed(1)}초 / 180초`);
    $('sunset-time').value = `${clock(state.time)} / 03:00`;
    const message = state.error ? `시안을 표시하지 못했습니다: ${state.error}`
      : !state.ready ? '원본과 두 A안 레이어를 준비하고 있습니다.'
        : ended ? '3분 비교가 끝났습니다. 다시 재생하거나 원하는 시간을 선택해 주세요.'
          : state.playing ? '기존 A · 수정 A 동기 재생 중 — 3.5배속'
            : '두 A안 일시 정지 — 시간 막대로 같은 순간을 비교할 수 있습니다.';
    if (message !== lastStatus) { status.textContent = message; lastStatus = message; }
  }
  function draw() {
    for (const look of ['legacy', 'sunset']) {
      renderers[look]?.draw(state.time, { look:look==='legacy'?'sunset-soft':'sunset-wide', layer: state.layer });
      if (renderers[look]) window.sunsetQAMetrics[look] = renderers[look].metrics();
    }
    for (const label of document.querySelectorAll('[data-layer-label]')) {
      label.textContent = state.layer === 'sky' ? '하늘·태양 레이어' : '전체 합성';
    }
    updateControls();
  }
  function frame(now) {
    if (lastTick === null) lastTick = now;
    const elapsed = (now - lastTick) / 1000;
    lastTick = now;
    if (state.ready && state.playing && !document.hidden) {
      state.time = Math.min(DURATION, state.time + elapsed * state.speed);
      if (state.time >= DURATION) state.playing = false;
      if (!state.playing || now - lastPaint >= 1000 / 24) { draw(); lastPaint = now; }
    }
    frameId = window.requestAnimationFrame(frame);
  }
  play.addEventListener('click', () => {
    if (!state.ready) return;
    if (state.time >= DURATION) state.time = 0;
    state.playing = !state.playing;
    lastTick = null;
    draw();
  });
  reset.addEventListener('click', () => { state.time = 0; lastTick = null; draw(); });
  timeline.addEventListener('input', () => {
    state.time = Math.max(0, Math.min(DURATION, Number(timeline.value)));
    state.playing = false;
    lastTick = null;
    draw();
  });
  select.addEventListener('change', () => { state.layer = select.value; draw(); });
  reduced.addEventListener('change', (event) => {
    if (event.matches) { state.playing = false; lastTick = null; updateControls(); }
  });
  document.addEventListener('visibilitychange', () => { lastTick = null; });
  window.addEventListener('resize', () => { if (state.ready) draw(); });
  window.addEventListener('pagehide', () => { window.cancelAnimationFrame(frameId); });
  window.addEventListener('pageshow', (event) => { if (event.persisted) { lastTick = null; frameId = window.requestAnimationFrame(frame); } });

  async function boot() {
    try {
      if (!window.LayerLab?.create) throw new Error('레이어 렌더러를 불러오지 못했습니다.');
      [renderers.legacy, renderers.sunset] = await Promise.all([
        window.LayerLab.create($('sunset-legacy'), { variant: 'A', look: 'sunset-soft', time: 0 }),
        window.LayerLab.create($('sunset-refined'), { variant: 'A', look: 'sunset-wide', time: 0 }),
      ]);
      await $('sunset-original').decode();
      state.ready = true;
      for (const control of [play, reset, timeline, select]) control.disabled = false;
      draw();
      window.sunsetQAReady = true;
      frameId = window.requestAnimationFrame(frame);
    } catch (error) {
      state.error = error instanceof Error ? error.message : String(error);
      window.sunsetQAError = state.error;
      state.playing = false;
      updateControls();
      console.error('Sunset comparison initialization failed', error);
    }
  }
  boot();
})();
