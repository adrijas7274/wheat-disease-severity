import numpy as np
import pytest

from src.severity import phase5_colour_stage as p5

GREEN, ORANGE = (40, 140, 40), (220, 120, 30)


def test_variant_severity_applies_preprocessing_only_to_the_colour_rule():
    image = np.concatenate([np.full((10, 10, 3), c, np.uint8) for c in (GREEN, ORANGE)], axis=1)
    leaf = np.ones((10, 20), bool)
    assert p5.variant_severity(image, leaf, leaf, "rust", [], 10) == pytest.approx(50.0)
    # region outside the leaf is ignored, and an empty leaf gives no estimate
    half = np.zeros((10, 20), bool)
    half[:, :10] = True
    assert p5.variant_severity(image, half, leaf, "rust", [], 10) == 0.0
    assert np.isnan(p5.variant_severity(image, np.zeros((10, 20), bool), leaf, "rust", ["denoise"], 10))


def _summary(shift: float, flip: float) -> dict:
    return {"mean_shift": shift, "mean_flip": flip}


def test_selection_rule():
    tuning = {"none": {"mae_leave_one_out": 17.0}, "a": {"mae_leave_one_out": 20.0}, "b": {"mae_leave_one_out": 21.0},
              "c": {"mae_leave_one_out": 16.0}}
    summary = {"none": _summary(6.0, 0.30), "a": _summary(4.0, 0.25), "b": _summary(1.0, 0.05), "c": _summary(5.0, 0.35)}
    sel = p5.select(summary, tuning, 3.64)
    assert sel["admissible"] == ["none", "a", "c"]            # b is 4 points worse on tuning
    assert sel["selected"] == "a" and sel["replaces_baseline"]
    # lower shift but more flips does not replace the baseline
    sel = p5.select({"none": _summary(6.0, 0.30), "c": _summary(5.0, 0.35)}, tuning, 3.64)
    assert sel["best_admissible"] == "c" and sel["selected"] == "none" and not sel["replaces_baseline"]


def test_summarise_means_over_the_benchmark_cells():
    cell = lambda shift: {"severity_shift": {"mean": shift}, "flip_rate": {"mean": 0.2}, "miou": {"mean": 0.5},
                          "flip_at": {"5": {"mean": 0.1}}}
    agg = {c: {str(lv): cell(2.0) for lv in p5.LEVELS} for c in p5.BENCH}
    agg["clean"] = {"0": cell(0.0)}
    records = [{"corruption": "clean", "models": {"k": {"severity": s}}} for s in (0.0, 10.0)]
    s = p5.summarise(agg, records, "k")
    assert s["mean_shift"] == pytest.approx(2.0) and s["mean_flip"] == pytest.approx(0.2) and s["mean_flip_at_5"] == pytest.approx(0.1)
    assert s["clean_zero_share"] == 0.5 and s["clean_mean_severity"] == 5.0


def test_report_row_prints_a_dash_for_a_group_without_a_threshold():
    # a disease group with no tuning image has no threshold (seen in --debug, 3 tuning images)
    s = {"mean_shift": 2.0, "mean_flip": 0.2, "clean_zero_share": 0.0, "clean_mean_severity": 1.0}
    row = p5._row("`none`", s, {"mae_leave_one_out": 7.7, "thresholds": {"rust": 10, "necrotic": None, "mildew": None}})
    assert "7.70 | 10 / - / - |" in row
