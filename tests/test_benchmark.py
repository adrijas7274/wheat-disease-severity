import numpy as np
import pytest

from src.corruptions import benchmark as bm

CONFIG = {"severity_thresholds": {"low_max": 0.05, "medium_max": 0.20},
          "decision_mapping": {"none": "no_action", "low": "monitor", "medium": "treat", "high": "treat_urgently"},
          "severity_method": {"refinement": "C1", "c1_thresholds": {"rust": 10}},
          "seed": 42}


def _rec(name: str, corruption: str, level: int, severity: float, iou: float = 0.5, leaf_iou: float = 1.0, rating=None) -> dict:
    r = {"name": name, "disease": "wheat leaf rust", "corruption": corruption, "level": level, "click": [1, 1],
         "leaf_share": 0.3, "leaf_iou_vs_clean": leaf_iou, "models": {"m": {"iou": iou, "severity": severity}}}
    if rating is not None:
        r["rating"] = rating
    return r


def test_decision_uses_placeholder_levels_and_none_without_estimate():
    assert bm.decision(0.0, CONFIG) == "no_action" and bm.decision(3.0, CONFIG) == "monitor"
    assert bm.decision(12.0, CONFIG) == "treat" and bm.decision(35.0, CONFIG) == "treat_urgently"
    assert bm.decision(float("nan"), CONFIG) is None


def test_aggregate_shift_level_accuracy_and_flip_rate():
    records = [_rec("a", "clean", 0, 4.0, iou=0.8), _rec("b", "clean", 0, 10.0, iou=0.6),
               _rec("a", "jpeg", 1, 6.0, iou=0.7),    # low -> medium: flip, shift 2
               _rec("b", "jpeg", 1, 12.0, iou=0.5)]   # medium -> medium: no flip, shift 2
    cell = bm.aggregate(records, "m", CONFIG)["jpeg"]["1"]
    assert cell["severity_shift"]["mean"] == pytest.approx(2.0)
    assert cell["flip_rate"]["mean"] == pytest.approx(0.5) and cell["level_accuracy"]["mean"] == pytest.approx(0.5)
    assert cell["miou"]["mean"] == pytest.approx(0.6)
    assert "mae_vs_rating" not in cell


def test_missing_estimates_flip_and_missing_clean_is_left_out():
    nan = float("nan")
    records = [_rec("a", "clean", 0, 10.0), _rec("b", "clean", 0, nan),
               _rec("a", "jpeg", 5, nan), _rec("b", "jpeg", 5, 50.0)]
    agg = bm.aggregate(records, "m", CONFIG)
    cell = agg["jpeg"]["5"]
    assert agg["n_without_clean_estimate"] == 1
    assert cell["flip_rate"] == pytest.approx({"mean": 1.0, "ci_low": 1.0, "ci_high": 1.0, "n": 1})
    assert cell["n_no_estimate"] == 1 and cell["severity_shift"]["n"] == 0
    assert cell["miou"]["n"] == 2  # mIoU does not depend on the severity estimate


def test_rated_sets_report_error_against_the_rating():
    records = [_rec("a", "clean", 0, 10.0, rating=12.0), _rec("a", "jpeg", 1, 30.0, rating=12.0)]
    cell = bm.aggregate(records, "m", CONFIG)["jpeg"]["1"]
    assert cell["mae_vs_rating"]["mean"] == pytest.approx(18.0)
    assert cell["decision_agreement_with_rating"]["mean"] == 0.0  # treat_urgently vs treat


def test_frozen_severity_clips_region_to_leaf():
    image = np.concatenate([np.full((10, 10, 3), c, np.uint8) for c in ((40, 140, 40), (220, 120, 30))], axis=1)
    leaf = np.zeros((10, 20), bool)
    leaf[:, 5:15] = True  # half green, half orange
    assert bm.frozen_severity(image, leaf, np.ones((10, 20), bool), "rust", CONFIG["severity_method"]) == pytest.approx(50.0)
    assert np.isnan(bm.frozen_severity(image, np.zeros((10, 20), bool), np.ones((10, 20), bool), "rust", CONFIG["severity_method"]))


def test_report_and_figures(tmp_path):
    records = [_rec(n, "clean", 0, s, rating=10.0) for n, s in (("a", 4.0), ("b", 10.0))]
    records += [_rec(n, c, lv, s + lv, rating=10.0) for n, s in (("a", 4.0), ("b", 10.0)) for c in ("jpeg", "combined") for lv in (1, 5)]
    aggs = {"m": bm.aggregate(records, "m", CONFIG)}
    report = bm.format_report({"Set": {"aggs": aggs, "rated": True}}, ["jpeg", "combined"], [1, 5],
                              CONFIG, {"click_model": "segformer"}, "abc")
    assert "PLACEHOLDER" in report.upper() and "decision flip rate" in report and "| jpeg |" in report
    assert "severity MAE against the rating" in report
    paths = bm.plot_set(aggs, ["jpeg", "combined"], [1, 5], tmp_path, "", "Set")
    assert len(paths) == 5 and all(p.exists() for p in paths)


def test_single_threshold_flips():
    config = CONFIG | {"phase4": {"flip_thresholds": [5, 10]}}
    records = [_rec("a", "clean", 0, 4.0), _rec("b", "clean", 0, 12.0),
               _rec("a", "jpeg", 1, 6.0),    # crosses 5, not 10
               _rec("b", "jpeg", 1, 8.0)]    # crosses 10, not 5
    aggs = {"m": bm.aggregate(records, "m", config)}
    cell = aggs["m"]["jpeg"]["1"]
    assert cell["flip_at"]["5"]["mean"] == pytest.approx(0.5) and cell["flip_at"]["10"]["mean"] == pytest.approx(0.5)
    report = bm.format_report({"Set": {"aggs": aggs, "rated": False}}, ["jpeg"], [1], config, {"click_model": "segformer"}, "abc")
    assert "flip rate at a single threshold" in report and "5% (level 1)" in report
