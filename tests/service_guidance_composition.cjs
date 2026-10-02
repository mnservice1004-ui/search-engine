const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window:{}, document:{getElementById:()=>({addEventListener(){}})}};
vm.runInNewContext(fs.readFileSync('public/js/examinations.js','utf8'),context);
const {compose,entries} = context.window.ServiceGuidanceView;
const ids = items => Array.from(items,i=>i.id);
const guide = (id,related,expired=false)=>({id,related_task_ids:related,is_archived:expired});
test('one business card keeps linked tasks inside its dialog',()=>{
  assert.deepEqual(ids(compose([guide('guide-S015',['M004','F109'])],[{id:'M004'},{id:'F109'}])),['guide-S015']);
});
test('distinct programs sharing one room remain discoverable',()=>{
  assert.deepEqual(ids(compose([guide('guide-S015',['M004','F109']),guide('guide-S016',['M006','F109'])],
    [{id:'M004'},{id:'M006'},{id:'F109'},{id:'A003'}])),['guide-S015','guide-S016','A003']);
});
test('expired program cannot suppress a current task or location',()=>{
  assert.deepEqual(ids(compose([guide('guide-S025',['M003'],true)],[{id:'M003'}])),['guide-S025','M003']);
});
test('location-only query retains its location card and removes repeated IDs',()=>{
  assert.deepEqual(ids(compose([],[{id:'F109'},{id:'F109'}])),['F109']);
});
test('duplicate official records produce only one guide with task links',()=>{
  const item={id:'S015',title:'산모',summary:'안내',related_task_ids:['M004','F109']};
  const actual=entries({services:{guides:[item,item]}},'산모',()=>{});
  assert.deepEqual(ids(actual),['guide-S015']);
  assert.deepEqual(Array.from(actual[0].related_task_ids),['M004','F109']);
});
