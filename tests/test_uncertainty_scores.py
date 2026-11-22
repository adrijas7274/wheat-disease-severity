import numpy as np
import pytest

from src.uncertainty import scores as sc

TH = {"low_max": 0.05, "medium_max": 0.20}


def test_photometric_views_are_small_changes_in_both_directions():
    image = np.full((8, 8, 3), 120, np.uint8)
    views = sc.photometric_views(image)
    assert len(views) == len(sc.PHOTOMETRIC_VIEWS) and all(v.shape == image.shape and v.dtype == np.uint8 for v in views)
    assert views[0].mean() > image.mean() > views[1].mean()
    assert views[2][..., 0].mean() > views[2][..., 2].mean() and views[3][..., 0].mean() < views[3][..., 2].mean()
    assert all(abs(float(v.mean()) - 120) < 15 for v in views)


def test_spread_ignores_missing_values():
    assert sc.spread([1.0, 3.0]) == pytest.approx(1.0)
    assert sc.spread([1.0, float("nan"), 3.0]) == pytest.approx(1.0)
    assert sc.spread([2.0]) == 0.0 and sc.spread([]) == 0.0


def test_threshold_margin():
    assert sc.threshold_margin(0.0, TH) == 0.0
    assert sc.threshold_margin(4.0, TH) == pytest.approx(1.0)
    assert sc.threshold_margin(12.0, TH) == pytest.approx(7.0)
    assert sc.threshold_margin(26.0, TH) == pytest.approx(6.0)


def test_risk_coverage_with_a_perfect_and_a_useless_score():
    risk = np.array([0.0, 0.0, 0.0, 10.0, 10.0])
    perfect = risk.copy()
    cov, curve = sc.risk_coverage(perfect, risk, n_points=5)
    assert list(np.round(cov, 2)) == [0.2, 0.4, 0.6, 0.8, 1.0]
    assert list(curve) == pytest.approx([0, 0, 0, 2.5, 4.0])
    assert sc.risk_at_coverage(perfect, risk, 0.6) == 0.0 and sc.risk_at_coverage(perfect, risk, 1.0) == pytest.approx(4.0)
    mixed = np.array([10.0, 0.0, 10.0, 0.0, 0.0])  # a constant score keeps the given order
    assert sc.aurc(mixed, mixed) < sc.aurc(np.zeros(5), mixed) < sc.aurc(-mixed, mixed)


def test_threshold_for_coverage_keeps_about_that_share():
    score = np.arange(100, dtype=float)
    t = sc.threshold_for_coverage(score, 0.8)
    assert (score <= t).mean() == pytest.approx(0.8, abs=0.01)
