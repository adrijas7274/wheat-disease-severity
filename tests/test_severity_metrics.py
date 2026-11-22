import numpy as np

from src.severity.metrics import binary_dice, binary_iou, bootstrap_ci, infected_area_ratio_error


def test_binary_iou_perfect_match():
    mask = np.array([[0, 1], [1, 0]])
    assert binary_iou(mask, mask) == 1.0


def test_binary_iou_no_overlap():
    pred = np.array([[1, 0], [0, 0]])
    true = np.array([[0, 1], [0, 0]])
    assert binary_iou(pred, true) == 0.0


def test_binary_iou_both_empty_is_perfect():
    empty = np.zeros((4, 4))
    assert binary_iou(empty, empty) == 1.0


def test_binary_iou_partial_overlap():
    pred = np.array([1, 1, 0, 0])
    true = np.array([1, 0, 0, 0])
    # intersection=1, union=2
    assert binary_iou(pred, true) == 0.5


def test_binary_dice_perfect_match():
    mask = np.array([[1, 1], [0, 0]])
    assert binary_dice(mask, mask) == 1.0


def test_binary_dice_partial_overlap():
    pred = np.array([1, 1, 0, 0])
    true = np.array([1, 0, 0, 0])
    # intersection=1, pred_sum=2, true_sum=1 -> 2*1/(2+1) = 2/3
    assert abs(binary_dice(pred, true) - 2 / 3) < 1e-9


def test_binary_dice_both_empty_is_perfect():
    empty = np.zeros((4, 4))
    assert binary_dice(empty, empty) == 1.0


def test_infected_area_ratio_error_zero_when_equal_fraction():
    pred = np.array([1, 1, 0, 0])
    true = np.array([1, 0, 1, 0])  # same fraction (0.5), different pixels
    assert infected_area_ratio_error(pred, true) == 0.0


def test_infected_area_ratio_error_nonzero():
    pred = np.array([1, 1, 1, 0])  # 0.75
    true = np.array([1, 0, 0, 0])  # 0.25
    assert abs(infected_area_ratio_error(pred, true) - 0.5) < 1e-9


def test_bootstrap_ci_empty_returns_nan():
    mean, lo, hi = bootstrap_ci([])
    assert all(v != v for v in (mean, lo, hi))  # nan != nan


def test_bootstrap_ci_constant_values_tight_interval():
    mean, lo, hi = bootstrap_ci([0.8] * 50, n_bootstrap=200)
    assert abs(mean - 0.8) < 1e-9
    assert abs(lo - 0.8) < 1e-6
    assert abs(hi - 0.8) < 1e-6


def test_bootstrap_ci_mean_matches_sample_mean():
    values = [0.1, 0.5, 0.9, 0.3, 0.7]
    mean, lo, hi = bootstrap_ci(values, n_bootstrap=500)
    assert abs(mean - sum(values) / len(values)) < 1e-9
    assert lo <= mean <= hi


def test_bootstrap_ci_reproducible_with_seed():
    values = [0.2, 0.4, 0.6, 0.8, 0.9, 0.1]
    result1 = bootstrap_ci(values, seed=123)
    result2 = bootstrap_ci(values, seed=123)
    assert result1 == result2
