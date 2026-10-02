/* Independent photographic layers. Clouds translate rigidly right-to-left;
   transparent branch cutouts rotate about fixed pivots. No animated pixel warp. */
(() => {
  'use strict';
  const SUN = { x: 0.303, y: 0.510 };
  const CLOUD_SPEED = 0.0028;
  const FRAME_INTERVAL = 1000 / 24;
  const clamp = value => Math.max(0, Math.min(1, value));
  const mod = (value, period) => ((value % period) + period) % period;
  const activeSeconds = seconds => Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const CROWNS = [
    { pivot:[.012,.650], points:[[0,.363],[.038,.378],[.058,.395],[.082,.389],[.111,.420],[.116,.472],[.100,.496],[.127,.515],[.124,.568],[.137,.596],[.120,.645],[0,.656]] },
    { pivot:[.065,.664], points:[[.059,.568],[.135,.581],[.155,.607],[.179,.604],[.216,.630],[.208,.653],[.162,.680],[.075,.695]] },
    { pivot:[.545,.705], points:[[.480,.646],[.497,.584],[.523,.587],[.540,.622],[.555,.608],[.578,.650],[.570,.687],[.483,.688]] },
    { pivot:[.617,.752], points:[[.545,.650],[.568,.598],[.580,.556],[.613,.571],[.627,.605],[.654,.581],[.671,.625],[.707,.640],[.712,.687],[.668,.714],[.558,.721]] },
    { pivot:[.789,.810], points:[[.705,.699],[.719,.627],[.741,.605],[.749,.576],[.778,.567],[.822,.589],[.849,.620],[.869,.692],[.850,.764],[.740,.768]] },
    { pivot:[.951,.814], points:[[.854,.718],[.868,.672],[.897,.653],[.938,.663],[.973,.653],[1,.676],[1,.782],[.886,.780]] },
  ];
  function leafMotionAt(seconds, index) {
    const t = activeSeconds(seconds), i = mod(index, CROWNS.length);
    return .0055 * Math.sin(t * (.74 + i * .067) + i * 1.73)
      + .0016 * Math.sin(t * (1.41 + i * .083) + i * .61);
  }
  function sceneAt(seconds) {
    const time = activeSeconds(seconds);
    return { time, cloudX: -time * CLOUD_SPEED, leafAngles:CROWNS.map((_, i) => leafMotionAt(time, i)) };
  }
  function cloudTileOffsets(seconds, period, width = 1) {
    if (!(period > 0) || !(width > 0)) return [];
    const start = -mod(activeSeconds(seconds) * CLOUD_SPEED, period), positions = [];
    for (let x = start; x < width; x += period) positions.push(x);
    return positions;
  }
  function sampleDensity(density, width, height, u, v) {
    const x = mod(u, 1) * width, y = clamp(v) * (height - 1);
    const x0 = Math.floor(x), x1 = (x0 + 1) % width, y0 = Math.floor(y), y1 = Math.min(height - 1, y0 + 1);
    const ax = x - x0, ay = y - y0;
    const upper = density[y0 * width + x0] * (1 - ax) + density[y0 * width + x1] * ax;
    const lower = density[y1 * width + x0] * (1 - ax) + density[y1 * width + x1] * ax;
    return clamp(upper * (1 - ay) + lower * ay);
  }
  function cloudRatio(photo, illumination) {
    return Math.max(0, Math.min(2, photo / Math.max(16, illumination)));
  }
  function illuminatedChannel(illumination, ratio, sunWeight) {
    const guarded = Math.max(.94, Math.min(1.04, ratio));
    return Math.max(0, Math.min(255, illumination * (ratio * (1 - sunWeight) + guarded * sunWeight)));
  }
  function coverGeometry(width, height, imageWidth, imageHeight, positionX = .5) {
    const scale = Math.max(width / imageWidth, height / imageHeight);
    const uvScale = [width / (imageWidth * scale), height / (imageHeight * scale)];
    return { scale:uvScale, offset:[(1 - uvScale[0]) * positionX, (1 - uvScale[1]) * .5] };
  }
  function inside(x, y, points) {
    let result = false;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const a = points[i], b = points[j];
      if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) result = !result;
    }
    return result;
  }
  function horizonAt(x) {
    const points = [[0,.652],[.14,.690],[.188,.674],[.239,.680],[.319,.704],[.371,.713],[.413,.706],[.452,.677],[.479,.665],[.532,.666],[.570,.702],[.70,.704],[.90,.731],[1,.720]];
    for (let i = 1; i < points.length; i++) if (x <= points[i][0]) {
      const a = points[i - 1], b = points[i];
      return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]);
    }
    return .72;
  }
  function surface(width, height) {
    const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
    return canvas;
  }
  function buildLayers(image) {
    // Preparation happens ONCE in memory; original JPEG bytes are never rewritten.
    const width = Math.min(1600, image.naturalWidth), height = Math.round(image.naturalHeight * width / image.naturalWidth);
    const source = surface(width, height), sourceContext = source.getContext('2d', {willReadFrequently:true});
    sourceContext.drawImage(image, 0, 0, width, height);
    const photo = sourceContext.getImageData(0, 0, width, height).data;
    // Preserve the photograph's stationary illumination and golden sunlight.
    // Only cloud contrast/texture moves; no animated coordinate deformation.
    const illumination = surface(width, height), illuminationContext = illumination.getContext('2d', {willReadFrequently:true});
    illuminationContext.filter = 'blur(65px)';
    illuminationContext.drawImage(source, -100, -100, width + 200, height + 200);
    illuminationContext.filter = 'none';
    const originalSunMask = surface(width, height), originalSunMaskContext = originalSunMask.getContext('2d');
    originalSunMaskContext.translate(SUN.x * width, SUN.y * height);
    originalSunMaskContext.scale(width * .105, height * .105);
    const sunFeather = originalSunMaskContext.createRadialGradient(0, 0, 0, 0, 0, 1);
    sunFeather.addColorStop(0, 'white'); sunFeather.addColorStop(.60, 'white'); sunFeather.addColorStop(1, 'rgba(255,255,255,0)');
    originalSunMaskContext.fillStyle = sunFeather; originalSunMaskContext.fillRect(-1, -1, 2, 2);
    const originalSun = surface(width, height), originalSunContext = originalSun.getContext('2d');
    originalSunContext.drawImage(source, 0, 0);
    originalSunContext.globalCompositeOperation = 'destination-in'; originalSunContext.drawImage(originalSunMask, 0, 0);
    illuminationContext.drawImage(originalSun, 0, 0);
    const lightData = illuminationContext.getImageData(0, 0, width, height);
    const cloudSource = surface(width, height), cloudContext = cloudSource.getContext('2d');
    const cloudData = cloudContext.createImageData(width, height);
    for (let k = 0; k < photo.length; k += 4) {
      for (let c = 0; c < 3; c++) cloudData.data[k + c] = Math.round(127.5 * cloudRatio(photo[k + c], lightData.data[k + c]));
      cloudData.data[k + 3] = 255;
    }
    // Keep lighting opaque: transparent canvas RGB would be lost to premultiplication.
    cloudContext.putImageData(cloudData, 0, 0);
    const fixedSkyMask = surface(width, height), fixedSkyContext = fixedSkyMask.getContext('2d');
    fixedSkyContext.fillStyle = 'white';
    const fixed = surface(width, height), fixedContext = fixed.getContext('2d'), fixedData = fixedContext.createImageData(width, height);
    const foliage = CROWNS.map(crown => {
      const xs = crown.points.map(p => p[0]), ys = crown.points.map(p => p[1]);
      const x = Math.max(0, Math.floor(Math.min(...xs) * width)), y = Math.max(0, Math.floor(Math.min(...ys) * height));
      const w = Math.min(width - x, Math.ceil(Math.max(...xs) * width) - x + 1), h = Math.min(height - y, Math.ceil(Math.max(...ys) * height) - y + 1);
      const canvas = surface(w, h), context = canvas.getContext('2d');
      return {canvas, context, pixels:context.createImageData(w, h), x, y, pivot:[crown.pivot[0] * width, crown.pivot[1] * height]};
    });
    const groundYs = Array.from({length:width}, (_, x) => horizonAt(x / width) * height);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const u = x / width, v = y / height, id = y * width + x, k = id * 4;
      const maximum = Math.max(photo[k], photo[k + 1], photo[k + 2]);
      const dark = clamp((97 - maximum) / 34);
      const ground = y >= groundYs[x];
      const group = y < groundYs[x] + 7 ? CROWNS.findIndex(crown => inside(u, v, crown.points)) : -1;
      const alpha = ground ? 1 : group >= 0 ? dark : (v > .60 && maximum < 70 ? dark : 0);
      if (!alpha) continue;
      // Thin fixed objects above the horizon (including the crane) must not
      // survive in the moving sky as a second, drifting copy.
      if (!ground && group < 0 && alpha > .15 && x % 2 === 0 && y % 2 === 0) fixedSkyContext.fillRect(x - 16, y - 16, 33, 33);
      if (ground || group < 0) {
        fixedData.data[k] = photo[k]; fixedData.data[k + 1] = photo[k + 1]; fixedData.data[k + 2] = photo[k + 2];
        fixedData.data[k + 3] = Math.round(alpha * 255);
      }
      if (group >= 0) {
        const leaf = foliage[group], dest = ((y - leaf.y) * leaf.canvas.width + x - leaf.x) * 4;
        leaf.pixels.data[dest] = photo[k]; leaf.pixels.data[dest + 1] = photo[k + 1]; leaf.pixels.data[dest + 2] = photo[k + 2];
        leaf.pixels.data[dest + 3] = Math.round(dark * 255);
      }
    }
    fixedContext.putImageData(fixedData, 0, 0);
    foliage.forEach(leaf => { leaf.context.putImageData(leaf.pixels, 0, 0); delete leaf.pixels; delete leaf.context; });
    // Separate the sky from silhouettes with feathered photographic patches.
    // Source patches come from the unobstructed upper sky; never copy another tree.
    // These masks affect only static asset preparation, NOT runtime displacement.
    const skyBase = surface(width, height), skyBaseContext = skyBase.getContext('2d');
    skyBaseContext.drawImage(cloudSource, 0, 0);
    function patch(mask, dx, dy) {
      const softened = surface(width, height), softContext = softened.getContext('2d');
      softContext.filter = 'blur(12px)'; softContext.drawImage(mask, 0, 0); softContext.filter = 'none';
      const replacement = surface(width, height), replacementContext = replacement.getContext('2d');
      replacementContext.drawImage(cloudSource, -dx * width, -dy * height);
      replacementContext.globalCompositeOperation = 'destination-in';
      replacementContext.drawImage(softened, 0, 0);
      skyBaseContext.drawImage(replacement, 0, 0);
    }
    function crownMask(indices) {
      const mask = surface(width, height), context = mask.getContext('2d');
      context.fillStyle = 'white'; context.strokeStyle = 'white'; context.lineWidth = 28; context.lineJoin = 'round';
      indices.forEach(i => {
        context.beginPath(); CROWNS[i].points.forEach((p, n) => n ? context.lineTo(p[0] * width, p[1] * height) : context.moveTo(p[0] * width, p[1] * height));
        context.closePath(); context.fill(); context.stroke();
      });
      return mask;
    }
    patch(crownMask([0, 1]), .22, -.29);
    patch(crownMask([2, 3, 4, 5]), 0, -.40);
    patch(fixedSkyMask, 0, -.40);
    const groundMask = surface(width, height), groundContext = groundMask.getContext('2d');
    groundContext.fillStyle = 'white'; groundContext.beginPath();
    groundContext.moveTo(0, height);
    for (let x = 0; x <= width; x += 4) groundContext.lineTo(x, horizonAt(x / width) * height + 2);
    groundContext.lineTo(width, height); groundContext.closePath(); groundContext.fill();
    patch(groundMask, 0, -.40);
    const sunMask = surface(width, height), sunContext = sunMask.getContext('2d');
    sunContext.translate(SUN.x * width, SUN.y * height); sunContext.scale(width * .16, height * .155);
    const feather = sunContext.createRadialGradient(0, 0, 0, 0, 0, 1);
    feather.addColorStop(0, 'white'); feather.addColorStop(.66, 'white'); feather.addColorStop(1, 'rgba(255,255,255,0)');
    sunContext.fillStyle = feather; sunContext.fillRect(-1, -1, 2, 2);
    patch(sunMask, .16, -.22);
    const skyPixels = skyBaseContext.getImageData(0, 0, width, height).data;
    // Bake a short overlap ONCE into a periodic strip. Runtime motion is uniform
    // everywhere, including screen edges, lower sky, and the sun's surroundings.
    const overlap = Math.round(width * .10), periodPixels = width - overlap;
    const sky = surface(periodPixels, height), skyContext = sky.getContext('2d'), skyData = skyContext.createImageData(periodPixels, height);
    const density = new Float32Array(periodPixels * height);
    for (let y = 0; y < height; y++) {
      let low = 255, high = 0;
      for (let x = 0; x < periodPixels; x++) {
        const dest = (y * periodPixels + x) * 4, src = (y * width + x) * 4;
        const amount = x < overlap ? x / overlap : 1, other = (y * width + x + periodPixels) * 4;
        for (let c = 0; c < 3; c++) skyData.data[dest + c] = Math.round(skyPixels[src + c] * amount + (amount < 1 ? skyPixels[other + c] * (1 - amount) : 0));
        skyData.data[dest + 3] = 255;
        const light = .2126 * skyData.data[dest] + .7152 * skyData.data[dest + 1] + .0722 * skyData.data[dest + 2];
        density[y * periodPixels + x] = light; low = Math.min(low, light); high = Math.max(high, light);
      }
      for (let x = 0; x < periodPixels; x++) density[y * periodPixels + x] = clamp((density[y * periodPixels + x] - low) / Math.max(35, high - low));
    }
    skyContext.putImageData(skyData, 0, 0);
    return {width, height, sky, illumination, sunMask:originalSunMask, fixed, foliage, density, period:periodPixels / width};
  }
  function createSkyRenderer(layers) {
    const canvas = surface(layers.width, layers.height), gl = canvas.getContext('webgl', {alpha:false, antialias:false, preserveDrawingBuffer:true});
    if (!gl) throw new Error('Sky compositor unavailable');
    function shader(type, code) {
      const item = gl.createShader(type); gl.shaderSource(item, code); gl.compileShader(item);
      if (!gl.getShaderParameter(item, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(item));
      return item;
    }
    const vertex = shader(gl.VERTEX_SHADER, 'attribute vec2 p; varying vec2 uv; void main(){ uv=(p+1.0)*0.5; gl_Position=vec4(p,0.0,1.0); }');
    const fragment = shader(gl.FRAGMENT_SHADER, `precision highp float; varying vec2 uv;
      uniform sampler2D clouds; uniform sampler2D lighting; uniform sampler2D sunMask; uniform float cloudX; uniform float period;
      void main(){
        vec3 ratio=texture2D(clouds,vec2(fract((uv.x-cloudX)/period),uv.y)).rgb*2.0;
        vec4 light=texture2D(lighting,uv);
        float sunContrast=clamp(dot(ratio,vec3(0.2126,0.7152,0.0722)),0.94,1.04);
        ratio=mix(ratio,vec3(sunContrast),texture2D(sunMask,uv).a);
        gl_FragColor=vec4(clamp(light.rgb*ratio,0.0,1.0),1.0);
      }`);
    const program = gl.createProgram(); gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,1,1]), gl.STATIC_DRAW);
    const attribute = gl.getAttribLocation(program, 'p'); gl.enableVertexAttribArray(attribute); gl.vertexAttribPointer(attribute, 2, gl.FLOAT, false, 0, 0);
    const textures = [layers.sky, layers.illumination, layers.sunMask].map((source, i) => {
      const texture = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + i); gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true); gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source); return texture;
    });
    gl.uniform1i(gl.getUniformLocation(program, 'clouds'), 0); gl.uniform1i(gl.getUniformLocation(program, 'lighting'), 1);
    gl.uniform1i(gl.getUniformLocation(program, 'sunMask'), 2);
    gl.uniform1f(gl.getUniformLocation(program, 'period'), layers.period);
    const shift = gl.getUniformLocation(program, 'cloudX'); gl.viewport(0, 0, canvas.width, canvas.height);
    return {canvas, draw(seconds) { if (gl.isContextLost()) throw new Error('Sky context lost'); gl.uniform1f(shift, sceneAt(seconds).cloudX); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); },
      dispose() { textures.forEach(t => gl.deleteTexture(t)); gl.deleteBuffer(buffer); gl.deleteProgram(program); gl.deleteShader(vertex); gl.deleteShader(fragment); canvas.width = canvas.height = 0; }};
  }
  function createRenderer(canvas, image) {
    const ctx = canvas.getContext('2d', {alpha:false});
    if (!ctx) throw new Error('Canvas unavailable');
    const layers = buildLayers(image);
    const skyRenderer = createSkyRenderer(layers);
    let dimensions = [0, 0], scale = 1, crop = null;
    function resize() {
      const width = document.documentElement.clientWidth, height = window.innerHeight;
      const factor = Math.min(window.devicePixelRatio || 1, 1.25, 1600 / width, Math.sqrt(1600000 / (width * height)));
      canvas.width = Math.max(1, Math.round(width * factor)); canvas.height = Math.max(1, Math.round(height * factor));
      crop = coverGeometry(width, height, layers.width, layers.height, width <= 760 ? .3 : .5);
      scale = Math.max(width / layers.width, height / layers.height) * factor;
      dimensions = [width, height];
    }
    function draw(seconds) {
      if (dimensions[0] !== document.documentElement.clientWidth || dimensions[1] !== window.innerHeight) resize();
      const scene = sceneAt(seconds);
      ctx.setTransform(scale, 0, 0, scale, -crop.offset[0] * layers.width * scale, -crop.offset[1] * layers.height * scale);
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
      // Whole-sky translation: no pixel offsets, animated scaling, or vertical motion.
      skyRenderer.draw(seconds); ctx.drawImage(skyRenderer.canvas, 0, 0);
      layers.foliage.forEach((leaf, i) => {
        ctx.save(); ctx.translate(leaf.pivot[0], leaf.pivot[1]); ctx.rotate(scene.leafAngles[i]);
        ctx.drawImage(leaf.canvas, leaf.x - leaf.pivot[0], leaf.y - leaf.pivot[1]); ctx.restore();
      });
      // Cover the small branch-root overlap with fixed ground, preventing a gap.
      ctx.drawImage(layers.fixed, 0, 0);
      canvas.dataset.sceneTime = seconds.toFixed(3); canvas.dataset.cloudX = scene.cloudX.toFixed(6);
      canvas.dataset.cloudDirection = 'right-to-left';
      canvas.dataset.leafAngles = scene.leafAngles.map(a => a.toFixed(5)).join(',');
      canvas.dataset.sunTransmission = '0.94–1.04 achromatic';
      canvas.dataset.sunSource = 'original-photograph'; canvas.dataset.renderer = 'independent-rigid-layers';
    }
    return {draw, dispose() { skyRenderer.dispose(); [layers.sky, layers.illumination, layers.sunMask, layers.fixed, ...layers.foliage.map(leaf => leaf.canvas)].forEach(layer => { layer.width = 0; layer.height = 0; }); }};
  }
  function initializeAtmosphere(canvas, button, rendererFactory = createRenderer) {
    if (!canvas || !button) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let renderer = null, loading = false, failed = false, userPaused = false;
    let frame = null, lastTick = null, lastDraw = -Infinity, elapsed = 0, frames = 0;
    const canRun = () => renderer && !failed && !userPaused && !motion.matches && !document.hidden && !document.querySelector('dialog[open]');
    function stop() { if (frame !== null) window.cancelAnimationFrame(frame); frame = null; lastTick = null; }
    function fail() { stop(); failed = true; canvas.hidden = true; button.hidden = true; canvas.dataset.state = 'static-fallback'; }
    function tick(now) {
      frame = null;
      if (!canRun()) { sync(); return; }
      if (lastTick !== null) elapsed += Math.max(0, (now - lastTick) / 1000);
      lastTick = now;
      if (now - lastDraw >= FRAME_INTERVAL) {
        try { renderer.draw(elapsed); } catch { fail(); return; }
        canvas.dataset.frames = String(++frames);
        lastDraw = Number.isFinite(lastDraw) ? now - ((now - lastDraw) % FRAME_INTERVAL) : now;
      }
      frame = window.requestAnimationFrame(tick);
    }
    function sync() {
      stop(); canvas.hidden = !renderer || failed || motion.matches; button.hidden = !renderer || failed || motion.matches;
      button.setAttribute('aria-pressed', String(!userPaused)); button.querySelector('span').textContent = userPaused ? '꺼짐' : '켜짐';
      canvas.dataset.state = failed ? 'static-fallback' : canRun() ? 'running' : 'paused'; if (canRun()) frame = window.requestAnimationFrame(tick);
    }
    function load() {
      if (loading || renderer || failed || motion.matches) return;
      loading = true; const image = new Image(); image.decoding = 'async';
      image.onload = () => {
        loading = false; if (motion.matches) return;
        try { renderer = rendererFactory(canvas, image); renderer.draw(elapsed); sync(); } catch { fail(); }
      };
      image.onerror = fail; image.src = '/images/hero-dongtan.jpg';
    }
    button.addEventListener('click', () => { userPaused = !userPaused; sync(); });
    motion.addEventListener('change', () => { if (!motion.matches) load(); sync(); });
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('resize', () => { if (renderer && !failed) { try { renderer.draw(elapsed); } catch { fail(); } } });
    const dialogs = new MutationObserver(sync);
    document.querySelectorAll('dialog').forEach(dialog => dialogs.observe(dialog, {attributes:true, attributeFilter:['open']}));
    canvas.addEventListener('contextlost', fail);
    window.addEventListener('pagehide', () => { stop(); dialogs.disconnect(); if (renderer) renderer.dispose(); renderer = null; });
    window.addEventListener('pageshow', event => {
      if (!event.persisted) return;
      document.querySelectorAll('dialog').forEach(dialog => dialogs.observe(dialog, {attributes:true, attributeFilter:['open']})); load(); sync();
    });
    canvas.dataset.state = motion.matches ? 'reduced-motion' : 'loading'; load();
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {sceneAt, leafMotionAt, cloudTileOffsets, sampleDensity, cloudRatio, illuminatedChannel, coverGeometry, SUN, CLOUD_SPEED, FRAME_INTERVAL, initializeAtmosphere, buildLayers, createSkyRenderer, createRenderer};
  if (typeof document !== 'undefined') {
    const canvas = document.getElementById('hero-atmosphere'), button = document.getElementById('background-motion-toggle');
    initializeAtmosphere(canvas, button);
  }
})();
