"""Execute the actual shared marker projection, independent of task ID/route."""
import json
import subprocess
from pathlib import Path


def test_all_22_printed_labels_project_to_bottom_center_at_any_image_size():
    script = Path('public/js/app.js').read_text(encoding='utf-8')
    source = 'function syncMarkerToImage' + script.split('function syncMarkerToImage', 1)[1].split('function syncRouteOverlayToImage', 1)[0]
    points = json.loads(Path('data/map_points.json').read_text(encoding='utf-8'))
    program = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const ir={left:93.4,top:144.7,width:768,height:0};
const sr={left:70.2,top:121.3,width:810,height:1000};
const c={markerEl:{style:{}},floorImageEl:{naturalWidth:2560,naturalHeight:1709,getBoundingClientRect:()=>ir},
 mapStageEl:{getBoundingClientRect:()=>sr},mapPanelEl:{getBoundingClientRect:()=>sr},
 guidanceGridEl:{style:{setProperty(k,v){this[k]=v;}}},
 getComputedStyle:()=>({borderLeftWidth:'0.8px',borderTopWidth:'0.8px',height:'84px'})};
vm.createContext(c);vm.runInContext(p.source,c);
let targets=0;
for(const [floor,entries] of Object.entries(p.points)) {
 c.floorImageEl.naturalHeight={'1층':1709,'2층':2000,'3층':1933}[floor];
 for(const point of Object.values(entries)) {
  if(!point.label_bbox || point.alias_of)continue;
  targets++;
  for(const width of [180,234,264,520,768,1400]) {
   ir.width=width;ir.height=width*c.floorImageEl.naturalHeight/2560;
   for(const padding of [0,16,26,100]) {
    ir.left=sr.left+padding+.8;
   assert.equal(c.syncMarkerToImage(point),true,JSON.stringify({floor,point,natural:c.floorImageEl.naturalHeight}));
    const actualX=sr.left+.8+Number.parseFloat(c.markerEl.style.left);
    const actualBottom=sr.top+.8+Number.parseFloat(c.markerEl.style.top);
    assert.ok(Math.abs(actualX-(ir.left+(point.label_bbox.left+point.label_bbox.width/2)*width/2560))<1e-9);
    assert.ok(Math.abs(ir.top+point.label_bbox.top*width/2560-actualBottom-6)<1e-9);
   }
  }
 }
}
assert.equal(targets,22);
assert.equal(c.syncMarkerToImage(p.points['3층']['소회의실']),false);
assert.equal(c.syncMarkerToImage({label_bbox:{left:0,top:0,width:0,height:5}}),false);
assert.equal(c.syncMarkerToImage({label_bbox:{left:0,top:0,width:3000,height:5}}),false);
ir.width=0;assert.equal(c.syncMarkerToImage(p.points['1층']['민원실']),false);
'''
    result = subprocess.run(['node','-e',program],input=json.dumps({'source':source,'points':points}),capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


def test_no_floating_placard_and_marker_cannot_be_clipped_by_map_border():
    html=Path('public/index.html').read_text(encoding='utf-8')
    css=Path('public/css/style.css').read_text(encoding='utf-8')
    script=Path('public/js/app.js').read_text(encoding='utf-8')
    assert 'id="map-label"' not in html
    assert 'mapLabelEl' not in script and '#map-label' not in css
    assert 'transform:translate(-50%,-100%);transform-origin:50% 100%' in css
    assert "center bottom/contain no-repeat" in css
    assert '#map-marker.arrived{animation:none}' in css
    assert '#map-marker.arrived .map-runner-sprite{animation:runner-dance 2s ease-in-out infinite}' in css
    assert '@keyframes runner-dance' in css
    assert 'markerHeight * 1.15 + 6' in script
    assert '.map-panel{position:sticky;top:12px;overflow:visible}' in css
    stage=css.split('.map-stage.map-cropped{--v26-left:',1)[1].split('}',1)[0]
    assert 'overflow:visible' in stage
    assert 'visibleMarkerPoint = null;' in script.split('function hideMapLocation()',1)[1].split('function setMapControlsHidden',1)[0]
    assert "guidanceGridEl.style.removeProperty('--marker-overhang');" in script
    assert '.guidance-grid{padding-top:var(--marker-overhang,0px)}' in css
    assert 'if (detailDialogEl.open && visibleMarkerPoint) syncMarkerToImage(visibleMarkerPoint);' in script
    assert 'id="route-text"' in html  # accessible location is not the removed placard


def test_runner_body_axis_and_dance_are_independent_of_the_map_anchor():
    from hashlib import sha256
    css=Path('public/css/style.css').read_text(encoding='utf-8')
    html=Path('public/index.html').read_text(encoding='utf-8')
    assert sha256(Path('public/images/runner.png').read_bytes()).hexdigest() == '1bb5a37f33aa14957b7d8687660d3a36a6301e3dda2a6d34e46d3061798ee2de'
    assert 'class="map-runner"><span class="map-runner-sprite"' in html
    assert '--runner-body-axis:40.1634723788%' in css
    assert 'aspect-ratio:887/980' in css
    assert 'translateX(calc(-1 * var(--runner-body-axis)))' in css
    assert 'transform-origin:var(--runner-body-axis) 100%' in css
    assert '8%{transform:translateY(-7%) rotate(-8deg)}' in css
    assert '16%{transform:translateY(3%) rotate(8deg)}' in css
    assert '24%{transform:translateY(-4%) rotate(-5deg)}' in css
    assert '@media(prefers-reduced-motion:reduce){#map-marker.arrived .map-runner-sprite{animation:none}}' in css
    # Body-axis correction uses one bitmap measurement for ALL destinations.
    for height in (69,84):
        width=height*887/980
        offset=-width*40.1634723788/100
        projected_body_axis=offset+width*356.25/887
        assert abs(projected_body_axis)<1e-9
