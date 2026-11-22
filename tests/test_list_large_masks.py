from pathlib import Path

import numpy as np
from PIL import Image

from src.data.list_large_masks import find_large_mask_tagged_images, format_table, mask_area_fraction


def test_mask_area_fraction_full(tmp_path: Path) -> None:
    mask_path = tmp_path / "mask.png"
    Image.fromarray(np.ones((10, 10), dtype=np.uint8)).save(mask_path)
    assert mask_area_fraction(mask_path) == 1.0


def test_mask_area_fraction_quarter(tmp_path: Path) -> None:
    mask_path = tmp_path / "mask.png"
    arr = np.zeros((10, 10), dtype=np.uint8)
    arr[:5, :5] = 1
    Image.fromarray(arr).save(mask_path)
    assert mask_area_fraction(mask_path) == 0.25


def test_find_large_mask_tagged_images_excludes_untagged_and_small_masks(tiny_config: dict) -> None:
    # tiny_plantseg_dir fixture masks are all-zero (fraction 0.0), so nothing
    # should ever exceed any positive threshold - this just proves untagged
    # rows (e.g. stripe_5.jpg) are excluded regardless of mask content.
    results = find_large_mask_tagged_images(tiny_config, threshold=0.90)
    names = {r["name"] for r in results}
    assert "stripe_5.jpg" not in names  # untagged, must be excluded even if it had a big mask
    assert results == []  # all fixture masks are empty (fraction 0.0)


def test_find_large_mask_tagged_images_includes_tagged_large_mask(tmp_path: Path) -> None:
    import csv

    root = tmp_path / "plantseg"
    (root / "images" / "train").mkdir(parents=True)
    (root / "annotations" / "train").mkdir(parents=True)

    with open(root / "Metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Index", "Plant", "Disease", "Resolution", "Label file",
                          "Mask ratio", "URL", "License", "Split"])
        writer.writerow(["a.jpg", 0, "Wheat", "wheat stripe rust", "10x10", "a.png",
                          0.95, "http://x", "CC-BY-NC", "Training"])

    Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(root / "images" / "train" / "a.jpg")
    mask_arr = np.ones((10, 10), dtype=np.uint8)  # fraction 1.0, well over 0.90
    Image.fromarray(mask_arr).save(root / "annotations" / "train" / "a.png")

    processed = tmp_path / "processed"
    processed.mkdir()
    with open(processed / "wheat_tags.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "plant", "disease", "split", "tag", "tagged_at"])
        writer.writerow(["a.jpg", "Wheat", "wheat stripe rust", "Training", "close_up", "ts"])

    config = {
        "crop": "wheat",
        "disease_classes": ["wheat stripe rust"],
        "data": {"plantseg_dir": str(root), "processed_dir": str(processed)},
    }

    results = find_large_mask_tagged_images(config, threshold=0.90)

    assert len(results) == 1
    assert results[0]["name"] == "a.jpg"
    assert results[0]["tag"] == "close_up"
    assert results[0]["mask_area_fraction"] == 1.0


def test_format_table() -> None:
    results = [{"name": "a.jpg", "disease": "wheat stripe rust", "split": "Training",
                "tag": "close_up", "mask_area_fraction": 0.95}]
    table = format_table(results, 0.90)
    assert "Count: 1" in table
    assert "a.jpg" in table
    assert "95.0%" in table
