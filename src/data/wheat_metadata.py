"""Loading and filtering PlantSeg's per-image Metadata.csv.

Column names are detected automatically (case/spacing-insensitive) rather
than hardcoded, so a minor header rename in a future PlantSeg version
doesn't silently break every downstream script.
"""

import csv
from pathlib import Path

SPLIT_DIR_MAP = {"Training": "train", "Validation": "val", "Test": "test"}

# canonical field -> accepted header aliases, matched after lowercasing and
# stripping non-alphanumeric characters (so "Label file" and "label_file"
# both match "labelfile").
_COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["name", "filename", "imagename"],
    "plant": ["plant"],
    "disease": ["disease", "class"],
    "resolution": ["resolution"],
    "label_file": ["labelfile", "maskfile", "mask"],
    "mask_ratio": ["maskratio", "severityratio"],
    "url": ["url", "sourceurl"],
    "license": ["license", "licence"],
    "split": ["split"],
}


def _normalize(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def detect_columns(header: list[str]) -> dict[str, str]:
    """Map each canonical field name to the actual header string that matches it.

    Raises ValueError listing any canonical field with no match, so a schema
    change fails loudly instead of silently dropping a column.
    """
    normalized = {_normalize(h): h for h in header}
    detected = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                detected[canonical] = normalized[alias]
                break
    missing = set(_COLUMN_ALIASES) - set(detected)
    if missing:
        raise ValueError(f"Could not find columns for {sorted(missing)} in header {header}")
    return detected


def load_metadata_rows(csv_path: Path) -> list[dict]:
    """Load Metadata.csv into dicts keyed by canonical field names (name,
    plant, disease, resolution, label_file, mask_ratio, url, license, split).
    """
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = detect_columns(reader.fieldnames)
        return [{canonical: raw[header] for canonical, header in columns.items()} for raw in reader]


def filter_by_crop_and_disease(rows: list[dict], plant: str, disease_classes: list[str]) -> list[dict]:
    """Keep only rows for the given plant (case-insensitive) and an explicit
    set of disease class names (exact match, as PlantSeg's taxonomy defines them).
    """
    plant_lower = plant.lower()
    disease_set = set(disease_classes)
    return [r for r in rows if r["plant"].lower() == plant_lower and r["disease"] in disease_set]


def image_path(plantseg_dir: Path, row: dict) -> Path:
    return plantseg_dir / "images" / SPLIT_DIR_MAP[row["split"]] / row["name"]


def mask_path(plantseg_dir: Path, row: dict) -> Path:
    return plantseg_dir / "annotations" / SPLIT_DIR_MAP[row["split"]] / row["label_file"]
