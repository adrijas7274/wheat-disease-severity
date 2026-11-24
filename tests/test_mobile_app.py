"""Phase 8 app: strings file, review sheet, policy file and the JavaScript pipeline (small, fast checks)."""
from __future__ import annotations

import csv
import json
import re
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
    assert 30 <= len(keys) <= 100
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
        assert advice["diseases"][name]["products"] == [] and advice["diseases"][name]["options"] == []
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
    assert out[5][0]["products"] == out[6][0]["products"] and 1 <= len(out[6][0]["products"]) <= 3
    assert all(len(a.get("products", [])) == 0 for a, _ in out[:5] + out[7:])


def test_conversions_are_exact():
    from src.mobile import build_advice as b
    assert b.HA_PER_ACRE == 0.40468564224
    for d in b.build()["diseases"].values():
        assert len(d["options"]) <= 3 and d["options"] == sorted(d["options"], key=lambda i: d["products"][i]["page"])
        for p in d["products"]:
            c = p["converted"]
            dose = b.parse_amount(p["formulation_per_ha"])
            per_l = b.parse_amount(p["dose_per_litre"])
            water = b.parse_water(p["water_l_per_ha"])
            if dose:
                assert c["per_acre"]["lo"] == dose[0] * b.HA_PER_ACRE and c["per_acre"]["hi"] == dose[1] * b.HA_PER_ACRE
            if per_l:
                assert c["per_tank"]["lo"] == per_l[0] * 15 and c["per_tank"]["unit"] == per_l[2]
            if water:
                assert c["water_per_acre"]["lo"] == water[0] * b.HA_PER_ACRE
            if not dose and not per_l:
                assert c["per_acre"] is None and c["per_tank"] is None  # no unit printed: never converted
    az = b.conversions(b.AZ_DIF)
    assert az["per_tank"]["text"] == "15 ml" and az["per_acre"]["lo"] == 500 * 0.40468564224


def _node(script: str) -> object:
    res = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True,
                         timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_camera_hints():
    out = _node("""
    import { frameStats, hintFor } from './app/web/js/camera.js';
    const w = 40, h = 30, n = w * h;
    const flat = (v) => new Uint8Array(n).fill(v);
    const stripes = (a, b) => Uint8Array.from({ length: n }, (_, i) => ((i % w) % 2 ? a : b));
    console.log(JSON.stringify({
      dark: hintFor(frameStats(stripes(10, 60), w, h)),
      bright: hintFor(frameStats(flat(255), w, h)),
      flat: hintFor(frameStats(flat(120), w, h)),
      sharp: hintFor(frameStats(stripes(60, 180), w, h, stripes(60, 180))),
      moving: hintFor(frameStats(stripes(60, 180), w, h, stripes(180, 60))),
      stats: frameStats(flat(120), w, h),
    }));
    """)
    assert out["dark"] == "cam_dark" and out["bright"] == "cam_bright"
    assert out["flat"] == "cam_blur"  # no detail at all: blurry
    assert out["sharp"] == "cam_ok" and out["moving"] == "cam_steady"
    assert out["stats"]["mean"] == 120 and out["stats"]["sharp"] == 0 and out["stats"]["motion"] is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_history_list():
    out = _node("""
    import { withEntry, trend, MAX } from './app/web/js/history.js';
    let l = [];
    for (let i = 0; i < MAX + 5; i++) l = withEntry(l, { t: i, disease: i % 2 ? 'a' : 'b', severity: i % 3 ? i : null });
    console.log(JSON.stringify({ n: l.length, max: MAX, first: l[0].t, trend: trend(l, 'a', 4).map((e) => e.t) }));
    """)
    assert out["n"] == out["max"] and out["first"] == out["max"] + 4  # newest first, capped
    assert out["trend"] == sorted(out["trend"]) and len(out["trend"]) == 4  # oldest first, answered only


UNIT = re.compile(r"\d\s*(g|gm|kg|ml|l|lit|lt|ltr)(?![a-z])", re.I)


def test_every_option_shown_has_an_explicit_dose_unit(advice):
    """Safety rule: the app shows only products whose official dose prints a clear unit."""
    from src.mobile import build_advice as b
    hidden = set()
    for name, d in advice["diseases"].items():
        for i in d["options"]:
            p = d["products"][i]
            dose = p["dose_per_litre"] or p["formulation_per_ha"]
            assert dose and UNIT.search(dose), (name, p["product"], dose)
            assert "to be confirmed" not in (p["note"] or "")
        hidden |= {p["product"] for i, p in enumerate(d["products"]) if i not in d["options"]}
        # no complete option -> no spray level; medium and high say "ask an expert"
        if not d["options"]:
            assert set(d["levels"].values()) <= {"no_spray", "watch", "ask_expert"}
            assert d["levels"]["medium"] == d["levels"]["high"] == "ask_expert"
    for product in ("Kresoxim-methyl 44.3% SC", "Sulphur 80% WG", "Propiconazole 25% EC"):
        assert product in hidden  # kept for the expert sheet, never shown
    # a registered product with no unit alone gives no option, so the disease falls back to "ask an expert"
    unitless = {**b.SULPH}
    assert b.pick_options([unitless]) == []
    rows = b.review_rows(advice)
    assert any("Kresoxim-methyl" in r[3] for r in rows) and any("Sulphur" in r[3] for r in rows)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_registered_but_incomplete_disease_asks_an_expert(advice):
    """A disease whose registered products all lack a clear unit: no dose, 'ask an expert', not 'none registered'."""
    from src.mobile import build_advice as b
    fake = json.loads(json.dumps(advice))
    d = fake["diseases"]["wheat powdery mildew"]
    d["options"] = []
    d["levels"] = dict(b.LEVEL_ACTION_NO_PRODUCT)
    script = """
    import fs from 'node:fs';
    import { adviceFor, outcomeFor } from './app/web/js/advice.js';
    const advice = JSON.parse(fs.readFileSync(0, 'utf8'));
    const r = { action: 'answer', severity: 60, level: 'high', decision: 'treat_urgently' };
    const a = adviceFor(r, 'wheat powdery mildew', advice);
    console.log(JSON.stringify([a, outcomeFor(r, a)]));
    """
    res = subprocess.run(["node", "--input-type=module", "-e", script], input=json.dumps(fake), cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    a, outcome = json.loads(res.stdout)
    assert a["action"] == "ask_expert" and a["products"] == [] and a["noRegistered"] is False
    assert outcome == "consult" and a["kcc"] == "1800-180-1551"
