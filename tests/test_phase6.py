import numpy as np
import pytest

from src.uncertainty import phase6 as p6

CONFIG = {"severity_thresholds": {"low_max": 0.05, "medium_max": 0.20},
          "decision_mapping": {"none": "no_action", "low": "monitor", "medium": "treat", "high": "treat_urgently"}, "seed": 42}
EXPERIMENT = {"unreliable_shift": 3.64, "coverages": [0.8, 0.9], "gate_tail_pct": 2.5, "n_bootstrap": 20}


def _features(noise: float, sharpness: float = 200.0) -> dict:
    return {"sharpness": sharpness, "noise": noise, "luma": 0.45, "clip_high": 0.0, "clip_low": 0.0, "cast": 0.2, "min_side": 400.0}


def _rec(name, corruption, level, severity, noise=1.0, **scores) -> dict:
    base = {"name": name, "disease": "wheat leaf rust", "corruption": corruption, "level": level, "severity": severity,
            "leaf_share": 0.3, "features": _features(noise), "entropy": 0.1, "tta": 0.0, "photometric": 0.0}
    return base | scores


def _split(n_images: int, seed: int) -> list[dict]:
    """Clean estimate 10%; sensor noise moves it by a noise-dependent amount that the photometric score tracks."""
    rng = np.random.default_rng(seed)
    records = []
    for k in range(n_images):
        name = f"img{seed}_{k}"
        records.append(_rec(name, "clean", 0, 10.0, noise=1.0 + 0.05 * rng.random()))
        for corruption in ("sensor_noise", "jpeg"):
            for level in range(1, 6):
                err = (2.0 * level if corruption == "sensor_noise" else 0.3) * (0.5 + rng.random())
                records.append(_rec(name, corruption, level, 10.0 + err, noise=1.0 + (level if corruption == "sensor_noise" else 0.0),
                                    photometric=err + 0.2 * rng.random(), tta=0.2 * rng.random()))
    return records


def test_add_errors_uses_the_clean_estimate_of_the_same_image():
    records = [_rec("a", "clean", 0, 4.0), _rec("a", "jpeg", 1, 9.0), _rec("a", "jpeg", 2, float("nan")),
               _rec("b", "jpeg", 1, 5.0)]  # b has no clean estimate and is dropped
    out = p6.add_errors(records, CONFIG, 3.64)
    assert [r["name"] for r in out] == ["a", "a", "a"]
    assert out[0]["shift"] == 0 and out[0]["flip"] == 0 and out[0]["unreliable"] == 0
    assert out[1]["shift"] == 5.0 and out[1]["flip"] == 1 and out[1]["unreliable"] == 1  # low -> medium
    assert np.isnan(out[2]["shift"]) and out[2]["flip"] == 1 and out[2]["unreliable"] == 1
    assert out[1]["margin"] == pytest.approx(-4.0)  # 9% is 4 points from the 5% boundary


def test_policy_thresholds_and_outcome():
    recs = p6.add_errors([_rec("a", "clean", 0, 10.0)] + [_rec("a", "jpeg", 1, 10.0 + e) for e in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)], CONFIG, 3.64)[1:]
    score = np.arange(10, dtype=float)
    gate = np.array([False] * 9 + [True])
    thr = p6.policy_thresholds(recs, score, gate, [0.8])["0.8"]
    out = p6.policy_outcome(recs, score, gate, thr)
    assert out["retake"] == pytest.approx(0.1) and out["answered"] == pytest.approx(0.8, abs=0.11)
    assert out["shift_answered"] < out["shift_all"] < out["shift_refused"]


def test_analyse_fits_on_validation_and_reports_on_test():
    val, test = _split(30, 1), _split(30, 2)
    gate_set = {"skip": [{"name": "s", "features": _features(9.0), "leaf_share": 0.01}], "wide (non-disputed)": []}
    res, curves = p6.analyse(val, test, gate_set, EXPERIMENT, CONFIG)
    t = res["test_table"]
    assert t["n"] == 30 * 10 and t["n_images"] == 30
    best = t["scores"][res["policy_score"]]
    assert best["shift"]["at_0.8"]["risk"] < t["base"]["shift"]            # abstaining lowers the error
    assert t["scores"]["oracle_shift"]["shift"]["aurc"] <= best["shift"]["aurc"]
    assert t["scores"]["photometric"]["auroc_unreliable"] > 0.9
    assert res["gate"]["matrix"]["rate"]["sensor_noise"]["5"] == 1.0 and res["gate"]["matrix"]["rate"]["jpeg"]["5"] < 0.2
    assert res["gate_set"]["sets"]["skip"]["either"] == 1.0 and np.isnan(res["gate_set"]["sets"]["wide (non-disputed)"]["photo"])
    assert set(curves) >= {"photometric", "oracle_shift", "oracle_flip"}
    report = p6.format_report(res, EXPERIMENT | {"colour_stage": {"variant": "none", "thresholds": {"rust": 10}}}, CONFIG, "abc")
    assert "PLACEHOLDER" in report and "Risk-coverage" in report and "(policy score)" in report


def test_plot_writes_both_figures(tmp_path):
    res, curves = p6.analyse(_split(20, 1), _split(20, 2), {"skip": []}, EXPERIMENT, CONFIG)
    p6.plot(res, curves, tmp_path)
    assert (tmp_path / "risk_coverage.png").exists() and (tmp_path / "gate_retake_rate.png").exists()


def test_gate_coverage_counts_the_unreliable_estimates_the_gate_catches():
    ranges = {"noise": [None, 2.0]}
    records = p6.add_errors([_rec("a", "clean", 0, 10.0), _rec("a", "sensor_noise", 1, 20.0, noise=5.0),  # moved, caught
                             _rec("a", "sensor_noise", 2, 20.0, noise=1.0),                                 # moved, missed
                             _rec("a", "jpeg", 1, 10.5, noise=5.0)], CONFIG, 3.64)                          # stable, sent back
    pool = p6.corrupted(records)
    out = p6.gate_coverage(pool, ranges, refused=np.array([True, True, True]))
    noise, jpeg = out["sensor_noise"]["all"], out["jpeg"]["all"]
    assert noise["unreliable"] == 1.0 and noise["caught"] == 0.5 and noise["policy_caught"] == 1.0
    assert noise["shift_passed"] == pytest.approx(10.0) and out["sensor_noise"]["1"]["caught"] == 1.0
    assert jpeg["unreliable"] == 0.0 and jpeg["false_retake"] == 1.0 and np.isnan(jpeg["caught"])
    assert np.isnan(out["colour_cast"]["all"]["retake"])  # no records of that corruption


def test_colour_stage_accepts_one_variant_or_one_per_group():
    variants = {"none": [], "denoise": ["denoise"]}
    steps, thr = p6.colour_stage({"variants": variants, "colour_stage": {"variant": "denoise", "thresholds": {"rust": 5, "necrotic": 15, "mildew": 8}}})
    assert steps == {"rust": ["denoise"], "necrotic": ["denoise"], "mildew": ["denoise"]} and thr["necrotic"] == 15
    per = {"rust": {"variant": "denoise", "threshold": 5}, "necrotic": {"variant": "none", "threshold": 15}, "mildew": {"variant": "none", "threshold": 8}}
    steps, thr = p6.colour_stage({"variants": variants, "colour_stage": {"per_group": per}})
    assert steps["rust"] == ["denoise"] and steps["necrotic"] == [] and thr == {"rust": 5, "necrotic": 15, "mildew": 8}
    assert "per group" in p6.describe_colour_stage({"colour_stage": {"per_group": per}})
