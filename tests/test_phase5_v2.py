from pathlib import Path

import numpy as np
from PIL import Image

from src.corruptions.corruptions import CORRUPTIONS
from src.severity import phase5_v2 as v2

CONFIG = {"severity_thresholds": {"low_max": 0.05, "medium_max": 0.20},
          "decision_mapping": {"none": "no_action", "low": "monitor", "medium": "treat", "high": "treat_urgently"}, "seed": 42,
          "phase4": {"flip_thresholds": [3, 5, 10, 20]}}
SEPT, BLS = "wheat septoria blotch", "wheat bacterial leaf streak (black chaff)"


def _records(name: str, disease: str, clean: dict[str, float], jitter: dict[str, float]) -> list[dict]:
    """Clean record plus every benchmark condition; variant v's corrupted estimate = clean + jitter[v]."""
    def rec(corruption, level, sev):
        return {"name": name, "disease": disease, "corruption": corruption, "level": level, "leaf_iou_vs_clean": 1.0,
                "models": {f"segformer|{v}": {"iou": 0.5, "severity": s} for v, s in sev.items()}}

    out = [rec("clean", 0, clean)]
    for c in CORRUPTIONS:
        for lv in range(1, 6):
            out.append(rec(c, lv, {v: clean[v] + jitter[v] for v in clean}))
    return out


def _val() -> list[dict]:
    # variant "a" is more stable but answers 0 on septoria; variant "b" is more stable and keeps detection
    recs = []
    for k in range(4):
        recs += _records(f"s{k}", SEPT, {"none": 10.0, "a": 0.0, "b": 10.0}, {"none": 6.0, "a": 0.0, "b": 2.0})
        recs += _records(f"l{k}", BLS, {"none": 8.0, "a": 8.0, "b": 8.0}, {"none": 6.0, "a": 1.0, "b": 2.0})
    return recs


def _healthy(median_b: float) -> list[dict]:
    return [{"name": f"h{k}", "severity": {"none": {"necrotic": 0.0}, "a": {"necrotic": 0.0}, "b": {"necrotic": median_b}}} for k in range(5)]


EXP = {"guards": {"tuning_loo_limit": 3.64, "healthy_share_above": 5.0}}
LOO = {"none": {"necrotic": 10.0}, "a": {"necrotic": 11.0}, "b": {"necrotic": 12.0}}


def test_detection_guard_rejects_a_variant_that_answers_zero():
    s = v2.select_group("necrotic", ["none", "a", "b"], _val(), LOO, _healthy(0.0), EXP, CONFIG)
    assert not s["rows"]["a"]["g2"] and s["rows"]["b"]["passes"]
    assert s["selected"] == "b" and s["replaces_baseline"]


def test_healthy_and_tuning_guards():
    s = v2.select_group("necrotic", ["none", "a", "b"], _val(), LOO, _healthy(6.0), EXP, CONFIG)
    assert not s["rows"]["b"]["g3"] and s["selected"] == "none"
    loo = dict(LOO, b={"necrotic": 14.0})
    s = v2.select_group("necrotic", ["none", "a", "b"], _val(), loo, _healthy(0.0), EXP, CONFIG)
    assert not s["rows"]["b"]["g1"] and s["selected"] == "none"


def test_add_stage_takes_each_disease_groups_variant():
    recs = _records("x", SEPT, {"none": 1.0, "a": 2.0, "b": 3.0}, {"none": 0.0, "a": 0.0, "b": 0.0})[:1]
    out = v2.add_stage(recs, {"rust": "a", "necrotic": "b", "mildew": "a"}, "segformer|v2")
    assert out[0]["models"]["segformer|v2"]["severity"] == 3.0 and "segformer|v2" not in recs[0]["models"]


def test_healthy_entries_need_every_substring(tmp_path):
    for rel in ("Original Dataset/Healthy Leaf/a.jpg", "Augmented Dataset/Healthy Leaf/b.jpg", "Original Dataset/Leaf Blight/c.jpg"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.zeros((4, 4, 3), np.uint8)).save(p)
    assert [p.name for p in v2.healthy_entries(tmp_path, ["original", "healthy"])] == ["a.jpg"]
