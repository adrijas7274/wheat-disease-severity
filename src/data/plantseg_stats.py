"""Print per-candidate-crop dataset statistics from PlantSeg's official splits.

Reads the three official COCO-format annotation files (train/val/test) that
define PlantSeg's split and disease label per image - the disease label is
recovered from each image's file_name (see plantseg_taxonomy.class_name_from_file_name),
not from category_id, since PlantSeg's per-image file_name already encodes the
exact class unambiguously and needs no assumption about category_id ordering.

Usage:
    python -m src.data.plantseg_stats --config configs/config.yaml
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from src.data.plantseg_taxonomy import CROP_ALIASES, class_name_from_file_name, plant_of
from src.utils.config import load_config

# Relative to the PlantSeg root (config data.plantseg_dir). Confirmed present
# in the PlantSeg GitHub repo (coco_annotations/); assumed to ship inside the
# Zenodo zip too - adjust here if the extracted layout differs.
SPLIT_ANNOTATION_FILES = {
    "train": "coco_annotations/annotation_train.json",
    "val": "coco_annotations/annotation_val.json",
    "test": "coco_annotations/annotation_test.json",
}


def load_split_classes(plantseg_dir: Path) -> dict[str, list[str]]:
    """Return {split: [class_name_per_image]} from the official COCO annotation files."""
    result = {}
    for split, rel_path in SPLIT_ANNOTATION_FILES.items():
        path = plantseg_dir / rel_path
        if not path.exists():
            raise FileNotFoundError(
                f"Expected official split file not found: {path}. "
                "Run `python -m src.data.download_plantseg` first."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        classes = []
        for image in data["images"]:
            class_name = class_name_from_file_name(image["file_name"])
            if class_name is None:
                raise ValueError(f"Could not parse class from file_name: {image['file_name']!r}")
            classes.append(class_name)
        result[split] = classes
    return result


def compute_crop_stats(split_classes: dict[str, list[str]]) -> list[dict]:
    """Per candidate crop: number of disease classes, total images, the
    bottleneck class's image count (min_images_per_disease), and per-split counts.
    """
    all_classes = [c for classes in split_classes.values() for c in classes]
    overall_counts = Counter(all_classes)
    per_split_counts = {split: Counter(classes) for split, classes in split_classes.items()}

    rows = []
    for crop, plant_names in CROP_ALIASES.items():
        disease_classes = [c for c in overall_counts if plant_of(c) in plant_names]
        total_images = sum(overall_counts[c] for c in disease_classes)
        min_images = min((overall_counts[c] for c in disease_classes), default=0)
        row = {
            "crop": crop,
            "num_diseases": len(disease_classes),
            "total_images": total_images,
            "min_images_per_disease": min_images,
        }
        for split in split_classes:
            row[f"{split}_count"] = sum(per_split_counts[split].get(c, 0) for c in disease_classes)
        rows.append(row)
    return rows


def format_table(rows: list[dict]) -> str:
    headers = ["crop", "num_diseases", "total_images", "min_images_per_disease", "train_count", "val_count", "test_count"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    plantseg_dir = Path(config["data"]["plantseg_dir"])

    split_classes = load_split_classes(plantseg_dir)
    rows = compute_crop_stats(split_classes)
    print(format_table(rows))


if __name__ == "__main__":
    main()
