import csv
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

DISEASE_CLASSES = ["wheat stripe rust", "wheat leaf rust"]

# (name, plant, disease, split, tag_or_None, disputed)
FIXTURE_ROWS = [
    ("stripe_1.jpg", "Wheat", "wheat stripe rust", "Training", "close_up", False),
    ("stripe_2.jpg", "Wheat", "wheat stripe rust", "Training", "wide", False),
    ("stripe_3.jpg", "Wheat", "wheat stripe rust", "Training", "non_photo", False),
    ("stripe_4.jpg", "Wheat", "wheat stripe rust", "Training", "skip", False),
    ("stripe_5.jpg", "Wheat", "wheat stripe rust", "Training", None, False),  # untagged
    ("stripe_6.jpg", "Wheat", "wheat stripe rust", "Training", "close_up", True),  # disputed but train - still included
    ("leaf_1.jpg", "Wheat", "wheat leaf rust", "Validation", "close_up", False),
    ("leaf_2.jpg", "Wheat", "wheat leaf rust", "Test", "close_up", False),
    ("leaf_3.jpg", "Wheat", "wheat leaf rust", "Test", "close_up", True),  # disputed - excluded from test
    ("scab_1.jpg", "Wheat", "wheat head scab", "Training", "close_up", False),  # excluded disease
    ("tomato_1.jpg", "Tomato", "tomato early blight", "Training", "close_up", False),  # excluded plant
]


@pytest.fixture
def tiny_plantseg_dir(tmp_path: Path) -> Path:
    """A minimal PlantSeg-v7-shaped directory: Metadata.csv + tiny images/masks."""
    root = tmp_path / "plantseg_v7"
    for split_dir in ["train", "val", "test"]:
        (root / "images" / split_dir).mkdir(parents=True)
        (root / "annotations" / split_dir).mkdir(parents=True)

    split_dir_map = {"Training": "train", "Validation": "val", "Test": "test"}

    with open(root / "Metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Index", "Plant", "Disease", "Resolution", "Label file",
                          "Mask ratio", "URL", "License", "Split"])
        for name, plant, disease, split, _tag, _disputed in FIXTURE_ROWS:
            label_file = name.replace(".jpg", ".png")
            writer.writerow([name, 0, plant, disease, "10x10", label_file, 0.1, "http://x", "CC-BY-NC", split])

            split_dir = split_dir_map[split]
            img = Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8))
            img.save(root / "images" / split_dir / name)
            mask = Image.fromarray(np.zeros((10, 10), dtype=np.uint8))
            mask.save(root / "annotations" / split_dir / label_file)

    return root


@pytest.fixture
def tiny_tags_csv(tmp_path: Path) -> Path:
    tags_path = tmp_path / "processed" / "wheat_tags.csv"
    tags_path.parent.mkdir(parents=True)
    with open(tags_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "plant", "disease", "split", "original_tag", "tag", "tag_source", "tagged_at", "review_reason", "disputed"])
        for name, plant, disease, split, tag, disputed in FIXTURE_ROWS:
            if tag is not None:
                writer.writerow([name, plant, disease, split, tag, tag, "human", "2026-10-01T00:00:00Z", "",
                                  "true" if disputed else "false"])
    return tags_path


@pytest.fixture
def tiny_config(tiny_plantseg_dir: Path, tiny_tags_csv: Path) -> dict:
    return {
        "crop": "wheat",
        "disease_classes": DISEASE_CLASSES,
        "data": {
            "plantseg_dir": str(tiny_plantseg_dir),
            "processed_dir": str(tiny_tags_csv.parent),
        },
    }
