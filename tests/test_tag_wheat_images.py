from pathlib import Path

import numpy as np
from PIL import Image

from src.data.tag_wheat_images import (
    OUTLINE_COLOR, REVIEW_LISTS, do_tag, do_undo, large_mask_review_rows, load_ordered_rows,
    mask_outline, next_untagged_index, overlay_outline, render, review_status, rows_for_disease,
    tagged_rows_for_disease, tags_csv_path,
)
from src.data.wheat_tags import load_tags


def test_outline_is_not_filled(tmp_path: Path) -> None:
    # 40x40 image, white background; mask has a 20x20 lesion square in the centre.
    img_path = tmp_path / "img.jpg"
    Image.fromarray(np.full((40, 40, 3), 255, dtype=np.uint8)).save(img_path)
    mask_path = tmp_path / "mask.png"
    mask_arr = np.zeros((40, 40), dtype=np.uint8)
    mask_arr[10:30, 10:30] = 1
    Image.fromarray(mask_arr).save(mask_path)

    plain, outlined = overlay_outline(img_path, mask_path, max_dim=40)
    outlined_arr = np.array(outlined)

    # deep inside the lesion (well away from the boundary band): untouched, still white
    assert tuple(outlined_arr[20, 20]) == (255, 255, 255)
    # far outside the lesion: also untouched
    assert tuple(outlined_arr[2, 2]) == (255, 255, 255)
    # right on the lesion boundary: cyan
    assert tuple(outlined_arr[10, 20]) == OUTLINE_COLOR


def test_mask_outline_empty_mask_is_all_zero(tmp_path: Path) -> None:
    mask_path = tmp_path / "mask.png"
    Image.fromarray(np.zeros((20, 20), dtype=np.uint8)).save(mask_path)

    outline = mask_outline(mask_path, (20, 20))

    assert np.array(outline).sum() == 0


def test_load_ordered_rows_filters_and_sorts(tiny_config: dict) -> None:
    rows = load_ordered_rows(tiny_config)
    names = [r["name"] for r in rows]
    assert names == sorted(names)
    assert "tomato_1.jpg" not in names  # wrong plant
    assert "scab_1.jpg" not in names  # excluded disease


def test_rows_for_disease_filters_to_one_class(tiny_config: dict) -> None:
    rows = rows_for_disease(tiny_config, "wheat leaf rust")
    assert {r["name"] for r in rows} == {"leaf_1.jpg", "leaf_2.jpg", "leaf_3.jpg"}


def test_tag_and_advance_flow(tiny_config: dict) -> None:
    plantseg_dir = Path(tiny_config["data"]["plantseg_dir"])
    tags_csv = tags_csv_path(tiny_config)
    rows = load_ordered_rows(tiny_config)

    # the only untagged row in the fixture is stripe_5.jpg
    start_index = next_untagged_index(rows, load_tags(tags_csv))
    assert rows[start_index]["name"] == "stripe_5.jpg"

    plain, outlined, status, next_index = do_tag(plantseg_dir, tags_csv, rows, "close_up", start_index)

    assert load_tags(tags_csv)["stripe_5.jpg"] == "close_up"
    assert next_index is None  # nothing left untagged in the fixture
    assert plain is None
    assert outlined is None
    assert "Class complete" in status


def test_undo_restores_previous_image(tiny_config: dict) -> None:
    plantseg_dir = Path(tiny_config["data"]["plantseg_dir"])
    tags_csv = tags_csv_path(tiny_config)
    rows = load_ordered_rows(tiny_config)

    start_index = next_untagged_index(rows, load_tags(tags_csv))
    do_tag(plantseg_dir, tags_csv, rows, "close_up", start_index)
    assert "stripe_5.jpg" in load_tags(tags_csv)

    plain, outlined, status, index = do_undo(plantseg_dir, tags_csv, rows, None)

    assert "stripe_5.jpg" not in load_tags(tags_csv)
    assert rows[index]["name"] == "stripe_5.jpg"
    assert plain is not None
    assert outlined is not None
    assert plain.size == outlined.size


def test_render_shows_remaining_count(tiny_config: dict) -> None:
    plantseg_dir = Path(tiny_config["data"]["plantseg_dir"])
    tags_csv = tags_csv_path(tiny_config)
    rows = rows_for_disease(tiny_config, "wheat stripe rust")  # 6 rows: 5 tagged, 1 untagged
    index = next_untagged_index(rows, load_tags(tags_csv))

    plain, outlined, status = render(plantseg_dir, tags_csv, rows, index)

    assert "5/6" in status
    assert "1 remaining" in status


def test_render_all_tagged_returns_none_images(tiny_config: dict) -> None:
    plantseg_dir = Path(tiny_config["data"]["plantseg_dir"])
    tags_csv = tags_csv_path(tiny_config)
    rows = load_ordered_rows(tiny_config)

    plain, outlined, status = render(plantseg_dir, tags_csv, rows, None)

    assert plain is None
    assert outlined is None
    assert "Class complete" in status


def test_tagged_rows_for_disease_filters_and_sorts(tiny_config: dict) -> None:
    rows = tagged_rows_for_disease(tiny_config, "wheat stripe rust")
    names = [r["name"] for r in rows]
    # stripe_5 untagged, excluded; stripe_6 is disputed but still tagged, so included here
    assert names == ["stripe_1.jpg", "stripe_2.jpg", "stripe_3.jpg", "stripe_4.jpg", "stripe_6.jpg"]
    by_name = {r["name"]: r["tag"] for r in rows}
    assert by_name == {
        "stripe_1.jpg": "close_up", "stripe_2.jpg": "wide",
        "stripe_3.jpg": "non_photo", "stripe_4.jpg": "skip", "stripe_6.jpg": "close_up",
    }


def test_large_mask_review_rows_includes_image_and_mask_fields(tmp_path: Path) -> None:
    import csv

    import numpy as np

    root = tmp_path / "plantseg"
    (root / "images" / "train").mkdir(parents=True)
    (root / "annotations" / "train").mkdir(parents=True)

    with open(root / "Metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Index", "Plant", "Disease", "Resolution", "Label file",
                          "Mask ratio", "URL", "License", "Split"])
        writer.writerow(["a.jpg", 0, "Wheat", "wheat powdery mildew", "10x10", "a.png",
                          0.95, "http://x", "CC-BY-NC", "Training"])

    Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(root / "images" / "train" / "a.jpg")
    Image.fromarray(np.ones((10, 10), dtype=np.uint8)).save(root / "annotations" / "train" / "a.png")

    processed = tmp_path / "processed"
    processed.mkdir()
    with open(processed / "wheat_tags.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "plant", "disease", "split", "tag", "tagged_at"])
        writer.writerow(["a.jpg", "Wheat", "wheat powdery mildew", "Training", "close_up", "ts"])

    config = {
        "crop": "wheat",
        "disease_classes": ["wheat powdery mildew"],
        "data": {"plantseg_dir": str(root), "processed_dir": str(processed)},
    }

    rows = large_mask_review_rows(config, "wheat powdery mildew", threshold=0.90)

    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "a.jpg"
    assert row["tag"] == "close_up"
    assert row["mask_area_fraction"] == 1.0
    assert row["label_file"] == "a.png"  # needed for mask_path()


def test_review_status_with_and_without_mask_area() -> None:
    row = {"tag": "close_up", "disease": "wheat stripe rust", "name": "a.jpg"}
    status = review_status(row, 0, 5, "All wheat stripe rust")
    assert "1/5" in status
    assert "current tag: close_up" in status
    assert "mask area" not in status

    row_with_mask = dict(row, mask_area_fraction=0.953)
    status2 = review_status(row_with_mask, 2, 5, "Large-mask")
    assert "3/5" in status2
    assert "mask area 95.3%" in status2


def test_review_lists_cover_expected_groups() -> None:
    assert set(REVIEW_LISTS) == {
        "Large-mask (>90%) wheat powdery mildew",
        "All wheat stripe rust",
        "All wheat bacterial leaf streak",
    }
