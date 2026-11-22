from pathlib import Path

import numpy as np
import pytest

from src.severity import area_diagrams as sad


@pytest.mark.parametrize("style", sad.STYLES)
@pytest.mark.parametrize("pct", sad.LEVELS)
def test_lesion_area_is_exact_and_inside_leaf(style: str, pct: int):
    leaf = sad.leaf_mask()
    lesion = sad.lesion_mask(leaf, pct, style, seed=7)
    assert not (lesion & ~leaf).any()
    assert lesion.sum() == round(pct / 100 * leaf.sum())  # exact to one pixel


def test_deterministic_and_seed_dependent():
    leaf = sad.leaf_mask()
    a = sad.lesion_mask(leaf, 10, "blotch", seed=1)
    assert (a == sad.lesion_mask(leaf, 10, "blotch", seed=1)).all()
    assert (a != sad.lesion_mask(leaf, 10, "blotch", seed=2)).any()


def test_leaf_shape_is_one_tapered_blade():
    import cv2

    leaf = sad.leaf_mask()
    n, _ = cv2.connectedComponents(leaf.astype(np.uint8))
    assert n == 2  # background + one leaf
    widths = leaf.sum(axis=0)
    assert widths.argmax() < leaf.shape[1] / 3  # widest near the base, tapering to the tip


def test_render_keeps_lesion_pixels_and_leaf_area():
    leaf = sad.leaf_mask()
    for style in sad.STYLES:
        lesion = sad.lesion_mask(leaf, 20, style, seed=3)
        img = sad.render_leaf(leaf, lesion, style, seed=3)
        is_leaf_green = (img == sad.LEAF_RGB).all(axis=2)
        assert is_leaf_green.sum() == (leaf & ~lesion).sum()  # nothing drawn over healthy tissue
        assert (img[~leaf & ~is_leaf_green] != sad.LESION_RGB[style]).any(axis=1).all()


def test_bad_inputs():
    leaf = sad.leaf_mask()
    with pytest.raises(ValueError):
        sad.lesion_mask(leaf, 101, "rust", 0)
    with pytest.raises(ValueError):
        sad.lesion_mask(leaf, 5, "spots", 0)


def test_generate_all_writes_panels_and_coverage(tmp_path: Path):
    rows = sad.generate_all(seed=1, out_dir=tmp_path)
    assert len(rows) == len(sad.STYLES) * len(sad.LEVELS)
    assert all(sad.panel_path(s, tmp_path).exists() for s in sad.STYLES)
    assert (tmp_path / "coverage.csv").exists()
    assert max(abs(r["measured_pct"] - r["target_pct"]) for r in rows) < 0.01
