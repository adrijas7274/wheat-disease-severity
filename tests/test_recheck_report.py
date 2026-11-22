import numpy as np
import pytest

from src.severity.recheck_report import lins_ccc, same_leaf, severity_level

TH = {"low_max": 0.05, "medium_max": 0.20}


def test_severity_level_bins():
    assert severity_level(0, TH) == "none"
    assert severity_level(0.01, TH) == "low"
    assert severity_level(4.99, TH) == "low"
    assert severity_level(5, TH) == "medium"
    assert severity_level(19.99, TH) == "medium"
    assert severity_level(20, TH) == "high"
    assert severity_level(100, TH) == "high"


def test_ccc_perfect_and_shifted():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    assert lins_ccc(x, x) == pytest.approx(1.0)
    # Pearson r is 1 for a shift, but CCC penalises the bias
    assert lins_ccc(x, x + 1) < 1.0
    # hand value: var_x = var_y = 1.25, cov = 1.25, bias^2 = 1 -> 2.5 / 3.5
    assert lins_ccc(x, x + 1) == pytest.approx(2.5 / 3.5)


def test_same_leaf_requires_mutual_containment():
    a = np.zeros((10, 10), bool)
    a[:, :5] = True
    b = np.zeros((10, 10), bool)
    b[:, 5:] = True
    assert same_leaf(a, a, (1, 1), (2, 2))
    assert not same_leaf(a, b, (1, 1), (7, 7))
    # one click inside both leaves is not enough
    assert not same_leaf(a, a | b, (1, 1), (7, 7))
