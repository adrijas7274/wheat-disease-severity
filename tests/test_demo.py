import json
from pathlib import Path

import numpy as np

from src.demo.pipeline import DISEASES, explain


def test_explain_gate_failure_asks_for_retake_in_plain_words():
    action, reason = explain(["sharpness", "clip_high"], 0.5, 3.0, "low", "monitor", 2.0)
    assert action == "retake" and "blurred" in reason and "over-exposed" in reason


def test_explain_high_uncertainty_sends_to_expert():
    action, reason = explain([], 5.0, 3.0, "medium", "treat", 12.0)
    assert action == "consult" and "5.0" in reason


def test_explain_answer_marks_placeholders():
    action, reason = explain([], 1.0, 3.0, "medium", "treat", 12.0)
    assert action == "answer" and "12.0%" in reason and "PLACEHOLDER" in reason


def test_explain_empty_leaf_asks_for_retake():
    assert explain([], 0.0, 3.0, None, None, None)[0] == "retake"


def test_overlay_and_example_names():
    from demo.app import _disease_of, overlay

    image = np.zeros((40, 50, 3), np.uint8)
    leaf = np.zeros((40, 50), bool)
    leaf[10:30, 10:40] = True
    lesion = np.zeros_like(leaf)
    lesion[15:20, 15:20] = True
    out = overlay(image, leaf, lesion, (35, 25))
    assert out.shape == image.shape and out[17, 17, 0] > 0
    assert _disease_of("wheat_septoria_blotch_1.jpg") == "wheat septoria blotch"
    assert all(_disease_of(p.name) in DISEASES for p in Path("demo/examples").glob("*.jpg"))
    assert _disease_of("z_blurred_wheat_leaf_rust_1.jpg") == _disease_of("wheat_leaf_rust_1.jpg") != DISEASES[0]


def test_frozen_policy_file_matches_final_pipeline():
    p = json.loads(Path("demo/final_policy.json").read_text(encoding="utf-8"))
    assert p["tag"] == "final-v1" and p["policy_score"] == "photometric"
    assert p["colour_steps"] == {"rust": [], "necrotic": [], "mildew": []}
    assert p["colour_thresholds"] == {"rust": 10, "necrotic": 15, "mildew": 8}
