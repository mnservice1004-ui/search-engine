"""Rigid left-moving clouds and independent foliage, without business dependencies."""
import json
import subprocess
from pathlib import Path

SOURCE = Path('public/js/hero-atmosphere.js')


def run_node(body):
    program = "const assert=require('node:assert/strict'); const api=require('./public/js/hero-atmosphere.js');\n" + body
    result = subprocess.run(['node', '-e', program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_browser_entrypoint_initializes_motion_without_preview_opt_in():
    run_node('''
const vm=require('node:vm');
const source=require('node:fs').readFileSync('./public/js/hero-atmosphere.js','utf8');
for(const reduced of [false,true])for(const search of ['', '?revision=hero-atmosphere-5',
 '?background-preview', '?background-preview=', '?background-preview=true',
 '?background-preview=sun-restored', '?background-preview=wrong', '?background-preview=%zz']){
 const calls={initialization:0,factory:0,image:0,frames:0};
 function unexpected(name){calls[name]++;throw new Error('unexpected animation '+name);}
 const motion={matches:reduced,addEventListener(){}};
 const canvas={hidden:true,dataset:{},addEventListener(){},getContext(){unexpected('factory');}};
 const button={hidden:true,addEventListener(){}};
 let imageUrl=null;
 const sandbox={URLSearchParams,module:{exports:{}},
  document:{
   hidden:false,addEventListener(){},querySelectorAll:()=>[],
   getElementById(id){
    if(id==='hero-atmosphere')return canvas;
    if(id==='background-motion-toggle')return button;
    throw new Error('unexpected element '+id);
   },
   createElement(){unexpected('factory');}
  },
  window:{location:{search},addEventListener(){},
   matchMedia(query){calls.initialization++;assert.equal(query,'(prefers-reduced-motion: reduce)');return motion;},
   requestAnimationFrame(){unexpected('frames');}},
  Image:class{constructor(){calls.image++;}set src(value){imageUrl=value;}},
  MutationObserver:class{observe(){}disconnect(){}}
 };
 vm.runInNewContext(source,sandbox,{filename:'hero-atmosphere.js'});
 assert.equal(canvas.dataset.state,reduced?'reduced-motion':'loading',
   'ordinary home URLs must enter initialization without a preview query');
 assert.deepEqual(calls,{initialization:1,factory:0,image:reduced?0:1,frames:0},
   'default startup must respect reduced motion and wait for the photograph before rendering');
 assert.equal(imageUrl,reduced?null:'/images/hero-dongtan.jpg');
 assert.equal(canvas.hidden,true,'the CSS photograph must stay visible while its image is loading');
 assert.equal(button.hidden,true,'the motion control must wait until the renderer is ready');
}
''')


def test_browser_entrypoint_allows_pages_without_background_controls():
    run_node('''
const vm=require('node:vm');
const source=require('node:fs').readFileSync('./public/js/hero-atmosphere.js','utf8');
for(const present of [[],['hero-atmosphere'],['background-motion-toggle']]){
 const sandbox={module:{exports:{}},
  document:{getElementById(id){return present.includes(id)?{}:null;}},
  window:{matchMedia(){throw new Error('incomplete decoration must not initialize motion');}}
 };
 assert.doesNotThrow(()=>vm.runInNewContext(source,sandbox,{filename:'hero-atmosphere.js'}));
}
''')


def test_cloud_motion_is_uniformly_right_to_left_without_reversal():
    run_node('''
assert.equal(api.CLOUD_SPEED,.0028);
for(const t of [0,.1,1,5,30,100,400,1000,50000]){
 const a=api.sceneAt(t),b=api.sceneAt(t+.25);
 assert.ok(Math.abs(a.cloudX+t*api.CLOUD_SPEED)<1e-10);
 assert.ok(b.cloudX<a.cloudX,'clouds must never reverse or reset to the right');
 assert.ok(Math.abs(b.cloudX-a.cloudX+.25*api.CLOUD_SPEED)<1e-10);
}
const moved=(api.sceneAt(0).cloudX-api.sceneAt(5).cloudX)*1440;
assert.ok(moved>15&&moved<25,'five-second leftward travel must be visible but gentle');
''')


def test_scene_is_deterministic_with_finite_independent_leaf_rotations():
    run_node('''
for(const t of [0,1,35,180,50000,NaN,-1,Infinity]){
 const s=api.sceneAt(t);assert.deepEqual(s,api.sceneAt(t));
 assert.ok(Number.isFinite(s.time)&&s.time>=0&&Number.isFinite(s.cloudX));
 assert.equal(s.leafAngles.length,6);
 s.leafAngles.forEach((angle,i)=>{
  assert.ok(Number.isFinite(angle)&&Math.abs(angle)<=.014+1e-12);
  assert.equal(angle,api.leafMotionAt(s.time,i));
 });
}
assert.equal(api.FRAME_INTERVAL,1000/24);
''')


def test_leaf_sway_is_bounded_reversible_and_independent_of_cloud_motion():
    run_node('''
const signatures=[];
for(let i=0;i<6;i++){
 const angles=Array.from({length:1200},(_,k)=>api.leafMotionAt(k*.25,i));
 angles.forEach(a=>assert.ok(Number.isFinite(a)&&Math.abs(a)<=.014+1e-12));
 assert.ok(Math.max(...angles)-Math.min(...angles)>.002,'foliage must actually sway');
 const deltas=angles.slice(1).map((a,k)=>a-angles[k]);
 assert.ok(deltas.some(v=>v>0)&&deltas.some(v=>v<0),'leaves sway independently, not pan');
 signatures.push(JSON.stringify(angles.slice(0,25)));
}
assert.equal(new Set(signatures).size,6,'six canopy patches need independent phases');
const body=api.leafMotionAt.toString();
assert.ok(!/CLOUD_SPEED|cloudTileOffsets|cloudX|transmissionAt/.test(body));
''')


def test_cloud_tiles_cover_the_viewport_across_wrap_without_rightward_rewind():
    run_node('''
for(const period of [.6,1,1.25,1.8])for(const width of [.4,1,1.5]){
 const wrap=period/api.CLOUD_SPEED;
 for(const t of [0,.001,20,wrap-.02,wrap,wrap+.02,2*wrap,50*wrap+.1]){
  const offsets=api.cloudTileOffsets(t,period,width).slice().sort((a,b)=>a-b);
  if(width===1)assert.deepEqual(api.cloudTileOffsets(t,period),offsets);
  assert.ok(offsets.length>=1);
  offsets.forEach(x=>assert.ok(Number.isFinite(x)));
  assert.ok(offsets[0]<=1e-9&&offsets.at(-1)+period>=width-1e-9,'sky has an uncovered edge');
  for(let i=1;i<offsets.length;i++)assert.ok(Math.abs(offsets[i]-offsets[i-1]-period)<1e-8);
  const dt=.01,next=api.cloudTileOffsets(t+dt,period,width);
  for(const x of offsets){
   const expected=x-api.CLOUD_SPEED*dt;
   if(expected+period>1e-7&&expected<width-1e-7)
    assert.ok(next.some(n=>Math.abs(n-expected)<1e-8),'visible tile rewound or disappeared at wrap');
  }
 }
}
''')


def test_rigid_cloud_translation_preserves_internal_geometry():
    run_node('''
const points=[[.1,.1],[.43,.19],[.86,.48],[.99,.71]];
const base=points.map((p)=>[p[0]-points[0][0],p[1]-points[0][1]]);
for(const t of [0,20,100,1000]){
 const dx=api.sceneAt(t).cloudX,translated=points.map(([x,y])=>[x+dx,y]);
 translated.forEach((p,i)=>{
  assert.ok(Math.abs(p[0]-translated[0][0]-base[i][0])<1e-12);
  assert.equal(p[1]-translated[0][1],base[i][1]);
 });
}
assert.ok(!/Math\\.sin/.test(api.sceneAt.toString()),'cloud trajectory is not a sine-wave warp');
''')


def test_density_sampling_is_bilinear_periodic_and_clamps_vertical_edges():
    run_node('''
const field=new Float32Array([0,1,1,0]);
for(const u of [-2.3,-.01,0,.13,.25,.5,.75,.999,1,2.7]){
 const mid=api.sampleDensity(field,2,2,u,.5);
 assert.ok(Math.abs(mid-.5)<1e-7,'bilinear middle row must average opposite corners');
 for(const v of [-2,0,.13,.9,1,3]){
  const d=api.sampleDensity(field,2,2,u,v);
  assert.ok(d>=0&&d<=1);
  assert.ok(Math.abs(d-api.sampleDensity(field,2,2,u+3,v))<1e-7);
  assert.ok(Math.abs(d-api.sampleDensity(field,2,2,u,Math.max(0,Math.min(1,v))))<1e-7);
 }
}
for(const v of [0,.3,1])
 assert.ok(Math.abs(api.sampleDensity(field,2,2,-1e-7,v)-api.sampleDensity(field,2,2,1e-7,v))<1e-5);
for(const value of [0,.2,.6,1]){
 const constant=new Float32Array(12).fill(value);
 assert.ok(Math.abs(api.sampleDensity(constant,4,3,.375,.6)-value)<1e-7);
}
''')


def test_layer_preparation_contract_normalizes_donors_and_preserves_photo_sun():
    """Preparation contract only; actual browser frames establish visual quality."""
    run_node('''
assert.deepEqual(api.SUN,{x:.303,y:.510});
const build=api.buildLayers.toString().replace(/\\s+/g,'');
assert.ok(build.includes('cloudRatio(photo[k+c],lightData.data[k+c])'),
  'cloud texture must first remove the source location illumination');
assert.ok(build.indexOf('cloudContext.putImageData(cloudData,0,0)')<
  build.indexOf('replacementContext.drawImage(cloudSource,'),
  'donor transplantation must happen after photographic cloud normalization');
assert.ok(build.includes('replacementContext.drawImage(cloudSource,-dx*width,-dy*height)'),
  'patches must transplant normalized cloud texture');
assert.ok(!build.includes('replacementContext.drawImage(source,'),
  'raw donor illumination must not travel with a copied cloud patch');
assert.ok(build.includes('originalSunContext.drawImage(source,0,0)'),
  'the stationary sun core must retain pixels from the source photograph');
assert.ok(build.includes('originalSunContext.drawImage(originalSunMask,0,0)'));
assert.ok(build.includes('illuminationContext.drawImage(originalSun,0,0)'),
  'the photograph sun belongs to the fixed illumination');
const render=api.createRenderer.toString().replace(/\\s+/g,'');
assert.ok(!/createRadialGradient|addColorStop/.test(render),
  'runtime must not regenerate a replacement glow');
assert.ok(render.indexOf('ctx.drawImage(layers.fixed,0,0)')>
  render.indexOf('ctx.drawImage(leaf.canvas,'),
  'opaque fixed ground must cover the moving foliage root overlap');
''')


def test_cloud_ratio_reconstructs_both_dark_and_bright_photo_channels():
    run_node('''
for(const light of [0,1,15,16,32,89,128,190,240,254,255]){
 for(let photo=0;photo<=255;photo++){
  const ratio=api.cloudRatio(photo,light);
  assert.ok(Number.isFinite(ratio)&&ratio>=0&&ratio<=2,
    'cloud normalization needs a finite ratio even in dark source regions');
  const reconstructed=api.illuminatedChannel(light,ratio,0);
  if(light>=16&&photo<=2*light){
   assert.ok(Math.abs(reconstructed-photo)<1e-10,
     'multiplicative reconstruction must preserve darker as well as brighter cloud channels');
  }
  const stored=Math.round(ratio*127.5)/127.5;
  assert.ok(Math.abs(api.illuminatedChannel(light,stored,0)-reconstructed)<=1+1e-10,
    'two-sided cloud-ratio storage must remain within one output color level');
 }
}
assert.equal(api.cloudRatio(64,128),.5,'dark cloud detail must survive normalization');
assert.equal(api.cloudRatio(192,128),1.5,'bright cloud detail needs ratios above one');
for(const light of [16,64,128,200,255]){
 assert.equal(api.cloudRatio(light,light),1,'neutral cloud texture must multiply by one');
 assert.equal(api.illuminatedChannel(light,1,0),light);
 assert.equal(api.illuminatedChannel(light,1,1),light);
}
''')


def test_sun_core_keeps_94_percent_of_photo_light_and_bounds_brightening():
    run_node('''
for(const light of [0,16,64,128,192,240,255]){
 let previous=-1;
 for(let step=0;step<=200;step++){
  const ratio=step/100,value=api.illuminatedChannel(light,ratio,1);
  assert.ok(Number.isFinite(value)&&value>=.94*light-1e-10&&
    value<=Math.min(255,1.04*light)+1e-10,
    'passing clouds must retain the photographic sun without unbounded brightening');
  assert.ok(value>=previous-1e-10,'brighter cloud texture must not darken the sun');
  previous=value;
  const ordinary=api.illuminatedChannel(light,ratio,0);
  for(const weight of [.1,.3,.5,.8]){
   const blended=api.illuminatedChannel(light,ratio,weight);
   assert.ok(blended>=Math.min(ordinary,value)-1e-10&&
     blended<=Math.max(ordinary,value)+1e-10,
     'the sun boundary must interpolate without a brightness overshoot');
  }
 }
}
assert.equal(api.illuminatedChannel(200,0,1),188);
assert.equal(api.illuminatedChannel(200,2,1),208);
''')


def test_sky_sampling_contract_has_one_uniform_horizontal_shift_and_fixed_lighting():
    """Shader structure is a regression guard, not evidence of rendered motion."""
    run_node('''
const sky=api.createSkyRenderer.toString().replace(/\\s+/g,'');
assert.ok(sky.includes('texture2D(clouds,vec2(fract((uv.x-cloudX)/period),uv.y))'),
  'every cloud sample must use the same horizontal displacement and unchanged y');
assert.ok(sky.includes('texture2D(lighting,uv)'),
  'photographic illumination must stay in fixed image coordinates');
assert.ok(sky.includes('texture2D(sunMask,uv)'),
  'sun protection must stay at the original photographic coordinates');
assert.ok(sky.includes('floatsunContrast=clamp(dot(ratio,vec3(0.2126,0.7152,0.0722)),0.94,1.04)'),
  'sun modulation must use one bounded luminance ratio from the passing clouds');
assert.ok(sky.includes('ratio=mix(ratio,vec3(sunContrast),texture2D(sunMask,uv).a)'),
  'all sun-core color channels must share the same contrast to preserve photographic hue');
assert.ok(!/\\b(?:sin|cos)\\(/.test(sky),
  'the sky compositor must not distort cloud coordinates with a local wave');
''')


def test_sky_compositor_uploads_once_advances_only_shift_and_disposes_resources():
    """Exercise the GL interface without claiming mock pixels prove visual quality."""
    run_node('''
const calls={uploads:[],uniforms:[],draws:0,deleted:[]};
let contextLost=false,serial=0;
const gl={
 getShaderParameter:()=>true,getProgramParameter:()=>true,
 getAttribLocation:()=>0,getUniformLocation:(_,name)=>name,
 uniform1f(name,value){calls.uniforms.push([name,value]);},
 texImage2D(...args){calls.uploads.push(args.at(-1));},
 drawArrays(){calls.draws++;},isContextLost:()=>contextLost
};
for(const name of ['VERTEX_SHADER','FRAGMENT_SHADER','COMPILE_STATUS','LINK_STATUS',
 'ARRAY_BUFFER','STATIC_DRAW','FLOAT','TEXTURE0','TEXTURE_2D','UNPACK_FLIP_Y_WEBGL',
 'UNPACK_PREMULTIPLY_ALPHA_WEBGL','TEXTURE_MIN_FILTER','TEXTURE_MAG_FILTER','LINEAR',
 'TEXTURE_WRAP_S','TEXTURE_WRAP_T','CLAMP_TO_EDGE','RGBA','UNSIGNED_BYTE','TRIANGLE_STRIP'])gl[name]=++serial;
for(const name of ['Shader','Program','Buffer','Texture']){
 gl['create'+name]=()=>({kind:name,id:++serial});
 gl['delete'+name]=item=>calls.deleted.push(item);
}
for(const name of ['shaderSource','compileShader','attachShader','linkProgram','useProgram',
 'bindBuffer','bufferData','enableVertexAttribArray','vertexAttribPointer','activeTexture',
 'bindTexture','pixelStorei','texParameteri','uniform1i','viewport'])gl[name]=()=>{};
const canvas={getContext(kind){assert.equal(kind,'webgl');return gl;}};
global.document={createElement(name){assert.equal(name,'canvas');return canvas;}};
const layers={width:1600,height:1200,period:.9,sky:{id:'clouds'},
 illumination:{id:'photographic-light'},sunMask:{id:'fixed-sun-mask'}};
const renderer=api.createSkyRenderer(layers);
assert.deepEqual(calls.uploads,[layers.sky,layers.illumination,layers.sunMask]);
assert.deepEqual(calls.uniforms,[['period',.9]]);
const times=[0,5,30,.9/api.CLOUD_SPEED,.9/api.CLOUD_SPEED+.01];
for(const time of times)renderer.draw(time);
assert.equal(calls.draws,times.length);
assert.equal(calls.uploads.length,3,'animation must reuse prepared image textures');
assert.deepEqual(calls.uniforms.slice(1),times.map(t=>['cloudX',api.sceneAt(t).cloudX]),
 'frames must only advance a common horizontal shift');
contextLost=true;
assert.throws(()=>renderer.draw(31),/context lost/i,
 'offscreen GL context loss must reach the lifecycle static fallback');
assert.equal(calls.draws,times.length);
renderer.dispose();
assert.equal(calls.deleted.filter(item=>item.kind==='Texture').length,3);
assert.equal(calls.deleted.filter(item=>item.kind==='Shader').length,2);
assert.equal(calls.deleted.filter(item=>item.kind==='Buffer').length,1);
assert.equal(calls.deleted.filter(item=>item.kind==='Program').length,1);
assert.equal(canvas.width,0);assert.equal(canvas.height,0);
''')


def test_background_cover_geometry_preserves_photo_aspect_ratio():
    run_node('''
for(const [w,h] of [[1440,900],[1024,768],[390,844],[360,800],[720,450]]){
 const position=w<=760?.3:.5,c=api.coverGeometry(w,h,4000,3000,position);
 assert.ok(Math.abs(c.scale[0]*4000/(c.scale[1]*3000)-w/h)<1e-10);
 assert.ok(c.offset.every(v=>v>=0));
 assert.ok(c.scale.every(v=>v>0&&v<=1));
 assert.ok(Math.abs(c.offset[0]-(1-c.scale[0])*position)<1e-10);
}
''')


def test_background_is_layered_decorative_and_separate_from_business_ui():
    script=SOURCE.read_text(encoding='utf-8')
    html=Path('public/qa/home-modified-a.html').read_text(encoding='utf-8')
    css=Path('public/css/style.css').read_text(encoding='utf-8')
    assert '/qa/layer-engine.js?revision=a-whole-sky' in html
    assert '/qa/layer-home.js?revision=a-whole-sky' in html
    assert '/js/hero-atmosphere.js' not in html
    assert 'class="hero-atmosphere" aria-hidden="true" hidden' in html
    assert 'id="background-motion-toggle"' in html and 'aria-label="배경 움직임"' in html
    rule=css.split('.hero-atmosphere{',1)[1].split('}',1)[0]
    assert 'pointer-events:none' in rule and 'z-index:-1' in rule and 'position:fixed' in rule
    assert '.hero-atmosphere[hidden],.background-motion-toggle[hidden]{display:none}' in css
    assert 'prefers-reduced-motion:reduce){.hero-atmosphere,.background-motion-toggle{display:none!important}' in css
    assert '.translate(' in script and '.rotate(' in script and '.drawImage(' in script
    assert "getContext('2d'" in script
    assert not any(term in script for term in ['fetch(', '/api/', 'getUserMedia', 'eval(', 'localStorage', 'setInterval('])
    assert "image.src = '/images/hero-dongtan.jpg'" in script


HARNESS = '''
let requests=new Map(),serial=0,now=0,draws=0,imageLoads=0,factoryCalls=0,disposed=0,dialogOpen=false;
const events={},docEvents={},canvasEvents={},buttonEvents={},motionEvents={};
const motion={matches:REDUCED,addEventListener:(k,v)=>motionEvents[k]=v};
const canvas={dataset:{},hidden:true,addEventListener:(k,v)=>canvasEvents[k]=v};
const label={textContent:''};
const button={hidden:true,attrs:{},querySelector:()=>label,setAttribute(k,v){this.attrs[k]=v;},addEventListener:(k,v)=>buttonEvents[k]=v};
global.document={hidden:false,documentElement:{clientWidth:1440},
 querySelector:()=>dialogOpen?{}:null,querySelectorAll:()=>[{}],addEventListener:(k,v)=>docEvents[k]=v};
global.window={innerHeight:900,devicePixelRatio:2,matchMedia:()=>motion,
 requestAnimationFrame(fn){const id=++serial;requests.set(id,fn);return id;},
 cancelAnimationFrame(id){requests.delete(id);},addEventListener:(k,v)=>events[k]=v};
global.Image=class{constructor(){this.naturalWidth=4000;this.naturalHeight=3000;}
 set src(value){assert.equal(value,'/images/hero-dongtan.jpg');imageLoads++;if(IMAGE_FAIL)this.onerror();else this.onload();}};
let mutation;
global.MutationObserver=class{constructor(fn){mutation=fn;}observe(){}disconnect(){}};
function factory(target,image){
 factoryCalls++;assert.equal(target,canvas);assert.equal(image.naturalWidth,4000);
 if(FACTORY_FAIL)throw new Error('renderer unavailable');
 return {draw(seconds){if(DRAW_FAIL&&draws>2)throw new Error('draw unavailable');draws++;canvas.dataset.sceneTime=seconds.toFixed(3);},dispose(){disposed++;}};
}
function advance(frames){for(let i=0;i<frames;i++){
 now+=1000/60;const active=[...requests.values()];requests.clear();active.forEach(fn=>fn(now));
 assert.ok(requests.size<=1,'duplicate frame loop');
}}
api.initializeAtmosphere(canvas,button,factory);
'''


def run_lifecycle(assertions, *, reduced=False, factory_fail=False, image_fail=False, draw_fail=False):
    harness=HARNESS
    for key,value in {'REDUCED':reduced,'FACTORY_FAIL':factory_fail,'IMAGE_FAIL':image_fail,'DRAW_FAIL':draw_fail}.items():
        harness=harness.replace(key,json.dumps(value))
    run_node(harness+assertions)


def test_background_pause_visibility_dialog_and_frame_budget():
    run_lifecycle('''
assert.equal(canvas.dataset.state,'running');assert.equal(button.hidden,false);
assert.equal(button.attrs['aria-pressed'],'true');advance(61);assert.ok(draws<=26);
const before=canvas.dataset.sceneTime;buttonEvents.click();assert.equal(requests.size,0);
advance(60);assert.equal(canvas.dataset.sceneTime,before);assert.equal(label.textContent,'꺼짐');
buttonEvents.click();advance(5);assert.equal(requests.size,1);
document.hidden=true;docEvents.visibilitychange();assert.equal(requests.size,0);
document.hidden=false;docEvents.visibilitychange();advance(5);
dialogOpen=true;mutation();assert.equal(requests.size,0);
dialogOpen=false;mutation();advance(5);assert.equal(requests.size,1);
''')


def test_slow_frames_preserve_real_active_time_not_one_tenth_speed():
    run_lifecycle('''
advance(1);
const before=Number(canvas.dataset.sceneTime);
for(let i=0;i<12;i++){
 now+=1000;const active=[...requests.values()];requests.clear();active.forEach(fn=>fn(now));
}
assert.ok(Math.abs(Number(canvas.dataset.sceneTime)-before-12)<.002);
assert.equal(requests.size,1);
''')


def test_pauses_do_not_catch_up_hidden_or_dialog_time():
    run_lifecycle('''
advance(10);
for(const kind of ['button','hidden','dialog']){
 const before=Number(canvas.dataset.sceneTime);
 if(kind==='button')buttonEvents.click();
 if(kind==='hidden'){document.hidden=true;docEvents.visibilitychange();}
 if(kind==='dialog'){dialogOpen=true;mutation();}
 now+=120000;assert.equal(requests.size,0);
 if(kind==='button')buttonEvents.click();
 if(kind==='hidden'){document.hidden=false;docEvents.visibilitychange();}
 if(kind==='dialog'){dialogOpen=false;mutation();}
 advance(5);
 assert.ok(Number(canvas.dataset.sceneTime)-before<.2,'paused time leaked into scene');
}
''')


def test_reduced_motion_skips_renderer_and_can_change_live():
    run_lifecycle('''
assert.equal(factoryCalls,0);assert.equal(imageLoads,0);assert.equal(requests.size,0);
motion.matches=false;motionEvents.change();advance(3);
assert.equal(factoryCalls,1);assert.equal(canvas.hidden,false);
motion.matches=true;motionEvents.change();assert.equal(canvas.hidden,true);
assert.equal(button.hidden,true);assert.equal(requests.size,0);
motion.matches=false;motionEvents.change();assert.equal(factoryCalls,1);advance(3);
''', reduced=True)


def test_renderer_unavailable_keeps_static_background_without_frame_loop():
    run_lifecycle('''
assert.equal(canvas.hidden,true);assert.equal(button.hidden,true);
assert.equal(canvas.dataset.state,'static-fallback');assert.equal(requests.size,0);
''', factory_fail=True)


def test_image_failure_keeps_static_background_without_frame_loop():
    run_lifecycle('''
assert.equal(canvas.hidden,true);assert.equal(button.hidden,true);
assert.equal(canvas.dataset.state,'static-fallback');assert.equal(factoryCalls,0);
assert.equal(requests.size,0);
''', image_fail=True)


def test_draw_failure_keeps_static_background_without_frame_loop():
    run_lifecycle('''
advance(20);
assert.equal(canvas.hidden,true);assert.equal(button.hidden,true);
assert.equal(canvas.dataset.state,'static-fallback');assert.equal(requests.size,0);
''', draw_fail=True)


def test_page_lifecycle_disposes_and_restores_renderer_safely():
    run_lifecycle('''
advance(4);events.pagehide();assert.equal(requests.size,0);assert.equal(disposed,1);
events.pageshow({persisted:true});advance(4);assert.equal(requests.size,1);
assert.equal(imageLoads,2);assert.equal(factoryCalls,2);
''')


def test_canvas_context_loss_stays_static_after_visibility_events():
    run_lifecycle('''
advance(4);canvasEvents.contextlost();
assert.equal(canvas.hidden,true);assert.equal(button.hidden,true);
assert.equal(canvas.dataset.state,'static-fallback');assert.equal(requests.size,0);
document.hidden=true;docEvents.visibilitychange();
document.hidden=false;docEvents.visibilitychange();
assert.equal(canvas.hidden,true);assert.equal(requests.size,0);
assert.equal(canvas.dataset.state,'static-fallback','failed renderer must not be reported merely paused');
''')
