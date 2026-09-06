/* Temporary homepage adapter. No production JS, search, map, or SMS changes. */
(() => {
  'use strict';
  const canvas=document.getElementById('hero-atmosphere');
  const toggle=document.getElementById('background-motion-toggle');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const requestedLook=new URLSearchParams(location.search).get('look');
  const look=['legacy','sunset-small','sunset','sunset-soft'].includes(requestedLook)?requestedLook:'sunset-wide';
  // Keep A and 3.5x; the previous appearance remains available with ?look=legacy.
  const policy=Object.freeze({preferredVariant:'A',playbackRate:3.5,animationApproved:true,
    decision:'ANIMATED_A',reason:'USER_SELECTED_A_3_5',look,source:'/images/hero-dongtan.jpg'});
  window.heroBackgroundPolicy=policy;
  const variant=policy.preferredVariant;
  if(!policy.animationApproved){
    canvas.hidden=true;toggle.hidden=true;
    Object.assign(canvas.dataset,{state:'original-static',variant,requestedSpeed:String(policy.playbackRate),frames:'0',reason:policy.reason});
    const link=document.createElement('a');link.href='/qa/compare.html';
    link.textContent='원본 정지 배경 사용 중 · 배경 비교 화면';
    link.style.cssText='display:inline-block;color:inherit;margin:8px 16px;text-decoration:underline;font-size:14px';
    toggle.after(link);window.heroLayerReady=true;return;
  }
  let renderer,enabled=true,time=0,last=0,drawn=0;
  canvas.dataset.playbackRate=String(policy.playbackRate);
  function sync(){
    const playing=enabled&&!reduced.matches;
    toggle.hidden=false;toggle.setAttribute('aria-pressed',String(playing));
    toggle.querySelector('span').textContent=playing?'켜짐':'꺼짐';
    canvas.hidden=!playing;
  }
  function tick(now){
    const delta=last?Math.min((now-last)/1000,.2):0;last=now;
    const live=enabled&&!reduced.matches&&!document.hidden&&!document.querySelector('dialog[open]');
    if(live){time+=delta*policy.playbackRate;if(now-drawn>=1000/24){renderer.draw(time);canvas.dataset.state='running';drawn=now;}}
    else canvas.dataset.state='paused';
    requestAnimationFrame(tick);
  }
  toggle.addEventListener('click',()=>{enabled=!enabled;sync();});
  reduced.addEventListener('change',sync);
  window.LayerLab.create(canvas,{variant,look}).then(r=>{
    renderer=r;window.heroLayerRenderer=r;sync();requestAnimationFrame(tick);
    const a=document.createElement('a');a.href='/qa/sunset-compare.html?revision=a-whole-sky';a.textContent=`${look==='sunset-wide'?'하늘 전체의 석양빛':'이전'} ${variant}안 · ${policy.playbackRate}배속 · 비교 화면`;
    a.style.cssText='display:inline-block;color:inherit;margin:8px 16px;text-decoration:underline;font-size:14px';
    toggle.after(a);window.heroLayerReady=true;
  }).catch(error=>{canvas.hidden=true;toggle.hidden=true;window.heroLayerError=String(error);console.error(error);});
})();
