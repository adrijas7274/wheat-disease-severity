import numpy as np
import pytest
from PIL import Image

from src.severity import annotation_core as core
from src.severity.annotation_sets import pick_recheck, shuffled_queue


def _two_blobs() -> np.ndarray:
    """Green image with two separate red squares."""
    img = np.zeros((40, 60, 3), np.uint8)
    img[:] = (40, 160, 40)
    img[5:15, 5:15] = (200, 40, 30)
    img[25:35, 40:50] = (200, 40, 30)
    return img


def test_wand_contiguous_selects_only_seed_blob():
    sel = core.wand_select(core.to_lab(_two_blobs()), (10, 10), tolerance=10, contiguous=True)
    assert sel[5:15, 5:15].all()
    assert not sel[25:35, 40:50].any()
    assert sel.sum() == 100


def test_wand_global_selects_all_matching_and_tolerance_grows_selection():
    lab = core.to_lab(_two_blobs())
    sel = core.wand_select(lab, (10, 10), tolerance=10, contiguous=False)
    assert sel.sum() == 200
    assert core.wand_select(lab, (10, 10), tolerance=500, contiguous=False).all()


def test_brush_layer_adds_green_removes_magenta_and_rescales():
    mask = np.zeros((20, 20), bool)
    mask[10:20] = True
    layer = np.zeros((10, 10, 4), np.uint8)  # half resolution, like the display copy
    layer[0:2, :] = (0, 255, 0, 255)  # add rows 0-3 at full res
    layer[8:10, :] = (255, 0, 255, 255)  # remove rows 16-19
    out = core.apply_brush_layer(mask, layer)
    assert out[0:4].all() and not out[4:10].any()
    assert out[10:16].all() and not out[16:20].any()


def test_brush_ignores_faint_antialiased_pixels():
    mask = np.zeros((4, 4), bool)
    layer = np.zeros((4, 4, 4), np.uint8)
    layer[..., :3] = (0, 255, 0)
    layer[..., 3] = 50
    assert not core.apply_brush_layer(mask, layer).any()


def test_severity_counts_lesion_on_leaf_only():
    leaf = np.zeros((10, 10), bool)
    leaf[:, :5] = True
    lesion = np.zeros((10, 10), bool)
    lesion[:5, :] = True  # 25 px on the leaf, 25 off it
    assert core.severity(leaf, lesion) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        core.severity(np.zeros((2, 2), bool), lesion[:2, :2])


def test_render_overlay_shape_and_scale():
    img = np.zeros((100, 200, 3), np.uint8)
    m = np.zeros((100, 200), bool)
    out = core.render_overlay(img, m, m, None, scale=0.5)
    assert out.shape == (50, 100, 3) and out.dtype == np.uint8
    assert core.display_scale((3000, 5000), 1000) == pytest.approx(0.2)
    assert core.display_scale((100, 100), 1000) == 1.0


def test_log_roundtrip_latest_row_wins_and_sets_are_separate(tmp_path):
    log = tmp_path / "log.csv"
    core.append_log(log, {"name": "a.jpg", "set": "pilot", "status": "skipped"})
    core.append_log(log, {"name": "a.jpg", "set": "pilot", "status": "done"})
    core.append_log(log, {"name": "a.jpg", "set": "gold", "status": "skipped"})
    assert core.load_status(log, "pilot")["a.jpg"]["status"] == "done"
    assert core.load_status(log, "gold")["a.jpg"]["status"] == "skipped"
    assert core.load_status(tmp_path / "missing.csv", "pilot") == {}


def test_save_masks_full_res_binary(tmp_path):
    leaf = np.zeros((7, 9), bool)
    leaf[2:5, 3:6] = True
    core.save_masks(tmp_path, "pilot", "x (1).jpg", leaf, leaf & False)
    leaf_p, lesion_p = core.mask_paths(tmp_path, "pilot", "x (1).jpg")
    arr = np.array(Image.open(leaf_p))
    assert arr.shape == (7, 9) and set(np.unique(arr)) == {0, 255}
    assert np.array(Image.open(lesion_p)).max() == 0


def _queues():
    return {"d1": [{"name": f"d1_{i}"} for i in range(3)], "d2": [{"name": f"d2_{i}"} for i in range(2)]}


def test_next_row_follows_queue_order_and_replaces_skips():
    q, quotas = _queues(), {"d1": 1, "d2": 2}
    assert core.next_row(q, quotas, {})["name"] == "d1_0"
    status = {"d1_0": {"status": "skipped"}}
    assert core.next_row(q, quotas, status)["name"] == "d1_1"  # skip -> next in queue, not a free choice
    status["d1_1"] = {"status": "done"}
    assert core.next_row(q, quotas, status)["name"] == "d2_0"


def test_next_row_none_when_quota_met_or_queue_exhausted():
    q, quotas = _queues(), {"d1": 1, "d2": 2}
    status = {"d1_0": {"status": "done"}, "d2_0": {"status": "done"}, "d2_1": {"status": "skipped"}}
    assert core.next_row(q, quotas, status) is None  # d2 is short by one but out of images
    prog = core.progress(q, quotas, status)
    assert prog[1] == {"disease": "d2", "done": 1, "quota": 2, "skipped": 1, "incomplete": 0, "left_in_queue": 0}
    assert core.set_finished(prog)


def test_shuffled_queue_deterministic_and_salted():
    rows = [{"name": str(i)} for i in range(20)]
    assert shuffled_queue(rows, 42, "gold:a") == shuffled_queue(rows, 42, "gold:a")
    assert shuffled_queue(rows, 42, "gold:a") != shuffled_queue(rows, 42, "gold:b")
    assert sorted(r["name"] for r in shuffled_queue(rows, 42, "x")) == sorted(r["name"] for r in rows)


def test_pick_recheck_deterministic_order_independent():
    names = [f"n{i}" for i in range(54)]
    a = pick_recheck(names, 5, 42)
    assert a == pick_recheck(list(reversed(names)), 5, 42)
    assert len(set(a)) == 5
    with pytest.raises(ValueError):
        pick_recheck(names[:3], 5, 42)


def test_largest_part_fraction():
    m = np.zeros((10, 10), bool)
    assert core.largest_part_fraction(m) == 0.0
    m[0:4, 0:4] = True  # 16 px
    assert core.largest_part_fraction(m) == 1.0
    m[8, 8] = True
    m[6, 0:4] = True  # +1 +4 separate pieces -> 16/21
    assert core.largest_part_fraction(m) == pytest.approx(16 / 21)
