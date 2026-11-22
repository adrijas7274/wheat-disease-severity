import cv2
import numpy as np
import pytest

from src.corruptions.corruptions import corrupt
from src.uncertainty import quality_gate as qg


@pytest.fixture
def photo() -> np.ndarray:
    rng = np.random.default_rng(1)
    img = np.zeros((300, 400, 3), np.uint8)
    img[:] = (60, 130, 50)
    for _ in range(60):  # texture: random lesions-like blobs with sharp edges
        x, y = int(rng.integers(0, 400)), int(rng.integers(0, 300))
        cv2.circle(img, (x, y), int(rng.integers(4, 14)), tuple(int(v) for v in rng.integers(60, 220, 3)), -1)
    return img


def _f(photo, name, level):
    return qg.features(corrupt(photo, name, level, seed=42, image_id="a.jpg"))


def test_features_move_in_the_expected_direction(photo):
    clean = qg.features(photo)
    assert set(clean) == set(qg.FEATURES) and clean["min_side"] == 300
    assert _f(photo, "gaussian_blur", 4)["sharpness"] < 0.5 * clean["sharpness"]
    assert _f(photo, "sensor_noise", 4)["noise"] > 3 * clean["noise"] + 1
    assert _f(photo, "under_exposure", 4)["luma"] < clean["luma"] < _f(photo, "over_exposure", 4)["luma"]
    assert _f(photo, "over_exposure", 5)["clip_high"] > clean["clip_high"]
    assert _f(photo, "colour_cast", 5)["cast"] != pytest.approx(clean["cast"], abs=0.02)


def test_features_do_not_depend_on_photo_size(photo):
    big = cv2.resize(photo, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    a, b = qg.features(photo), qg.features(big)
    assert b["luma"] == pytest.approx(a["luma"], abs=0.02) and b["min_side"] == 900


def test_ranges_and_failed_checks():
    ref = [{"sharpness": s, "noise": 1.0 + 0.01 * s, "luma": 0.3 + 0.004 * s, "clip_high": 0.0, "clip_low": 0.0,
            "cast": 0.1, "min_side": 500.0} for s in range(1, 101)]
    ranges = qg.fit_ranges(ref, tail_pct=5)
    assert ranges["sharpness"][1] is None and ranges["noise"][0] is None and None not in ranges["luma"]
    assert ranges["min_side"] == [qg.MIN_SIDE_PX, None]
    ok = dict(ref[50])
    assert qg.failed_checks(ok, ranges) == []
    assert qg.failed_checks(ok | {"sharpness": 0.5}, ranges) == ["sharpness"]
    assert qg.failed_checks(ok | {"noise": 9.0, "luma": 0.99}, ranges) == ["noise", "luma"]
    assert qg.failed_checks(ok | {"min_side": 100.0}, ranges) == ["min_side"]
    flagged = np.mean([bool(qg.failed_checks(f, ranges)) for f in ref])
    assert flagged <= 0.21  # at most the tails of the checked features


def test_feature_vector_length():
    assert len(qg.feature_vector({k: 1.0 for k in qg.FEATURES})) == len(qg.FEATURES)


def test_blockiness_rises_with_jpeg_compression(photo):
    clean = qg.blockiness(photo)
    assert 0.8 < clean < 1.3
    assert qg.blockiness(corrupt(photo, "jpeg", 5, seed=42, image_id="a.jpg")) > clean + 0.2
    assert qg.blockiness(corrupt(photo, "gaussian_blur", 5, seed=42, image_id="a.jpg")) < clean + 0.2


def test_fit_ranges_total_keeps_the_overall_clean_failure_rate_under_the_target():
    rng = np.random.default_rng(0)
    feats = [{"sharpness": float(rng.lognormal(5, 1)), "noise": float(rng.lognormal(0, 0.5)), "luma": float(rng.uniform(0.3, 0.6)),
              "clip_high": float(rng.uniform(0, 0.05)), "clip_low": float(rng.uniform(0, 0.05)), "blockiness": float(rng.uniform(0.9, 1.2)),
              "min_side": float(rng.uniform(150, 1500)), "cast": 0.1} for _ in range(200)]
    ranges, tail, rate = qg.fit_ranges_total(feats, 0.05)
    assert rate <= 0.05 and 0 < tail < 5 and set(ranges) == set(qg.CHECKS_V2)
    assert ranges["min_side"][0] is not None and ranges["min_side"][1] is None
    looser, _, rate_looser = qg.fit_ranges_total(feats, 0.15)
    assert rate_looser >= rate
