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
    assert 30 <= len(keys) <= 60
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


ADVICE = ROOT / "app/web/advice.json"


@pytest.fixture(scope="module")
def advice() -> dict:
    return json.loads(ADVICE.read_text(encoding="utf-8"))


def test_advice_table_is_unverified_and_sourced(advice):
    assert advice["status"] == "unverified" and advice["verified_by"] is None
    assert advice["kisan_call_centre"] == "1800-180-1551"
    names = {"wheat stripe rust", "wheat leaf rust", "wheat powdery mildew", "wheat septoria blotch",
             "wheat bacterial leaf streak (black chaff)"}
    assert set(advice["diseases"]) == names
    for d in advice["diseases"].values():
        for p in d["products"]:
            assert p["source"] in advice["sources"] and p["page"]
            assert advice["sources"][p["source"]]["url"].startswith("https://ppqs.gov.in/")
            # values not in the source stay empty: no per-acre conversion, no invented timing
            assert p["dose_per_acre"] is None and p["water_per_acre"] is None
            assert p["timing"] is None and p["repeat_interval"] is None
            assert "mancozeb" not in p["product"].lower()  # restricted in use: excluded
    for name in ("wheat septoria blotch", "wheat bacterial leaf streak (black chaff)"):
        assert advice["diseases"][name]["products"] == [] and advice["diseases"][name]["app_product"] is None
        assert "spray_recommended" not in advice["diseases"][name]["levels"].values()


def _adv(results, advice):
    script = """
    import fs from 'node:fs';
    import { adviceFor, outcomeFor } from './app/web/js/advice.js';
    const advice = JSON.parse(fs.readFileSync('app/web/advice.json', 'utf8'));
    const cases = JSON.parse(process.argv[1]);
    console.log(JSON.stringify(cases.map(([r, d]) => { const a = adviceFor(r, d, advice); return [a, outcomeFor(r, a)]; })));
    """
    res = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps(results)], cwd=ROOT,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_dose_only_for_answered_spray_results(advice):
    rust = "wheat stripe rust"
    cases = [
        [{"action": "retake", "failed": ["sharpness"]}, rust],
        [{"action": "retake_no_leaf", "failed": []}, rust],
        [{"action": "consult", "severity": 40.0, "level": "high", "decision": "treat_urgently"}, rust],
        [{"action": "answer", "severity": 0.0, "level": "none", "decision": "no_action"}, rust],
        [{"action": "answer", "severity": 3.0, "level": "low", "decision": "monitor"}, rust],
        [{"action": "answer", "severity": 8.0, "level": "medium", "decision": "treat"}, rust],
        [{"action": "answer", "severity": 60.0, "level": "high", "decision": "treat_urgently"}, rust],
        [{"action": "answer", "severity": 30.0, "level": "high", "decision": "treat_urgently"}, "wheat septoria blotch"],
        [{"action": "answer", "severity": 30.0, "level": "high", "decision": "treat_urgently"},
         "wheat bacterial leaf streak (black chaff)"],
    ]
    out = _adv(cases, advice)
    for (a, o), (r, _) in zip(out, cases):
        assert a["kcc"] == "1800-180-1551"  # every result shows the Kisan Call Centre number
        if a["product"] is not None:
            assert r["action"] == "answer" and a["action"] == "spray_recommended"
            assert a["warning"] is True  # unverified table: a dose always comes with the warning
    assert [o for _, o in out] == ["retake", "retake", "consult", "no_action", "monitor", "treat", "treat_urgently",
                                   "consult", "consult"]
    assert all(a["product"] is None for a, _ in out[:5])  # retake, consult, none, low: no dose
    assert out[5][0]["product"] is not None and out[6][0]["product"] is not None
    assert out[7][0]["product"] is None and out[8][0]["product"] is None  # nothing registered
    # never scaled by severity: medium (8%) and high (60%) give the identical dose
    assert out[5][0]["product"] == out[6][0]["product"]
    assert out[5][0]["product"]["dosePerLitre"] == "1 ml / Litre water"
