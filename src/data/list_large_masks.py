"""List already-tagged images whose mask covers most of the image area, to
recheck tags made before the mask-quality rule in docs/tagging_guidelines.md
(skip when the outline is a box over the photo rather than tracing a leaf).

Does not change any tags - read-only.

Usage:
    python -m src.data.list_large_masks --config configs/config.yaml
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from src.data.wheat_metadata import filter_by_crop_and_disease, load_metadata_rows, mask_path
from src.data.wheat_tags import load_tags
from src.utils.config import load_config

DEFAULT_THRESHOLD = 0.90


def mask_area_fraction(mask_path_: Path) -> float:
    arr = np.array(Image.open(mask_path_).convert("L"))
    return float((arr > 0).sum()) / arr.size


def find_large_mask_tagged_images(config: dict, threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    """Already-tagged images (any tag value) whose mask covers more than
    `threshold` fraction of the image area, sorted largest first.
    """
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = load_metadata_rows(plantseg_dir / "Metadata.csv")
    rows = filter_by_crop_and_disease(rows, config["crop"], config["disease_classes"])

    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
    tags = load_tags(tags_csv)

    results = []
    for row in rows:
        tag = tags.get(row["name"])
        if tag is None:
            continue
        frac = mask_area_fraction(mask_path(plantseg_dir, row))
        if frac > threshold:
            results.append({
                "name": row["name"], "disease": row["disease"], "split": row["split"],
                "tag": tag, "mask_area_fraction": frac,
            })

    results.sort(key=lambda r: -r["mask_area_fraction"])
    return results


def format_table(results: list[dict], threshold: float) -> str:
    lines = [
        "# Large-mask recheck",
        "",
        f"Already-tagged images whose mask covers more than {threshold:.0%} of the "
        "image area - candidates to recheck against the mask-quality rule in "
        "docs/tagging_guidelines.md (added 2026-10-04). Read-only list, no tags changed.",
        "",
        f"Count: {len(results)}",
        "",
        "| name | disease | split | current tag | mask area |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['disease']} | {r['split']} | {r['tag']} | {r['mask_area_fraction']:.1%} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()

    config = load_config(args.config)
    results = find_large_mask_tagged_images(config, threshold=args.threshold)
    table_md = format_table(results, args.threshold)
    print(table_md)

    out_path = Path("report/tables/large_mask_recheck.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(table_md, encoding="utf-8")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
