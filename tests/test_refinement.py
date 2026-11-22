from pathlib import Path

import numpy as np
import pytest

from src.severity import evaluate_gold as eg
from src.severity import refinement as rf
from src.severity import severity_pipeline as sp
from src.severity import tune_refinement as tr

GREEN, ORANGE, BROWN, WHITE, YELLOW, DARK = (40, 140, 40), (220, 120, 30), (120, 80, 50), (225, 225, 220), (220, 160, 30), (25, 25, 25)


def _image(*colours: tuple[int, int, int]) -> np.ndarray:
    """One 10-pixel-wide vertical stripe per colour, 10 pixels high."""
    return np.concatenate([np.full((10, 10, 3), c, np.uint8) for c in colours], axis=1)


def test_c0_removes_only_healthy_green():
    image = _image(GREEN, ORANGE, BROWN, WHITE)
    region = np.ones(image.shape[:2], bool)
    kept = rf.refine_c0(region, image)
    assert not kept[:, :10].any() and kept[:, 10:].all()


def test_lesion_colour_per_group():
    image = _image(GREEN, ORANGE, BROWN, WHITE, DARK)
    stripes = lambda m: [bool(m[:, i * 10:(i + 1) * 10].all()) for i in range(5)]
    assert stripes(rf.lesion_colour(image, "rust", 20)) == [False, True, False, False, False]
    assert stripes(rf.lesion_colour(image, "necrotic", 5)) == [False, True, True, False, False]
    assert stripes(rf.lesion_colour(image, "mildew", 12)) == [False, False, False, True, False]  # dark is not mildew
    with pytest.raises(ValueError):
        rf.lesion_colour(image, "smut", 1)


def test_c1_counts_yellow_only_when_it_touches_a_lesion():
    # orange | yellow | green | yellow : the first yellow stripe touches the lesion, the second does not
    image = _image(ORANGE, YELLOW, GREEN, YELLOW)
    region = np.ones(image.shape[:2], bool)
    kept = rf.refine_c1(region, image, "rust", 20)
    assert kept[:, :20].all() and not kept[:, 20:].any()


def test_refinement_only_shrinks_the_region():
    image = _image(ORANGE, ORANGE, GREEN, WHITE)
    region = np.zeros(image.shape[:2], bool)
    region[:, 5:25] = True
    for kept in (rf.refine_c0(region, image), rf.refine_c1(region, image, "rust", 10)):
        assert not (kept & ~region).any()


def test_severity_is_lesion_on_leaf_over_leaf():
    leaf = np.zeros((10, 10), bool)
    leaf[:, :5] = True
    lesion = np.zeros((10, 10), bool)
    lesion[:2, :] = True  # 10 of its 20 pixels are on the leaf
    assert rf.severity_pct(lesion, leaf) == pytest.approx(20.0)
    assert np.isnan(rf.severity_pct(lesion, np.zeros((10, 10), bool)))


def test_every_configured_disease_has_a_group():
    from src.utils.config import load_config

    assert set(load_config("configs/config.yaml")["disease_classes"]) == set(rf.DISEASE_GROUPS)


# ---------------------------------------------------------------- tuning

GRID = {"rust": [0, 10], "necrotic": [0, 10], "mildew": [5]}


def _rec(name: str, group: str, rating: float, c1_b: dict, c0_b: float = 30.0) -> dict:
    return {"name": name, "disease": "d", "group": group, "rating": rating,
            "sev": {"A": 40.0, "B": 35.0, "C0(A)": 32.0, "C0(B)": c0_b},
            "c1": {"A": dict(c1_b), "B": dict(c1_b)}}


RECORDS = [_rec("r1", "rust", 10, {0: 20.0, 10: 11.0}), _rec("r2", "rust", 20, {0: 30.0, 10: 19.0}),
           _rec("n1", "necrotic", 5, {0: 6.0, 10: 1.0}), _rec("m1", "mildew", 8, {5: 9.0})]


def test_thresholds_minimise_group_mae_and_ties_go_to_the_first_value():
    assert tr.choose_thresholds(RECORDS, GRID, "B") == {"rust": 10, "necrotic": 0, "mildew": 5}
    tie = [_rec("r1", "rust", 10, {0: 12.0, 10: 8.0})]
    assert tr.choose_thresholds(tie, GRID, "B")["rust"] == 0
    assert tr.choose_thresholds(tie, GRID, "B")["mildew"] is None


def test_leave_one_out_never_uses_the_held_out_image():
    recs = [_rec("r1", "rust", 10, {0: 10.0, 10: 50.0}), _rec("r2", "rust", 10, {0: 50.0, 10: 10.0})]
    # each image alone prefers a different value, so leaving one out picks the value that is bad for it
    assert tr.leave_one_out(recs, GRID, "B") == [50.0, 50.0]
    assert tr.c1_predictions(recs, tr.choose_thresholds(recs, GRID, "B"), "B") == [10.0, 50.0]


def test_fallback_needs_more_than_the_resolution_limit():
    assert tr.apply_fallback(mae_c0=10.0, mae_c1=6.3, resolution_limit=3.64) == "C1"
    assert tr.apply_fallback(mae_c0=10.0, mae_c1=6.36, resolution_limit=3.64) == "C0"
    assert tr.apply_fallback(mae_c0=5.0, mae_c1=9.0, resolution_limit=3.64) == "C0"


def test_tune_reports_methods_and_choice():
    result = tr.tune(RECORDS, GRID, "B", 3.64)
    assert result["thresholds"] == {"rust": 10, "necrotic": 0, "mildew": 5}
    assert result["methods"]["C1(B)"]["mae"] == pytest.approx(1.0)
    assert result["methods"]["C0(B)"]["mae"] == pytest.approx(np.mean([20, 10, 25, 22]))
    assert result["chosen_method"] == "C1"
    report = tr.format_report(result, RECORDS, {"model": "segformer", "checkpoint": "x.pt"}, "abc")
    assert "**Method chosen: C1.**" in report and "leave-one-out" in report


# ---------------------------------------------------------------- evaluation metrics and the gold guard

CONFIG = {"severity_thresholds": {"low_max": 0.05, "medium_max": 0.20},
          "decision_mapping": {"none": "no_action", "low": "monitor", "medium": "treat", "high": "treat_urgently"},
          "annotation": {"leaf_check_locked": True},
          "severity_method": {"frozen": True, "refinement": "C0", "model": "segformer", "checkpoint": "x.pt",
                              "checkpoint_sha256": "abc", "resolution_limit": 3.64}}


def test_error_summary_bands_levels_and_decisions():
    s = sp.error_summary(pred=[4.0, 12.0, 30.0], rating=[6.0, 12.0, 25.0], diseases=["a", "a", "b"], config=CONFIG)
    assert s["pooled"]["mae"] == pytest.approx(7 / 3) and s["pooled"]["n"] == 3
    assert s["per_disease"]["a"]["n"] == 2 and s["per_disease"]["b"]["mae"] == pytest.approx(5.0)
    assert [v["n"] for v in s["by_rating_band"].values()] == [1, 1, 1]
    assert s["level_agreement"] == pytest.approx(2 / 3)  # 6% medium vs 4% low differs
    assert s["level_confusion_rating_then_method"]["medium"] == {"low": 1, "medium": 1}
    assert s["mean_signed_error"] == pytest.approx(1.0)


def test_gold_guard(tmp_path: Path):
    table = tmp_path / "gold_evaluation.md"
    eg.check_may_score_gold(CONFIG, table, "abc")
    for broken, sha in ((CONFIG | {"severity_method": CONFIG["severity_method"] | {"frozen": False}}, "abc"),
                        (CONFIG | {"annotation": {"leaf_check_locked": False}}, "abc"),
                        (CONFIG | {"severity_method": None}, "abc"),
                        (CONFIG, "other")):
        with pytest.raises(RuntimeError):
            eg.check_may_score_gold(broken, table, sha)
    table.write_text("done", encoding="utf-8")
    with pytest.raises(RuntimeError):
        eg.check_may_score_gold(CONFIG, table, "abc")


def test_method_severities_use_the_frozen_refinement():
    image = _image(GREEN, ORANGE)
    leaf = np.ones(image.shape[:2], bool)
    item = {"image": image, "leaf": leaf, "group": "rust", "regions": {"A": leaf.copy(), "B": leaf.copy()}}
    sev = eg.method_severities(item, CONFIG["severity_method"])
    assert sev == {"A": 100.0, "C(A)": 50.0, "B": 100.0, "C(B)": 50.0}
    c1 = CONFIG["severity_method"] | {"refinement": "C1", "c1_thresholds": {"rust": 20}}
    assert eg.method_severities(item, c1)["C(B)"] == 50.0


def test_gold_report_marks_placeholders_and_the_resolution_limit():
    items = [{"name": "x", "disease": "wheat leaf rust", "rating": 10.0, "image": _image(GREEN, ORANGE),
              "leaf": np.ones((10, 20), bool), "group": "rust",
              "regions": {"A": np.ones((10, 20), bool), "B": np.ones((10, 20), bool)}}]
    summary, per_image = eg.evaluate(items, CONFIG)
    report = eg.format_report(summary, CONFIG, 1, "tuning (debug)", "abc")
    assert per_image[0]["C(B)"] == 50.0
    assert "PLACEHOLDER" in report and "Resolution limit: 3.64" in report and "| C(B) | 40.00" in report


def test_real_frozen_method_matches_the_tuning_report():
    """The frozen method in the config is the one the tuning run chose."""
    import yaml

    from src.utils.config import load_config

    method = load_config("configs/config.yaml")["severity_method"]
    grid = yaml.safe_load(Path("configs/experiments/phase3_refinement.yaml").read_text(encoding="utf-8"))
    assert method["frozen"] is True and method["refinement"] in ("C0", "C1")
    assert set(method["c1_thresholds"]) == set(rf.GROUPS)
    assert all(method["c1_thresholds"][g] in grid["c1_grid"][g] for g in rf.GROUPS)
    assert (method["model"], method["checkpoint"]) == (grid["model"], grid["checkpoint"])
    assert method["resolution_limit"] == grid["resolution_limit"] == 3.64
    report = Path("report/tables/refinement_tuning.md").read_text(encoding="utf-8")
    assert f"**Method chosen: {method['refinement']}.**" in report
    for g in rf.GROUPS:
        assert f"Chosen: **{method['c1_thresholds'][g]}**" in report


def test_gold_report_sensitivity_section_and_limit_beside_results():
    rows = [{"name": n, "disease": "wheat leaf rust", "rating": r, "A": a, "B": a, "C(A)": c, "C(B)": c}
            for n, r, a, c in (("x", 10.0, 90.0, 12.0), ("y", 30.0, 95.0, 70.0))]
    without = {"names": ["y"], "reason": "label conflict", "n": 1, "summary": eg.summarise(rows[:1], CONFIG)}
    report = eg.format_report(eg.summarise(rows, CONFIG), CONFIG, 2, "gold", "abc", without=without)
    assert "## Sensitivity: without `y` (1 images)" in report and "label conflict" in report
    assert "| C(B) | 21.00" in report and "| C(B) | 2.00" in report
    assert report.count("| 3.64 |") == 8  # the limit beside every pooled row, with and without
