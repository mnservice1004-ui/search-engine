"""Freeze the user-approved modified A (sunset-wide), not the earlier A renderer."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PRESERVED_HOME='public/qa/home-modified-a.html'


def test_modified_a_reference_files_match_approved_5037_bytes():
    manifest=json.loads((ROOT/'docs/approved-background-modified-a.json').read_text(encoding='utf-8'))
    assert manifest['name']=='수정 A안'
    assert (manifest['variant'],manifest['look'],manifest['playbackRate'])==('A','sunset-wide',3.5)
    assert manifest['sourceLocations']=={'public/index.html':PRESERVED_HOME}
    for name,digest in manifest['sourceSha256'].items():
        location=manifest['sourceLocations'].get(name,name)
        content=(ROOT/location).read_bytes()
        if Path(name).suffix in {'.html','.css','.js'}:
            content=content.replace(b'\r\n',b'\n')
        assert hashlib.sha256(content).hexdigest()==digest,f'{name} preserved at {location}'


def test_modified_a_home_loads_the_approved_engine_not_legacy_animation():
    html=(ROOT/PRESERVED_HOME).read_text(encoding='utf-8')
    assert '/qa/layer-engine.js?revision=a-whole-sky' in html
    assert '/qa/layer-home.js?revision=a-whole-sky' in html
    assert '/js/hero-atmosphere.js' not in html
    assert 'href="data:,"' in html
    home=(ROOT/'public/qa/layer-home.js').read_text(encoding='utf-8')
    assert "preferredVariant:'A',playbackRate:3.5,animationApproved:true" in home
    assert "requestedLook:'sunset-wide'" in home
    assert 'prefers-reduced-motion: reduce' in home
    assert "document.querySelector('dialog[open]')" in home


def test_modified_a_cloud_direction_and_independent_foliage_contract():
    source=(ROOT/'public/qa/layer-engine.js').read_text(encoding='utf-8')
    program='const assert=require("node:assert/strict"),vm=require("node:vm");const c={window:{}};vm.createContext(c);vm.runInContext('+json.dumps(source)+',c);const a=c.window.LayerLab;'+r'''
assert.equal(a.SPEED,.0023);assert.equal(a.PERIOD,.92);
for(const t of [0,1,10,100,1000]){
 assert.ok(a.shiftAt(t+.1)>a.shiftAt(t));
 const angles=a.leafAngles(t);assert.equal(angles.length,6);
 angles.forEach(x=>assert.ok(Number.isFinite(x)&&Math.abs(x)<=.0075));
}
assert.notDeepEqual([...a.leafAngles(0)],[...a.leafAngles(1)]);
'''
    result=subprocess.run(['node','-e',program],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
