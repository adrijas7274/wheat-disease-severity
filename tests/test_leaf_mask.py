import numpy as np
import pytest

from src.severity.leaf_mask import mask_iou, select_leaf, tuning_rows
from src.utils.config import load_config


def _masks() -> np.ndarray:
    """Three nested candidates: small part, whole leaf, leaf + background."""
    m = np.zeros((3, 10, 10), bool)
    m[0, 4:6, 4:6] = True
    m[1, 2:8, 2:8] = True
    m[2, :, :] = True
    return m


def test_best_score_ignores_size():
    assert select_leaf(_masks(), np.array([0.9, 0.5, 0.1]), (5, 5), "best_score") == 0


def test_largest_containing_click_picks_biggest_with_click():
    masks = _masks()
    masks[2, 5, 5] = False  # the largest candidate misses the click
    assert select_leaf(masks, np.array([0.9, 0.5, 0.1]), (5, 5), "largest_containing_click") == 1


def test_largest_falls_back_to_best_score_when_no_candidate_has_click():
    masks = _masks()
    masks[:, 0, 0] = False
    assert select_leaf(masks, np.array([0.2, 0.7, 0.1]), (0, 0), "largest_containing_click") == 1


def test_min_area_takes_best_score_among_big_enough():
    # shares: 0.04, 0.36, 1.0
    assert select_leaf(_masks(), np.array([0.9, 0.5, 0.6]), (5, 5), "min_area", min_share=0.1) == 2
    assert select_leaf(_masks(), np.array([0.9, 0.5, 0.6]), (5, 5), "min_area", min_share=0.01) == 0


def test_min_area_falls_back_to_largest_and_needs_min_share():
    masks = _masks()
    masks[2] = False
    assert select_leaf(masks, np.array([0.9, 0.5, 0.6]), (5, 5), "min_area", min_share=0.9) == 1
    with pytest.raises(ValueError):
        select_leaf(masks, np.array([0.9, 0.5, 0.6]), (5, 5), "min_area")


def test_frozen_leaf_rule_in_config():
    """The leaf rule was frozen on 2026-11-11 before any gold image was processed."""
    sam = load_config("configs/config.yaml")["sam2"]
    assert sam["leaf_rule"] == "min_area"
    assert sam["leaf_min_area_share"] == 0.02
    assert sam["checkpoint"].endswith("sam2.1_hiera_tiny.pt")


def test_unknown_rule_raises():
    with pytest.raises(ValueError):
        select_leaf(_masks(), np.array([1.0, 0.0, 0.0]), (5, 5), "biggest")


def test_mask_iou():
    a, b = _masks()[0], _masks()[1]
    assert mask_iou(a, a) == 1.0
    assert mask_iou(a, b) == pytest.approx(4 / 36)


def test_tuning_rows_drop_exclusions_and_skips():
    config = load_config("configs/config.yaml")
    rows = tuning_rows(config)
    names = {r["name"] for r in rows}
    assert not names & set(config["annotation"]["tuning_exclude"])
    assert all(r["status"] == "done" and r["set"] == "tuning" for r in rows)
    assert len(rows) == 12
