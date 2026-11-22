import json
from pathlib import Path

from src.data.plantseg_stats import compute_crop_stats, load_split_classes


def _write_annotation(path: Path, file_names: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    images = [{"id": i, "file_name": name} for i, name in enumerate(file_names)]
    path.write_text(json.dumps({"images": images, "annotations": [], "categories": []}), encoding="utf-8")


def test_load_split_classes(tmp_path: Path) -> None:
    root = tmp_path / "plantseg"
    _write_annotation(root / "coco_annotations" / "annotation_train.json", [
        "tomato_early_blight_1.jpg", "potato_late_blight_1.jpg",
    ])
    _write_annotation(root / "coco_annotations" / "annotation_val.json", ["tomato_early_blight_2.jpg"])
    _write_annotation(root / "coco_annotations" / "annotation_test.json", ["rice_blast_1.jpg"])

    split_classes = load_split_classes(root)

    assert split_classes["train"] == ["tomato early blight", "potato late blight"]
    assert split_classes["val"] == ["tomato early blight"]
    assert split_classes["test"] == ["rice blast"]


def test_compute_crop_stats_counts_and_bottleneck() -> None:
    split_classes = {
        "train": ["tomato early blight"] * 3 + ["tomato late blight"] * 1,
        "val": ["tomato early blight"] * 1,
        "test": ["rice blast"] * 2,
    }

    rows = {row["crop"]: row for row in compute_crop_stats(split_classes)}

    tomato = rows["tomato"]
    assert tomato["num_diseases"] == 2
    assert tomato["total_images"] == 5
    assert tomato["min_images_per_disease"] == 1  # tomato late blight has only 1
    assert tomato["train_count"] == 4
    assert tomato["val_count"] == 1
    assert tomato["test_count"] == 0

    rice = rows["rice"]
    assert rice["total_images"] == 2
    assert rice["test_count"] == 2


def test_compute_crop_stats_unsupported_crop_is_zero() -> None:
    split_classes = {"train": ["tomato early blight"], "val": [], "test": []}

    rows = {row["crop"]: row for row in compute_crop_stats(split_classes)}

    assert rows["cotton"] == {
        "crop": "cotton",
        "num_diseases": 0,
        "total_images": 0,
        "min_images_per_disease": 0,
        "train_count": 0,
        "val_count": 0,
        "test_count": 0,
    }
