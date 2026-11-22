from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.external import phase7 as p7

CLASSES = [{"keyword": "healthy", "label": "healthy"}, {"keyword": "septoria", "label": "wheat septoria blotch"},
           {"keyword": "rust", "label": "wheat stripe rust"}, {"keyword": "strip", "label": "wheat stripe rust"}]


def _img(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.full((8, 8, 3), value, np.uint8)).save(path)


def test_label_of_reads_the_folder_path_only():
    assert p7.label_of(Path("train/Healthy Wheat Leaf/rust_like_name.jpg"), CLASSES) == "healthy"
    assert p7.label_of(Path("test/Strip Rust/a.jpg"), CLASSES) == "wheat stripe rust"
    assert p7.label_of(Path("Septoria Disease/a.jpg"), CLASSES) == "wheat septoria blotch"
    assert p7.label_of(Path("other/a.jpg"), CLASSES) is None


def test_list_mendeley_drops_unlabelled_files_and_byte_identical_copies(tmp_path):
    _img(tmp_path / "train" / "healthy" / "a.png", 10)
    _img(tmp_path / "test" / "healthy" / "a_copy.png", 10)       # same bytes
    _img(tmp_path / "train" / "Septoria" / "b.png", 20)
    _img(tmp_path / "misc" / "c.png", 30)
    entries, skipped = p7.list_mendeley(tmp_path, CLASSES)
    assert [e["label"] for e in entries] == ["healthy", "wheat septoria blotch"]
    assert skipped == {"no_class": 1, "duplicate": 1}


def test_list_nwrd_pairs_images_with_masks(tmp_path):
    _img(tmp_path / "train" / "images" / "1.jpg", 10)
    _img(tmp_path / "train" / "masks" / "1.png", 255)
    _img(tmp_path / "test" / "images" / "2.jpg", 10)  # no mask
    assert [p["name"] for p in p7.list_nwrd(tmp_path)] == ["train/images/1.jpg"]


def _rec(label, sev, action="answer"):
    groups = ["rust", "necrotic", "mildew"] if label == "healthy" else ["rust"]
    return {"name": f"{label}{sev}", "label": label, "leaf_share": 0.4,
            "groups": {g: {"severity": sev, "tta": 0.0, "photometric": 0.0} for g in groups},
            "decision": {g: {"failed_checks": [], "score": 0.1, "level": "none" if sev == 0 else "low", "action_0.8": action} for g in groups}}


def test_summarise_mendeley_counts_zero_and_detected_shares():
    recs = [_rec("healthy", 0.0), _rec("healthy", 2.0), _rec("wheat stripe rust", 0.0), _rec("wheat stripe rust", 12.0, "consult")]
    s = p7.summarise_mendeley(recs, ["rust", "necrotic", "mildew"], ["0.8"], 50, 0)
    assert s["healthy"]["groups"]["mildew"]["zero"]["share"] == 0.5
    rust = s["wheat stripe rust"]["groups"]["rust"]
    assert rust["detected"]["share"] == 0.5 and rust["actions"]["0.8"]["consult"] == 0.5
    assert rust["actions"]["0.8"]["answered_severity"]["n"] == 1 and rust["levels"]["none"] == 1


def test_describe_ignores_missing_estimates():
    d = p7.describe([0.0, 1.0, float("nan"), 4.0])
    assert d["n"] == 3 and d["zero"] == pytest.approx(1 / 3) and d["le_1"] == pytest.approx(2 / 3)


def test_cap_long_side_only_shrinks_large_photos():
    big = np.zeros((4000, 6000, 3), np.uint8)
    assert p7.cap_long_side(big, 2048).shape == (1365, 2048, 3)
    small = np.zeros((300, 400, 3), np.uint8)
    assert p7.cap_long_side(small, 2048) is small and p7.cap_long_side(big, None) is big
