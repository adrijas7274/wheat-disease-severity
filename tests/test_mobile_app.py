"""Phase 8 app: strings file, review sheet, policy file and the JavaScript pipeline (small, fast checks)."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.mobile import review_sheet

ROOT = Path(__file__).resolve().parents[1]
STRINGS = ROOT / "app/web/strings.json"
SCHEDULED = {"as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml", "mni", "mr", "ne", "or", "pa",
             "sa", "sat", "sd", "ta", "te", "ur"}


@pytest.fixture(scope="module")
def strings() -> dict:
    return json.loads(STRINGS.read_text(encoding="utf-8"))


def test_all_22_scheduled_languages_plus_english(strings):
    assert set(strings["languages"]) == SCHEDULED | {"en"}
    assert sorted(strings["order"]) == sorted(strings["languages"])
    assert strings["order"][0] == "en"


def test_every_language_has_every_phrase(strings):
    keys = set(strings["languages"]["en"]["strings"])
    assert 30 <= len(keys) <= 40
    for code, lang in strings["languages"].items():
        assert set(lang["strings"]) == keys, code
        assert all(v.strip() for v in lang["strings"].values()), code
        assert "{pct}" in lang["strings"]["severity"], code


def test_status_and_metadata(strings):
    for code, lang in strings["languages"].items():
        assert lang["status"] in {"machine_draft", "verified"}
        assert lang["dir"] in {"ltr", "rtl"}
        assert lang["font"] is None or lang["font"] in strings["fonts"]
        assert lang["tts"]
    assert strings["languages"]["en"]["status"] == "verified"
    # nothing is verified until a native speaker checks it
    assert all(l["status"] == "machine_draft" for c, l in strings["languages"].items() if c != "en")
    assert {c for c, l in strings["languages"].items() if l["dir"] == "rtl"} == {"ur", "ks", "sd"}


def test_review_sheet(tmp_path, strings):
    out = tmp_path / "review.csv"
    review_sheet.write(strings, out)
    with out.open(encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 1 + len(strings["languages"]["en"]["strings"])
    assert len(rows[0]) == 3 + 22
    assert all("machine_draft" in h for h in rows[0][3:])
    assert (tmp_path / "translation_review_howto.md").exists()


def test_policy_matches_frozen_rules():
    policy = json.loads((ROOT / "app/web/policy.json").read_text(encoding="utf-8"))
    assert policy["tag"] == "final-v1-mobile"
    assert policy["leaf_min_area_share"] == 0.02
    assert policy["decision_mapping"] == {"none": "no_action", "low": "monitor", "medium": "treat", "high": "treat_urgently"}
    for m in policy["models"].values():
        assert len(m["sha256"]) == 64


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_pipeline_units():
    script = """
    import * as p from './app/web/js/pipeline.js';
    const out = {
      round: [p.pyRound(0.5), p.pyRound(1.5), p.pyRound(2.5), p.pyRound(-0.5)],
      levels: [p.severityLevel(0, {low_max:0.05, medium_max:0.2}), p.severityLevel(3, {low_max:0.05, medium_max:0.2}),
               p.severityLevel(12, {low_max:0.05, medium_max:0.2}), p.severityLevel(40, {low_max:0.05, medium_max:0.2})],
      actions: [p.decideAction(['noise'], 0, 3, 5), p.decideAction([], 0, 3, null), p.decideAction([], 4, 3, 5),
                p.decideAction([], 1, 3, 5)],
      compute: [p.computeMs({start: 0, encoder: 4000, end: 4000}),
                p.computeMs({start: 0, encoder: 4000, tap: 9000, end: 9500})],
    };
    console.log(JSON.stringify(out));
    """
    res = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True,
                         timeout=60)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["round"] == [0, 2, 2, 0]
    assert out["actions"] == ["retake", "retake_no_leaf", "consult", "answer"]
    assert out["compute"] == [4000, 4500]
    assert out["levels"] == ["none", "low", "medium", "high"]
