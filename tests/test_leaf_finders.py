"""Phase 8 leaf finders: pre/post-processing geometry, the tap box and GrabCut on a synthetic leaf."""

import numpy as np

from src.mobile import leaf_finders as lf


def test_sam_preprocess_pads_to_1024_and_scales_long_side():
    img = np.full((300, 600, 3), 128, np.uint8)
    x, scale = lf.sam_preprocess(img)
    assert x.shape == (1, 3, 1024, 1024) and scale == 1024 / 600
    assert np.allclose(x[0, :, 600:, :], 0)  # padding below the resized 512-high photo stays zero
    assert not np.allclose(x[0, :, :500, :], 0)


def test_sam_postprocess_returns_photo_sized_masks_in_the_right_place():
    low = np.full((3, 256, 256), -5.0, np.float32)
    low[:, :64, :64] = 5.0  # top-left quarter of the padded 1024 frame = top-left of a square photo
    masks = lf.sam_postprocess(low, (400, 400, 3), 1024 / 400)
    assert masks.shape == (3, 400, 400) and masks.dtype == bool
    assert masks[0, 10, 10] and not masks[0, 300, 300]


def test_tap_box_contains_the_tap_and_the_nearest_region():
    region = np.zeros((200, 300), bool)
    region[150:170, 250:280] = True
    x0, y0, x1, y1 = lf.tap_box((240, 140), region, region.shape)
    assert x0 <= 240 <= x1 and y0 <= 140 <= y1
    assert x1 >= 279 and y1 >= 169
    assert 0 <= x0 and 0 <= y0 and x1 <= 299 and y1 <= 199


def test_grabcut_finds_a_green_leaf_on_brown_soil():
    rng = np.random.default_rng(0)
    img = np.empty((240, 320, 3), np.uint8)
    img[:] = (120, 85, 50)
    img[60:180, 100:220] = (40, 150, 50)
    img = np.clip(img.astype(int) + rng.integers(-8, 9, img.shape), 0, 255).astype(np.uint8)
    region = np.zeros(img.shape[:2], bool)
    region[100:140, 140:180] = True
    leaf = lf.grabcut_leaf(img, (160, 120), region)
    truth = np.zeros_like(region)
    truth[60:180, 100:220] = True
    iou = (leaf & truth).sum() / (leaf | truth).sum()
    assert leaf[120, 160] and iou > 0.8
