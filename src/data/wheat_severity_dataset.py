"""PyTorch Dataset for wheat leaf-disease severity.

Wraps PlantSeg v7's images/masks, filtered to the crop and disease_classes
in configs/config.yaml, joined against the manual tags from
data/processed/wheat_tags.csv (see src/data/tag_wheat_images.py).

Only tagged images are usable:
- "close_up" is the main dataset for severity training/eval.
- "wide" (whole plant/field shots) is kept as a separate subset, not mixed
  into training - it's for evaluating the Phase 6 quality gate later.
- "non_photo" (diagrams/lab plates/banners) and "skip" are excluded entirely.
- Untagged images are excluded too - tag them first.

Disputed images (data/processed/wheat_tags.csv "disputed" column - where a
blind inter-rater check disagreed with the human's original_tag; see
report/tables/inter_rater_agreement.md) are handled specially:
- split="test": excluded entirely, from every subset. This is every
  evaluation set built on this class - the severity test set and the
  future Phase 6 quality-gate test set both draw from split="test" - so we
  never score the model against a label we aren't confident in.
- split="train" (and "val"): included like any other image, subject to the
  normal tag/subset filter - a disputed *framing* label (close_up vs wide
  vs non_photo) doesn't make the lesion *mask* unusable. The only thing
  that excludes an image from training is an unusable mask, i.e. tag=skip
  (already enforced structurally: skip-tagged images never match
  subset="close_up"/"wide" in the first place).

Duplicate photos (leakage fix, 2026-11-14): images listed in
`data.split_exclude_file` are removed from train and val. They are copies of
a val or test image, or extra copies within train. Test is never filtered by
this list. See src/data/near_duplicates.py and experiments/LOG.md.

The official PlantSeg v7 train/val/test split is never reshuffled; filtering
only removes images from within whichever split they already belong to.
"""

from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from torch.utils.data import Dataset

from src.data.wheat_metadata import (
    SPLIT_DIR_MAP, filter_by_crop_and_disease, image_path, load_metadata_rows, mask_path,
)
from src.data.wheat_tags import load_disputed, load_tags

Subset = Literal["close_up", "wide"]
VALID_SPLITS = ("train", "val", "test")
VALID_SUBSETS = ("close_up", "wide")


def load_split_exclusions(config: dict) -> set[str]:
    """Names in `data.split_exclude_file` (empty if the key or the file is absent)."""
    path = config["data"].get("split_exclude_file")
    if not path or not Path(path).exists():
        return set()
    import yaml

    return {e["name"] for e in yaml.safe_load(Path(path).read_text(encoding="utf-8"))["exclude"]}


class WheatSeverityDataset(Dataset):
    def __init__(self, config: dict, split: str, subset: Subset = "close_up"):
        if split not in VALID_SPLITS:
            raise ValueError(f"split must be one of {VALID_SPLITS}, got {split!r}")
        if subset not in VALID_SUBSETS:
            raise ValueError(f"subset must be one of {VALID_SUBSETS}, got {subset!r}")

        self.plantseg_dir = Path(config["data"]["plantseg_dir"])
        self.split = split
        self.subset = subset

        rows = load_metadata_rows(self.plantseg_dir / "Metadata.csv")
        rows = filter_by_crop_and_disease(rows, config["crop"], config["disease_classes"])
        rows = [r for r in rows if SPLIT_DIR_MAP[r["split"]] == split]

        tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
        tags = load_tags(tags_csv)
        self.rows = [r for r in rows if tags.get(r["name"]) == subset]

        if split == "test":
            disputed = load_disputed(tags_csv)
            self.rows = [r for r in self.rows if not disputed.get(r["name"], False)]
        else:
            excluded = load_split_exclusions(config)
            self.rows = [r for r in self.rows if r["name"] not in excluded]

        self.rows.sort(key=lambda r: r["name"])

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int) -> dict:
        row = self.rows[idx]
        image = Image.open(image_path(self.plantseg_dir, row)).convert("RGB")
        mask = Image.open(mask_path(self.plantseg_dir, row)).convert("L")
        return {
            "image": np.array(image),
            "mask": np.array(mask),
            "disease": row["disease"],
            "image_id": row["name"],
        }
