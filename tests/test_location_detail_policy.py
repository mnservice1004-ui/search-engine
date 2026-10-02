"""Location directions must remain separate from cautions and source data."""
import json
from pathlib import Path
import subprocess


def test_location_policy_is_semantic_exhaustive_and_non_mutating():
    root = Path(__file__).resolve().parents[1]
    script = (root / 'public/js/app.js').read_text(encoding='utf-8')
    helpers = script[script.index('function hasPublicText('):script.index('function getPrimaryContact(')]
    policy = script[script.index('const LOCATION_ONLY_GUIDE_IDS'):script.index('function showDetail(')]
    tasks = json.loads((root / 'data/public_guidance.json').read_text(encoding='utf-8'))['tasks']
    program = "const assert = require('node:assert/strict');\n" + helpers + policy
    program += '\nconst tasks = ' + json.dumps(tasks, ensure_ascii=False) + ';\n'
    program += r'''
assert.equal(LOCATION_ONLY_GUIDE_IDS.size, 19);
for (const raw of tasks) {
  const task = {...raw, id: raw.task_id};
  const before = JSON.stringify(task);
  const expected = raw.task_id.startsWith('F');
  assert.equal(isLocationOnlyGuide(task), expected, raw.task_id);
  if (expected) {
    const text = getLocationVisitText(task);
    assert.equal(text, task.visit_steps);
    assert.equal(isLocationOnlyGuide({...task, public_title:'시설을 찾으시나요?'}), true);
  }
  assert.equal(JSON.stringify(task), before);
}
for (const id of ['M001','R001','R003','R005','A008','F999']) {
  assert.equal(isLocationOnlyGuide({id,public_title:'신청 안내'}), false);
}
assert.equal(isLocationOnlyGuide({id:'F108',public_title:null}), false);
assert.equal(isLocationOnlyGuide(null), false);
assert.equal(getLocationVisitText(null), '');
assert.equal(getLocationVisitText({}), '');
assert.equal(getLocationVisitText({visit_steps:'찾아가는 방법.',public_caution:'주의사항.',primary_action:'추가안내.'}), '찾아가는 방법.');
'''
    result = subprocess.run(['node', '-'], input=program, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
