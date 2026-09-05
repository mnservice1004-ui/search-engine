"""Exercise the real result-card click handler with a cached floor image."""

import json
import subprocess
from pathlib import Path
import math
import pytest


def test_cached_floor_route_is_measured_after_dialog_opens():
    script = Path("public/js/app.js").read_text(encoding="utf-8")
    handler = script.split("function renderResults(items) {", 1)[1].split(
        "async function runSearch(", 1
    )[0]
    program = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const cards = [];
const dialog = {open: false, showModal() { this.open = true; }};
function element(tag, className, text) {
  return {
    tag, className, text, dataset: {}, children: [], events: {},
    classList: { add() {}, remove() {} },
    setAttribute() {}, appendChild(child) { this.children.push(child); },
    addEventListener(name, handler) { this.events[name] = handler; }
  };
}
const measured = [];
const context = {
  createText: element,
  clearChildren() { cards.length = 0; },
  resultsEl: {appendChild(card) { cards.push(card); }},
  document: {querySelectorAll() { return cards; }},
  state: {}, detailDialogEl: dialog,
  showDetail(task) {
    // A cached image has no new load event. This synchronous layout read is
    // exactly where a closed dialog used to make the route disappear.
    const imageWidth = dialog.open ? 720 : 0;
    assert.ok(imageWidth > 0, 'route measured in a closed dialog');
    measured.push(task.room || task.place);
  },
};
vm.createContext(context);
vm.runInContext(SOURCE, context);
const tasks = Array.from({length: 7}, (_, index) => ({
  id: `synthetic-${index}`, floor: '1층', room: '민원실', place: '민원실',
  name: `result-${index}`, show_map: true
}));
context.renderResults(tasks);
for (let pass = 0; pass < 3; pass++) {
  for (const card of cards) {
    dialog.open = false;
    card.events.click();
  }
}
assert.equal(measured.length, 21);
assert.ok(measured.every(place => place === '민원실'));
'''
    import json

    program = program.replace(
        "SOURCE", json.dumps("function renderResults(items) {" + handler)
    )
    result = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def _inside_polygon(x, y, polygon):
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) != (b[1] > y):
            crossing = a[0] + (y-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if x < crossing:
                inside = not inside
    return inside


@pytest.mark.parametrize('destination,endpoint,count', [
    ('검사실', (566,1082), 9),
    ('방사선실', (615,465), 15),
    ('결핵실', (765,444), 15),
    ('통합건강증진실', (2248,1356), 5),
])
def test_four_destinations_follow_surveyed_corridors_to_door(destination, endpoint, count):
    data = json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    floor = data['floors']['1층']
    route = floor['routes'][destination]
    assert route['status'] == 'VERIFIED'
    assert route['waypoint_ids'][0] == data['render_contract']['route_start_waypoint']
    points = [floor['waypoints'][key] for key in route['waypoint_ids']]
    assert len(points) == count
    assert all(p['status'] == 'VERIFIED' for p in points)
    pixels = [(p['highres_pixel']['x'],p['highres_pixel']['y']) for p in points]
    assert pixels[0] == (1756,1535)
    assert pixels[-1] == endpoint
    assert points[-1]['point_type'] == 'destination_approach'
    for p, (x,y) in zip(points,pixels):
        assert p['x'] == pytest.approx(x/2560*100, abs=1e-7)
        assert p['y'] == pytest.approx(y/1709*100, abs=1e-7)
    assert route['max_stroke_width_percent'] == 0.78125
    polygons = list(floor['route_survey_20260905']['corridor_regions'].values())
    # Sample the continuous line and its maximum stroke footprint, not only dashes.
    # Pixel-level blue-tile/wall checks additionally run in the raster QA script.
    radius = route['max_stroke_width_percent']/100*2560/2
    for a,b in zip(pixels,pixels[1:]):
        steps=math.ceil(math.dist(a,b))
        for step in range(steps+1):
            x=a[0]+(b[0]-a[0])*step/steps
            y=a[1]+(b[1]-a[1])*step/steps
            for angle in range(0,360,45):
                xx=x+radius*math.cos(math.radians(angle))
                yy=y+radius*math.sin(math.radians(angle))
                assert any(_inside_polygon(xx,yy,poly) for poly in polygons), (destination,xx,yy)


def test_four_destination_names_use_shared_routes_without_task_id_lists():
    script=Path('public/js/app.js').read_text(encoding='utf-8')
    source='function getDisplayedMapTarget'+script.split('function getDisplayedMapTarget',1)[1].split('function showCorridorRoute',1)[0]
    routes=json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    points=json.loads(Path('data/map_points.json').read_text(encoding='utf-8'))
    program=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const c={state:{corridorRoutes:p.routes}};vm.createContext(c);vm.runInContext(p.source,c);
for(const [names,canonical] of [
 [['검사실','1층 검사실'],'검사실'],
 [['방사선실','영상의학실','영상의학실(방사선실)'],'방사선실'],
 [['결핵실','1층 결핵실'],'결핵실'],
 [['통합건강증진실','통합건강 증진실'],'통합건강증진실']]) {
 for(const name of names) for(let index=0;index<12;index++) {
  const task={id:'arbitrary-'+index,room:name,place:'민원실',floor:'1층'};
  const target=c.getDisplayedMapTarget(task);
  const point=c.getMapPointForTarget(p.points['1층'],target);
  const route=c.getCorridorRoute(task.floor,point.printed_label);
  assert.equal(route,p.routes.floors['1층'].routes[canonical]);
  assert.equal(route.status,'VERIFIED');
  const d=c.createMapRoutePath(route.waypoint_ids.map(key=>p.routes.floors['1층'].waypoints[key]));
  assert.match(d,/^M 68\.59 89\.82 L /);
  assert.ok(!/[CQSA]/i.test(d));
 }
}
// Service title alone must never override the destination displayed on the card.
for(const name of ['결핵 검사','골다공증 검사','방사선 검사']) {
 const task={name,room:'민원실',place:'영상의학실'};
 assert.equal(c.getDisplayedMapTarget(task),'민원실');
 const point=c.getMapPointForTarget(p.points['1층'],c.getDisplayedMapTarget(task));
 assert.equal(c.getCorridorRoute('1층',point.printed_label),p.routes.floors['1층'].routes['민원실']);
}
'''
    result=subprocess.run(['node','-e',program],input=json.dumps({'source':source,'routes':routes,'points':points}),capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


def test_previous_verified_routes_and_unverified_upper_destinations_stay_intact():
    routes=json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    assert Path('data/corridor_routes.json').read_bytes() == Path('public/data/corridor_routes.json').read_bytes()
    floor=routes['floors']['1층']
    expected={
      '민원실':[(1756,1535),(1756,855),(1710,855)],
      '정신건강복지센터':[(1756,1535),(1756,1145),(2219,1145),(2219,1384)],
      '재활보건실':[(1756,1535),(1756,472),(1640,472),(1640,414)]}
    for name,pixels in expected.items():
        route=floor['routes'][name]
        actual=[floor['waypoints'][key]['highres_pixel'] for key in route['waypoint_ids']]
        assert [(p['x'],p['y']) for p in actual] == pixels
    for name,targets in {'3층':['소회의실']}.items():
        for target in targets:
            route=routes['floors'][name]['routes'][target]
            assert route['status']=='REVIEW_REQUIRED' and not route['waypoint_ids']
            assert route['reason']


@pytest.mark.parametrize('floor,target,endpoint,count', [
    ('2층','만성질환관리센터',(740,1250),7),
    ('2층','금연상담실',(870,545),16),
    ('2층','화성시장애아동재활센터',(1340,558),16),
    ('2층','대강당',(2050,1528),7),
    ('3층','건강증진과',(530,1015),9),
    ('3층','건강증진과 과장실',(493,1134),7),
    ('2층','운동실',(568,740),13),
    ('2층','운동지도실',(689.5,550),16),
    ('3층','보건행정과',(704,650+(383-650)*19/(1183-685)),14),
])
def test_upper_floor_route_uses_independent_start_and_corridor_footprint(floor,target,endpoint,count):
    data=json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    registry=data['floors'][floor]
    route=registry['routes'][target]
    assert route['status']=='VERIFIED'
    assert route['waypoint_ids'][0]==registry['route_start_waypoint']
    assert registry['route_start_waypoint']!=data['render_contract']['route_start_waypoint']
    points=[registry['waypoints'][key] for key in route['waypoint_ids']]
    assert len(points)==count
    assert points[0]['point_type']=='floor_transition'
    assert points[-1]['point_type']=='destination_approach'
    assert all(p['status']=='VERIFIED' and p['floor']==floor for p in points)
    pixels=[(p['highres_pixel']['x'],p['highres_pixel']['y']) for p in points]
    assert pixels[0]==({'2층':(1371,1660),'3층':(1320,1580)}[floor])
    assert pixels[-1]==endpoint
    w,h=registry['route_survey_20260905']['natural_size']
    assert (w,h)==(2560,2000 if floor=='2층' else 1933)
    assert route['max_stroke_width_percent']==0.625
    for p,(x,y) in zip(points,pixels):
        assert p['x']==pytest.approx(x/w*100)
        assert p['y']==pytest.approx(y/h*100)
    polygons=list(registry['route_survey_20260905']['corridor_regions'].values())
    for a,b in zip(pixels,pixels[1:]):
        steps=math.ceil(math.dist(a,b))
        for step in range(steps+1):
            x=a[0]+(b[0]-a[0])*step/steps
            y=a[1]+(b[1]-a[1])*step/steps
            for angle in range(0,360,45):
                xx=x+8*math.cos(math.radians(angle));yy=y+8*math.sin(math.radians(angle))
                assert any(_inside_polygon(xx,yy,poly) for poly in polygons),(target,xx,yy)


def test_manager_route_ends_at_user_marked_entrance_without_moving_marker():
    data=json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    floor=data['floors']['3층']
    route=floor['routes']['건강증진과 과장실']
    approach=floor['waypoints'][route['waypoint_ids'][-1]]
    assert approach['confirmation_type']=='user_marked_entrance'
    assert approach['source_reference']=='3층의 건강증진과 과장실 입구지점.png'
    assert approach['source_sha256']=='0c533088f4ad1569bf1d28e95f2249a95c5f3f347efbc6418f652857bec8db25'
    assert approach['highres_pixel']=={'x':493,'y':1134}
    assert route['waypoint_ids'][:6]==floor['routes']['건강증진과']['waypoint_ids'][:6]
    survey=floor['route_survey_20260905']['manager_door_confirmation']
    assert survey['inliers']>=200 and survey['median_error']<1
    point=json.loads(Path('data/map_points.json').read_text(encoding='utf-8'))['3층']['건강증진과 과장실']
    assert approach['x']!=point['x'] or approach['y']!=point['y']


def test_letter_approaches_face_requested_glyph_without_entering_rooms():
    data=json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    for floor,name,letter in [('2층','운동실','동'),('2층','운동지도실','지'),('3층','보건행정과','행')]:
        f=data['floors'][floor];r=f['routes'][name]
        assert r['traversal_policy']=='corridor_only'
        assert not r.get('authorized_boundary_crossings') and not r.get('department_transit_regions')
        assert r['letter_reference']['letter']==letter
        a,b=[f['waypoints'][k]['highres_pixel'] for k in r['waypoint_ids'][-2:]]
        gx,gy=r['letter_reference']['center']
        dx,dy=b['x']-a['x'],b['y']-a['y']
        assert abs(dx*(gy-b['y'])-dy*(gx-b['x']))<1e-7
        assert dx*(gx-b['x'])+dy*(gy-b['y'])>0
        assert math.dist((b['x'],b['y']),(gx,gy))>100
        assert r['verification_summary']['unapproved_wall_pixels']==0
    assert data['floors']['3층']['routes']['소회의실']['status']=='REVIEW_REQUIRED'
    point=json.loads(Path('data/map_points.json').read_text(encoding='utf-8'))['3층']['소회의실']
    assert point['x'] is None and point['y'] is None


def test_only_director_route_can_cross_authorized_administration_boundary():
    data=json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    f=data['floors']['3층'];r=f['routes']['보건소장실']
    assert r['traversal_policy']=='user_authorized_department_transit'
    assert r['waypoint_ids'][0]==f['route_start_waypoint']
    pp=[f['waypoints'][k]['highres_pixel'] for k in r['waypoint_ids']]
    pixels=[(p['x'],p['y']) for p in pp]
    assert pixels[0]==(1320,1580) and pixels[-1]==(823,440) and len(pixels)==19
    assert len(r['authorized_boundary_crossings'])==1
    assert r['authorized_boundary_crossings'][0]['department']=='보건행정과'
    assert r['verification_summary']['authorized_boundary_crossings']==1
    assert '보건행정과 내부를 경유' in r['display_notice']
    allowed=list(f['route_survey_20260905']['corridor_regions'].values())+[f['route_survey_20260905']['authorized_department_regions'][k] for k in r['department_transit_regions']]
    for a,b in zip(pixels,pixels[1:]):
        steps=math.ceil(math.dist(a,b))
        for step in range(steps+1):
            x=a[0]+(b[0]-a[0])*step/steps;y=a[1]+(b[1]-a[1])*step/steps
            for angle in range(0,360,45):
                xx=x+8*math.cos(math.radians(angle));yy=y+8*math.sin(math.radians(angle))
                assert any(_inside_polygon(xx,yy,p) for p in allowed),(xx,yy)
    for floor,registry in data['floors'].items():
        for name,other in registry['routes'].items():
            if (floor,name)==('3층','보건소장실'):continue
            assert not other.get('authorized_boundary_crossings')
            assert not other.get('department_transit_regions')
    script=Path('public/js/app.js').read_text(encoding='utf-8')
    assert 'corridorRoute.display_notice' in script


def test_upper_shared_destinations_and_fail_closed_route_transitions():
    script=Path('public/js/app.js').read_text(encoding='utf-8')
    source='function getDisplayedMapTarget'+script.split('function getDisplayedMapTarget',1)[1].split('function resetMap',1)[0]
    data=json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    points=json.loads(Path('data/map_points.json').read_text(encoding='utf-8'))
    program=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
let displayed=false,d=null;
const c={state:{corridorRoutes:p.routes,mapSelectionToken:1},
 routeEl:{dataset:{},classList:{remove(){displayed=false},add(){displayed=true}}},
 routeLineEl:{removeAttribute(){d=null},setAttribute(k,v){d=v}},
 isValidMapPoint(q){return q&&Number.isFinite(q.x)&&Number.isFinite(q.y)&&q.x>=0&&q.x<=100&&q.y>=0&&q.y<=100},
 syncRouteOverlayToImage(){return true}};
vm.createContext(c);vm.runInContext(p.source,c);
for(const floor of ['1층','2층','3층']) for(const [target,point] of Object.entries(p.points[floor])) {
 if(!point.printed_label||point.alias_of)continue;
 const route=c.getCorridorRoute(floor,point.printed_label);if(!route)continue;
 for(const name of [target,floor+' '+target])for(let n=0;n<3;n++){
  const task={id:'any-future-id-'+n,room:name,place:'irrelevant'};
  const resolved=c.getMapPointForTarget(p.points[floor],c.getDisplayedMapTarget(task));
  assert.equal(resolved,point);
  const result=c.showCorridorRoute(route,floor,1);
  assert.equal(result,route.status==='VERIFIED',floor+target);
  assert.equal(displayed,result);
  if(result){assert.match(d,/^M /);assert.ok(!/[CQS]/.test(d));}
  else assert.equal(d,null);
 }
}
const good=p.routes.floors['2층'].routes['금연상담실'];
function reject(route,floor='2층',token=1){assert.equal(c.showCorridorRoute(good,'2층',1),true);assert.equal(c.showCorridorRoute(route,floor,token),false);assert.equal(displayed,false);assert.equal(d,null)}
reject({...good,waypoint_ids:['entrance_door_threshold',...good.waypoint_ids.slice(1)]});
reject({...good,waypoint_ids:[good.waypoint_ids[0],'missing',...good.waypoint_ids.slice(1)]});
reject({...good,status:'REVIEW_REQUIRED'});reject(good,'3층');reject(good,'2층',0);
const registry=p.routes.floors['2층'];const middle=registry.waypoints[good.waypoint_ids[1]];
middle.status='REVIEW_REQUIRED';assert.equal(c.showCorridorRoute(good,'2층',1),false);middle.status='VERIFIED';
middle.floor='1층';assert.equal(c.showCorridorRoute(good,'2층',1),false);middle.floor='2층';
delete registry.route_start_waypoint;assert.equal(c.showCorridorRoute(good,'2층',1),false);
'''
    result=subprocess.run(['node','-e',program],input=json.dumps({'source':source,'routes':data,'points':points}),capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_route_overlay_resynchronizes_after_image_reflow_without_moving_waypoints():
    script = Path("public/js/app.js").read_text(encoding="utf-8")
    source = "function syncRouteOverlayToImage" + script.split(
        "function syncRouteOverlayToImage", 1
    )[1].split("function isValidMapPoint", 1)[0]
    program = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
let resized;
let borderWidth=1;
const rect = {left: 95, top: 132, width: 769, height: 513};
const image = {getBoundingClientRect() {return rect;}};
let observed;
const style = {setProperty(name,value) {this[name]=value;}};
const context = {
  visibleMarkerPoint: null,
  getComputedStyle() {return {borderLeftWidth:borderWidth+'px',borderTopWidth:borderWidth+'px'};},
  floorImageEl: image,
  mapStageEl: {clientLeft: 1, clientTop: 1, getBoundingClientRect() {return {left:75,top:115,width:809,height:630};}},
  routeEl: {style, classList: {contains() {return true;}}},
  detailDialogEl: {open: true},
  ResizeObserver: class {constructor(callback) {resized=callback;} observe(target) {observed=target;}}
};
vm.createContext(context);
vm.runInContext(payload.source, context);
assert.equal(observed,image);
resized();
assert.equal(style.left,'19px');
assert.equal(style.top,'16px');
assert.equal(style.width,'769px');
borderWidth=0.571429;
resized();
assert.ok(Math.abs(Number.parseFloat(style.left)-(20-borderWidth))<1e-9);
assert.ok(Math.abs(Number.parseFloat(style.top)-(17-borderWidth))<1e-9);
borderWidth=1;
Object.assign(rect,{width:784,height:523});
resized();
assert.equal(style.width,'784px');
assert.equal(style.height,'523px');
context.routeEl.dataset={maxStrokeWidthPercent:'1.25'};
Object.assign(rect,{width:220,height:147});
resized();
assert.equal(style['--route-stroke-width'],'2.75px');
context.routeEl.dataset.maxStrokeWidthPercent='0';
Object.assign(rect,{width:784,height:523});
resized();
assert.equal(style['--route-stroke-width'],'7px');
// Closed/hidden dialogs do not reset geometry to a zero-size image.
context.detailDialogEl.open=false;
Object.assign(rect,{width:0,height:0});
resized();
assert.equal(style.width,'784px');
'''
    result = subprocess.run(
        ["node", "-e", program], input=json.dumps({"source": source}),
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_mental_health_route_uses_north_double_door_and_bypasses_small_rooms():
    routes = json.loads(Path('data/corridor_routes.json').read_text(encoding='utf-8'))
    assert Path('data/corridor_routes.json').read_bytes() == Path('public/data/corridor_routes.json').read_bytes()
    floor = routes['floors']['1층']
    route = floor['routes']['정신건강복지센터']
    assert route['status'] == 'VERIFIED'
    assert route['waypoint_ids'][0] == routes['render_contract']['route_start_waypoint']
    assert route['waypoint_ids'][-1] == 'door_정신건강복지센터'
    points = [floor['waypoints'][key] for key in route['waypoint_ids']]
    assert all(point['status'] == 'VERIFIED' for point in points)
    pixels = [(p['highres_pixel']['x'], p['highres_pixel']['y']) for p in points]
    assert pixels == [(1756, 1535), (1756, 1145), (2219, 1145), (2219, 1384)]
    assert all(a[0] == b[0] or a[1] == b[1] for a, b in zip(pixels, pixels[1:]))
    # Surveyed outlines of the two small rooms are west of x=2176 and south
    # of y=1190. The east corridor is bounded by x=2176 and x=2245 here.
    for a, b in zip(pixels, pixels[1:]):
        for step in range(101):
            x=a[0]+(b[0]-a[0])*step/100
            y=a[1]+(b[1]-a[1])*step/100
            assert not (1970 <= x <= 2176 and 1190 <= y <= 1390)
    assert 2190 < pixels[-1][0] < 2243 and pixels[-1][1] <= 1385
    # Stroke is capped to 32 natural-image pixels for this narrow corridor.
    half_stroke = route['max_stroke_width_percent'] / 100 * 2560 / 2
    assert pixels[-1][0] - half_stroke > 2176
    assert pixels[-1][0] + half_stroke < 2245
    script = Path('public/js/app.js').read_text(encoding='utf-8')
    utilities = 'function normalizeRouteTargetName' + script.split('function normalizeRouteTargetName',1)[1].split('function showCorridorRoute',1)[0]
    program = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const c={state:{corridorRoutes:p.routes}};vm.createContext(c);vm.runInContext(p.source,c);
for(const name of ['정신건강복지센터','정신건강 복지센터','1층 정신건강복지센터']) {
 const point=c.getMapPointForTarget(p.points['1층'],name);
 assert.equal(point,p.points['1층']['정신건강복지센터']);
 assert.equal(c.getCorridorRoute('1층',point.printed_label),p.routes.floors['1층'].routes['정신건강복지센터']);
}
'''
    result = subprocess.run(['node','-e',program],input=json.dumps({'source':utilities,'routes':routes,'points':json.loads(Path('data/map_points.json').read_text(encoding='utf-8'))}),capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


def test_maternal_destination_names_resolve_to_one_verified_door_route():
    script = Path("public/js/app.js").read_text(encoding="utf-8")
    utilities = "function normalizeRouteTargetName" + script.split(
        "function normalizeRouteTargetName", 1
    )[1].split("function showCorridorRoute", 1)[0]
    routes = json.loads(Path("data/corridor_routes.json").read_text(encoding="utf-8"))
    points = json.loads(Path("data/map_points.json").read_text(encoding="utf-8"))
    program = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {state: {corridorRoutes: payload.routes}};
vm.createContext(context);
vm.runInContext(payload.utilities, context);
const points = payload.points['1층'];
const route = payload.routes.floors['1층'].routes['모자보건실·예방접종실'];
for (const name of ['모자보건실', '예방접종실', '모자보건실·예방접종실',
    '모자보건실 예방접종실', '모자보건실예방접종실', '1층 모자보건실ㆍ예방접종실']) {
  const point = context.getMapPointForTarget(points, name);
  assert.equal(point, points['모자보건실·예방접종실'], name);
  const actual = context.getCorridorRoute('1층', point.printed_label);
  assert.equal(actual, route, name);
  assert.equal(actual.status, 'VERIFIED');
  assert.equal(actual.waypoint_ids[0], 'entrance_door_threshold');
  assert.equal(actual.waypoint_ids.at(-1), 'door_모자보건실');
}
const vaccinationPayment = context.getMapPointForTarget(points, '민원실');
assert.equal(context.getCorridorRoute('1층', vaccinationPayment.printed_label),
  payload.routes.floors['1층'].routes['민원실']);
const educationRoom = context.getMapPointForTarget(points, '모자보건교육실(수유실)');
assert.notEqual(educationRoom, points['모자보건실·예방접종실']);
assert.equal(context.getCorridorRoute('1층', educationRoom.printed_label).status, 'REVIEW_REQUIRED');
assert.equal(context.getMapPointForTarget({broken:{alias_of:'missing'}},'broken'),null);
assert.equal(context.getMapPointForTarget({a:{alias_of:'b'},b:{alias_of:'a'}},'a'),null);
'''
    result = subprocess.run(
        ["node", "-e", program],
        input=json.dumps({"utilities": utilities, "routes": routes, "points": points}),
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
