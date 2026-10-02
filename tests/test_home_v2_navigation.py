"""Run HOME navigation regressions without HTTP, credentials or a database."""

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_home_navigation_vm_contract():
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "home_v2_navigation.cjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["passed"] == 27
    assert report["failed"] == 0
    assert report["realSmsSent"] == 0
    assert len(report["cases"]) == len(set(report["cases"])) == 27
