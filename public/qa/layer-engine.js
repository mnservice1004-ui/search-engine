/* Temporary layer study: every cloud sample moves; fixed sky has no cloud photo patch. */
(() => {
  'use strict';
  const SPEED=.0023, PERIOD=.92, SUN=[.303,.510];
  const assetRoot='/qa/assets/';
  const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
  const mod=(v,n)=>((v%n)+n)%n;
  const shiftAt=t=>Math.max(0,t)*SPEED;
  const leafAngles=t=>Array.from({length:6},(_,i)=>.006*Math.sin(t*(.68+i*.061)+i*1.7)+.0015*Math.sin(t*1.37+i));
  let assetsPromise;
  function image(name){return new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('Asset load: '+name));i.src=assetRoot+name;});}
  function surface(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;return c;}
  function pixels(im,w,h){const c=surface(w,h),x=c.getContext('2d',{willReadFrequently:true});x.drawImage(im,0,0,w,h);return {canvas:c,data:x.getImageData(0,0,w,h)};}
  function box(src,w,h,r){
    const a=new Float32Array(w*h),b=new Float32Array(w*h);
    for(let y=0;y<h;y++){let sum=0;for(let x=0;x<=Math.min(w-1,r);x++)sum+=src[y*w+x];
      for(let x=0;x<w;x++){if(x>0){if(x+r<w)sum+=src[y*w+x+r];if(x-r-1>=0)sum-=src[y*w+x-r-1];}a[y*w+x]=sum/(Math.min(w-1,x+r)-Math.max(0,x-r)+1);}}
    for(let x=0;x<w;x++){let sum=0;for(let y=0;y<=Math.min(h-1,r);y++)sum+=a[y*w+x];
      for(let y=0;y<h;y++){if(y>0){if(y+r<h)sum+=a[(y+r)*w+x];if(y-r-1>=0)sum-=a[(y-r-1)*w+x];}b[y*w+x]=sum/(Math.min(h-1,y+r)-Math.max(0,y-r)+1);}}
    return b;
  }
  function refineForeground(photo,mask,w,h){
    // Guided alpha refinement follows photographed edges; no generated RGB replaces the foreground.
    const n=w*h,I=new Float32Array(n),P=new Float32Array(n),IP=new Float32Array(n),II=new Float32Array(n);
    const horizon=[[0,.70],[.14,.74],[.19,.72],[.32,.75],[.41,.75],[.48,.73],[.60,.76],[.70,.78],[.90,.79],[1,.79]];
    for(let j=0;j<n;j++){
      const x=(j%w)/w,y=Math.floor(j/w)/h,k=horizon.findIndex(p=>p[0]>=x),lo=horizon[Math.max(0,k-1)],hi=horizon[Math.max(0,k)];
      const ground=lo[1]+(hi[1]-lo[1])*(x-lo[0])/Math.max(.001,hi[0]-lo[0]);
      I[j]=(photo[j*4]*.2126+photo[j*4+1]*.7152+photo[j*4+2]*.0722)/255;
      // Car windows, signs and fence holes below the skyline are NOT transparent sky.
      P[j]=y>ground?1:mask[j*4]/255;IP[j]=I[j]*P[j];II[j]=I[j]*I[j];
    }
    const mi=box(I,w,h,6),mp=box(P,w,h,6),mip=box(IP,w,h,6),mii=box(II,w,h,6),a=new Float32Array(n),b=new Float32Array(n);
    for(let j=0;j<n;j++){a[j]=(mip[j]-mi[j]*mp[j])/(Math.max(0,mii[j]-mi[j]*mi[j])+.0006);b[j]=mp[j]-a[j]*mi[j];}
    const ma=box(a,w,h,6),mb=box(b,w,h,6),c=surface(w,h),ctx=c.getContext('2d'),out=ctx.createImageData(w,h);
    for(let j=0;j<n;j++){const v=Math.round(255*clamp(ma[j]*I[j]+mb[j]));out.data.set([v,v,v,255],j*4);}
    ctx.putImageData(out,0,0);return c;
  }
  function periodic(im){
    const w=im.width,h=im.height,overlap=Math.round(w*(1-PERIOD));
    const c=surface(w-overlap,h),ctx=c.getContext('2d',{willReadFrequently:true});
    ctx.drawImage(im,0,0);const img=ctx.getImageData(0,0,c.width,h),original=pixels(im,w,h).data.data;
    for(let y=0;y<h;y++)for(let x=0;x<overlap;x++){
      const mix=x/Math.max(1,overlap-1),j=(y*c.width+x)*4,k=(y*w+x)*4,z=(y*w+x+c.width)*4;
      for(let ch=0;ch<3;ch++)img.data[j+ch]=original[z+ch]*(1-mix)+original[k+ch]*mix;
    }
    ctx.putImageData(img,0,0);return c;
  }
  function assets(){if(!assetsPromise)assetsPromise=Promise.all(['sky.png','clouds-a-mask.png','clouds-b-mask.png','foreground-mask.png','original.jpg','detail.jpg','sky-sunset-v1.png'].map(image)).then(([sky,ca,cb,fg,original,detail,sunsetSky])=>{
    const w=1600,h=1200,p=pixels(original,w,h),m=pixels(fg,w,h),cloudA=periodic(ca),cloudB=periodic(cb);
    return {sky,sunsetSky,cloudA,cloudB,foreground:refineForeground(p.data.data,m.data.data,w,h),original,detail,
      densityA:pixels(cloudA,cloudA.width,cloudA.height).data.data,densityB:pixels(cloudB,cloudB.width,cloudB.height).data.data};
  });return assetsPromise;}
  const vertex=`attribute vec2 p;varying vec2 uv;void main(){uv=vec2((p.x+1.0)*.5,(1.0-p.y)*.5);gl_Position=vec4(p,0,1);}`;
  const fragment=`precision highp float;
    varying vec2 uv;uniform sampler2D sky,clouds,foreground,original,detail,sunsetSky;
    uniform float time,period,shift,variant,mode,refined;uniform vec2 coverSize,coverOffset;
    uniform float angles[6];
    vec2 rotateAbout(vec2 q,vec2 p,float a){vec2 d=q-p;return p+vec2(cos(a)*d.x-sin(a)*d.y,sin(a)*d.x+cos(a)*d.y);}
    vec2 branchUV(vec2 q){
      // Smooth overlapping branch weights; no rectangular cuts at group boundaries.
      vec2 d=vec2(0.);
      float w=(1.-smoothstep(.08,.15,q.x))*(1.-smoothstep(.58,.72,q.y));
      d+=(rotateAbout(q,vec2(.02,.69),angles[0])-q)*w;
      w=smoothstep(.06,.13,q.x)*(1.-smoothstep(.19,.25,q.x))*(1.-smoothstep(.62,.73,q.y));
      d+=(rotateAbout(q,vec2(.10,.72),angles[1])-q)*w;
      w=smoothstep(.47,.51,q.x)*(1.-smoothstep(.55,.59,q.x))*(1.-smoothstep(.66,.77,q.y));
      d+=(rotateAbout(q,vec2(.52,.76),angles[2])-q)*w;
      w=smoothstep(.54,.58,q.x)*(1.-smoothstep(.69,.73,q.x))*(1.-smoothstep(.66,.79,q.y));
      d+=(rotateAbout(q,vec2(.62,.78),angles[3])-q)*w;
      w=smoothstep(.70,.74,q.x)*(1.-smoothstep(.83,.88,q.x))*(1.-smoothstep(.75,.87,q.y));
      d+=(rotateAbout(q,vec2(.79,.86),angles[4])-q)*w;
      w=smoothstep(.84,.89,q.x)*(1.-smoothstep(.72,.88,q.y));
      d+=(rotateAbout(q,vec2(.96,.86),angles[5])-q)*w;
      return q+d;
    }
    // Lower-exposure source registered by sky SIFT. Only a luminance detail reference, not a fixed sun patch.
    vec3 originalCloudReference(vec2 q){
      vec3 p=texture2D(original,q).rgb;
      vec2 dst=q*vec2(4000.,3000.);
      // Matrix inverse calculated from recorded source-inventory homography.
      mat3 H=mat3(.6672391074,-.0093515486,-.0000050066401,-.0449201206,.6139988194,-.000023841677,645.3888436,889.7041677,1.);
      vec3 a=H[0],b=H[1],c=H[2];
      mat3 invH=mat3(cross(b,c),cross(c,a),cross(a,b));
      vec3 v=vec3(dot(invH[0],vec3(dst,1.)),dot(invH[1],vec3(dst,1.)),dot(invH[2],vec3(dst,1.)))/dot(a,cross(b,c));
      vec2 s=(v.xy/v.z)/vec2(4000.,3000.);
      float nearSun=(1.-smoothstep(.11,.19,distance(q,vec2(.303,.51))))*step(0.,s.x)*step(s.x,1.)*step(0.,s.y)*step(s.y,1.);
      return mix(p,texture2D(detail,s).rgb,nearSun);
    }
    void main(){
      vec2 q=coverOffset+uv*coverSize;
      // The clear-sky plate contains NO clouds. Registration corrects generated sun y=.549 to reference .510.
      vec3 back=texture2D(sky,clamp(q+vec2(0.,.039),0.,1.)).rgb;
      bool sunset=refined>.5&&variant<.5;
      if(sunset){
        // Register measured compact-disk centroid (.3102601,.56327264) to the SAME SUN (.303,.510).
        vec2 solarCenter=vec2(.303,.510),local=q-solarCenter;
        float radius=length(local*vec2(1.,.75));
        vec2 samplePoint=q;
        if(refined>1.5){
          // Double the solar DIAMETER, not the entire sky/halo or moving clouds.
          // Exactly 0.5 source scale in the core, smoothly return to identity by 78px at 1200px width.
          float localScale=mix(.5,1.,smoothstep(.035,.065,radius));
          samplePoint=solarCenter+local*localScale;
        }
        vec2 platePoint=clamp(samplePoint+vec2(.0072601,.05327264),0.,1.);
        back=texture2D(sunsetSky,platePoint).rgb;
        if(refined>1.5){
          // Small, bounded edge feather (~2 output pixels). No wide blur/glow field.
          vec2 feather=vec2(.0008,.0008/.75);
          vec3 softened=(back*4.
            +texture2D(sunsetSky,platePoint+vec2(feather.x,0.)).rgb
            +texture2D(sunsetSky,platePoint-vec2(feather.x,0.)).rgb
            +texture2D(sunsetSky,platePoint+vec2(0.,feather.y)).rgb
            +texture2D(sunsetSky,platePoint-vec2(0.,feather.y)).rgb)/8.;
          back=mix(back,softened,1.-smoothstep(.028,.04,radius));
        }
        if(refined>2.5){
          // Replace the clipped plate disk with a continuous light profile.
          // FWHM is ~50px at 1200px width (the selected 2x focal size), with no disk threshold.
          vec2 centerUV=solarCenter+vec2(.0072601,.05327264);
          vec3 ambient=(texture2D(sunsetSky,centerUV+vec2(.065,0.)).rgb
            +texture2D(sunsetSky,centerUV-vec2(.065,0.)).rgb
            +texture2D(sunsetSky,centerUV+vec2(0.,.065/.75)).rgb
            +texture2D(sunsetSky,centerUV-vec2(0.,.065/.75)).rgb)*.25;
          float focal=exp(-pow(radius/.025,2.));
          vec3 continuous=mix(ambient,vec3(1.,.977,.90),focal);
          // Eliminate both the white edge and the old narrow orange ring, without blurring cloud detail.
          back=mix(back,continuous,1.-smoothstep(.040,.078,radius));
          vec2 lightDistance=local*vec2(1.,.75)/vec2(.18,.115);
          float spread=exp(-dot(lightDistance,lightDistance))*(1.-smoothstep(.25,.30,radius));
          back=clamp(back+vec3(.095,.025,-.023)*spread*(1.-focal),0.,1.);
        }
        if(refined>3.5){
          // Hemisphere-scale skylight: no solar-radius cutoff. Keep blue zenith / clear gaps,
          // while a restrained rose-amber horizon continues through the RIGHT of the photograph.
          float horizonLight=smoothstep(.18,.72,q.y);
          float across=smoothstep(.30,.98,q.x);
          float protectCore=smoothstep(.045,.10,radius);
          back=clamp(back+mix(vec3(.048,.012,-.008),vec3(.075,.015,.018),across)
            *horizonLight*protectCore,0.,1.);
        }
      }
      vec2 cq=vec2(fract((q.x+shift)/period),q.y);
      float density=texture2D(clouds,cq).r;
      float tau=pow(clamp((density-.045)/.955,0.,1.),1.42)*3.5;
      float trans=exp(-tau),alpha=1.-trans;
      vec3 neutral=mix(vec3(.80,.825,.85),vec3(.45,.50,.55),pow(density,1.6));
      if(variant<.5){
        // Preserve measured original cloud microcontrast without carrying the source's solar glare along.
        vec2 src=vec2(mod(q.x+shift,period),q.y);
        vec3 observed=originalCloudReference(src);
        float lum=dot(observed,vec3(.2126,.7152,.0722));
        float local=dot(texture2D(original,clamp(src+vec2(.006,.006),0.,1.)).rgb,vec3(.2126,.7152,.0722));
        float fine=clamp((lum+.12)/(local+.12),.90,1.10);
        float suppress=max(1.-smoothstep(.10,.19,distance(src,vec2(.303,.51))),smoothstep(.02,.2,texture2D(foreground,src).r));
        suppress=max(suppress,max(1.-smoothstep(0.,.09,src.x),smoothstep(period-.09,period,src.x)));
        neutral*=mix(fine,1.,suppress);
      }
      // Forward illumination affects the MOVING cloud's own edges; there is no stationary cloud stencil.
      vec2 sunDelta=(q-vec2(.303,.510))*vec2(1.,.75);
      // A fidelity review: do not add a wide synthetic fog/glow field.
      // The existing generated sky plate remains under review; this is NOT proof of original fidelity.
      float glow=variant<.5?0.:exp(-dot(sunDelta,sunDelta)/.018);
      vec3 lit=mix(neutral,vec3(1.,.90,.66),glow*.44);
      lit+=vec3(.12,.095,.05)*glow*4.*trans*(1.-trans);
      vec3 radiance=back;
      if(sunset){
        // Warm only nearby moving clouds. No wide additive glow or fixed cloud cutout.
        float warm=1.-smoothstep(.035,.235,length(sunDelta));
        float rim=4.*trans*(1.-trans);
        vec3 warmCloud=neutral*vec3(1.12,1.015,.86);
        lit=mix(neutral,warmCloud,warm*.70);
        lit+=vec3(.13,.072,.018)*warm*rim;
        // Solar radiance is concentrated in the small disk, and still attenuated by the moving cloud alpha.
        float coreScale=refined>1.5?2.:1.;
        float core=smoothstep(.89,.98,min(back.r,min(back.g,back.b)))*(1.-smoothstep(.016*coreScale,.025*coreScale,length(sunDelta)));
        radiance+=vec3(.65,.60,.48)*core;
        if(refined>2.5){
          float radius=length(sunDelta);
          vec2 lightDistance=sunDelta/vec2(.20,.145);
          float spread=exp(-dot(lightDistance,lightDistance))*(1.-smoothstep(.25,.30,radius));
          // The same moving density field controls transmission, self-shadow and edge illumination.
          // No per-frame full-screen exposure pulse, static cloud patch or blur of the cloud texture.
          vec2 stepUV=vec2(.0025/period,.0025/.75);
          float edge=clamp((abs(density-texture2D(clouds,vec2(fract(cq.x+stepUV.x),cq.y)).r)
            +abs(density-texture2D(clouds,vec2(fract(cq.x-stepUV.x),cq.y)).r)
            +abs(density-texture2D(clouds,cq+vec2(0.,stepUV.y)).r)
            +abs(density-texture2D(clouds,cq-vec2(0.,stepUV.y)).r))*2.,0.,1.);
          float thick=smoothstep(.42,.90,density);
          float thin=4.*trans*(1.-trans);
          vec3 shade=neutral*mix(vec3(1.),vec3(.88,.92,1.),thick*spread*.55);
          lit=mix(shade,shade*vec3(1.20,1.015,.78),spread*.90);
          lit+=vec3(.24,.13,.035)*spread*(thin*.45+edge*.55)*(1.-thick*.65);
          lit-=vec3(.040,.026,.008)*spread*thick;
          // Smooth radiance, not a hard white threshold: passing clouds remain visible through the center.
          float focal=exp(-pow(radius/.025,2.));
          radiance=back+vec3(.38,.34,.24)*focal;
          if(refined>3.5){
            // Reference-driven cloud-sheet relighting, NOT a point lamp pasted over the sun.
            // This 2D density-gradient normal is an artistic approximation, not measured cloud geometry.
            float dx=texture2D(clouds,vec2(fract(cq.x+stepUV.x),cq.y)).r
              -texture2D(clouds,vec2(fract(cq.x-stepUV.x),cq.y)).r;
            float dy=texture2D(clouds,cq+vec2(0.,stepUV.y)).r
              -texture2D(clouds,cq-vec2(0.,stepUV.y)).r;
            vec3 normal=normalize(vec3(-dx*2.,-dy*2.,.40));
            float facing=max(0.,dot(normal,normalize(vec3(-.62,.26,.40))));
            float across=smoothstep(.30,.98,q.x);
            float altitude=mix(.62,1.,smoothstep(.02,.66,q.y));
            float illumination=clamp((.34+.58*facing+.20*thin)*(1.-thick*.72)*altitude,0.,1.);
            vec3 warmTint=mix(vec3(1.26,.99,.76),vec3(1.26,.88,.86),across);
            // Lit sides range honey/peach/rose; dense interiors retain blue-violet skylight.
            vec3 sheet=neutral*mix(vec3(.78,.80,.94),warmTint,illumination);
            // A small optical-thickness shadow keeps rosy dense clouds from becoming flat pastels.
            sheet*=1.-.065*thick;
            vec3 edgeLight=mix(vec3(.16,.095,.028),vec3(.16,.064,.055),across);
            sheet+=edgeLight*thin*edge*(.4+.6*facing)*altitude;
            // Preserve the enlarged soft solar focus, transition to all-sky light without an outer boundary.
            lit=mix(lit,sheet,smoothstep(.045,.10,radius));
          }
        }
      }
      vec3 color=radiance*trans+lit*alpha;
      vec2 fq=branchUV(q);float fa=texture2D(foreground,fq).r;
      vec3 fc=texture2D(original,fq).rgb;
      if(mode<.5){gl_FragColor=vec4(mix(color,fc,fa),1.);}
      else if(mode<1.5){gl_FragColor=vec4(back,1.);}
      else if(mode<2.5){gl_FragColor=vec4(clamp(lit,0.,1.),alpha);}
      else{gl_FragColor=vec4(fc,fa);}
    }`;
  function compile(gl,type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;}
  async function create(canvas,options={}){
    const a=await assets(),gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:false,antialias:false,preserveDrawingBuffer:true});
    if(!gl)throw new Error('WebGL unavailable; original remains available');
    const vs=compile(gl,gl.VERTEX_SHADER,vertex),fs=compile(gl,gl.FRAGMENT_SHADER,fragment),p=gl.createProgram();gl.attachShader(p,vs);gl.attachShader(p,fs);gl.linkProgram(p);
    if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));gl.useProgram(p);
    const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
    const pos=gl.getAttribLocation(p,'p');gl.enableVertexAttribArray(pos);gl.vertexAttribPointer(pos,2,gl.FLOAT,false,0,0);
    let variant=options.variant||'A',look=options.look||'legacy',layer=options.layer||'composite',lastTime=0,frames=0,disposed=false;
    const uniforms={};for(const name of ['time','period','shift','variant','mode','refined','coverSize','coverOffset','angles'])uniforms[name]=gl.getUniformLocation(p,name);
    const textureSlots=['sky','clouds','foreground','original','detail','sunsetSky'],textures=[];
    function upload(slot,im){gl.activeTexture(gl.TEXTURE0+slot);gl.bindTexture(gl.TEXTURE_2D,textures[slot]);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,false);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);}
    textureSlots.forEach((name,i)=>{textures.push(gl.createTexture());gl.activeTexture(gl.TEXTURE0+i);gl.bindTexture(gl.TEXTURE_2D,textures[i]);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.uniform1i(gl.getUniformLocation(p,name),i);upload(i,name==='clouds'?(variant==='A'?a.cloudA:a.cloudB):a[name]);});
    function draw(time,next={}){
      if(disposed||gl.isContextLost())throw new Error('Renderer unavailable');
      if(next.variant&&variant!==next.variant){variant=next.variant;upload(1,variant==='A'?a.cloudA:a.cloudB);}layer=next.layer||layer;look=next.look||look;
      lastTime=Math.max(0,Number(time)||0);
      const rect=canvas.getBoundingClientRect(),w=Math.max(1,Math.round(rect.width||800)),h=Math.max(1,Math.round(rect.height||600)),ratio=Math.min(window.devicePixelRatio||1,1.25,1800/w,Math.sqrt(1800000/(w*h)));
      if(canvas.width!==Math.round(w*ratio)||canvas.height!==Math.round(h*ratio)){canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);}
      gl.viewport(0,0,canvas.width,canvas.height);const scale=Math.max(w/4,h/3),size=[w/(scale*4),h/(scale*3)],offset=[(1-size[0])*(w<=760?.3:.5),(1-size[1])*.5];
      gl.uniform2fv(uniforms.coverSize,size);gl.uniform2fv(uniforms.coverOffset,offset);gl.uniform1f(uniforms.time,lastTime);gl.uniform1f(uniforms.period,PERIOD);gl.uniform1f(uniforms.shift,shiftAt(lastTime));gl.uniform1f(uniforms.variant,variant==='A'?0:1);gl.uniform1f(uniforms.mode,['composite','sky','clouds','foreground'].indexOf(layer));gl.uniform1fv(uniforms.angles,new Float32Array(leafAngles(lastTime)));
      gl.uniform1f(uniforms.refined,look==='sunset-wide'?4:look==='sunset-soft'?3:look==='sunset'?2:look==='sunset-small'?1:0);
      gl.drawArrays(gl.TRIANGLE_STRIP,0,4);frames++;
      Object.assign(canvas.dataset,{variant,look,layer,time:lastTime.toFixed(3),frames:String(frames),cloudDirection:'right-to-left',sun:'cloud-free-background',state:'rendered'});
    }
    function metrics(){const im=variant==='A'?a.cloudA:a.cloudB,data=variant==='A'?a.densityA:a.densityB,x=Math.floor(mod((SUN[0]+shiftAt(lastTime))/PERIOD,1)*im.width),y=Math.floor(SUN[1]*im.height),density=data[(y*im.width+x)*4]/255;return {variant,look,layer,time:lastTime,frames,cloudShift:shiftAt(lastTime),sunDensity:density,sunTransmission:Math.exp(-Math.pow(clamp((density-.045)/.955),1.42)*3.5),leafAngles:leafAngles(lastTime),source:'separate-density-and-cloud-free-sky',reconstructed:true};}
    function dispose(){disposed=true;textures.forEach(t=>gl.deleteTexture(t));gl.deleteBuffer(buffer);gl.deleteProgram(p);gl.deleteShader(vs);gl.deleteShader(fs);}
    draw(options.time||0);return {draw,metrics,dispose};
  }
  window.LayerLab={create,shiftAt,leafAngles,SUN,SPEED,PERIOD};
})();
