"""Quick, approximate check of how much PlantSeg mask area is still healthy
green tissue (simple HSV thresholding) - not a validated severity
correction, just a directional estimate of how much masks overestimate
lesion extent. See experiments/LOG.md 2026-10-03.

Usage:
    python -m src.severity.mask_coarseness_check --config configs/config.yaml
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from src.data.wheat_metadata import image_path, load_metadata_rows, mask_path
from src.data.wheat_tags import load_tags
from src.utils.config import load_config

# Generous "healthy green" range in OpenCV HSV (H:0-179, S/V:0-255) - a
# standard ballpark used in plant-image segmentation write-ups, not tuned or
# validated against ground truth. A directional estimate only.
GREEN_LOWER = np.array([25, 40, 40])
GREEN_UPPER = np.array([90, 255, 255])


def healthy_fraction_in_mask(img_path: Path, mask_path_: Path, max_dim: int = 512) -> float | None:
    """Fraction of masked (lesion-labelled) pixels that look healthy-green.
    None if the mask is empty or either file fails to load.
    """
    img = cv2.imread(str(img_path))
    mask = cv2.imread(str(mask_path_), cv2.IMREAD_GRAYSCALE)
    if img is None or mask is None:
        return None

    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    mask_binary = mask > 0
    n_mask = int(mask_binary.sum())
    if n_mask == 0:
        return None

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, GREEN_LOWER, GREEN_UPPER) > 0
    healthy_in_mask = int((green & mask_binary).sum())
    return healthy_in_mask / n_mask


def compute_table(config: dict) -> list[dict]:
    """Per disease class (config['disease_classes']): mean/median fraction of
    close_up-tagged images' masked area that is healthy-green.
    """
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = load_metadata_rows(plantseg_dir / "Metadata.csv")
    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
    tags = load_tags(tags_csv)

    results = []
    for disease in config["disease_classes"]:
        close_up_rows = [r for r in rows if r["disease"] == disease and tags.get(r["name"]) == "close_up"]
        fractions = []
        for row in close_up_rows:
            frac = healthy_fraction_in_mask(image_path(plantseg_dir, row), mask_path(plantseg_dir, row))
            if frac is not None:
                fractions.append(frac)

        if fractions:
            mean_frac = sum(fractions) / len(fractions)
            sorted_f = sorted(fractions)
            median_frac = sorted_f[len(sorted_f) // 2]
        else:
            mean_frac = median_frac = None

        results.append({
            "disease": disease,
            "n_close_up": len(close_up_rows),
            "n_analyzed": len(fractions),
            "mean_healthy_frac": mean_frac,
            "median_healthy_frac": median_frac,
        })
    return results


def format_table(results: list[dict]) -> str:
    lines = [
        "# Mask coarseness check: healthy-green fraction inside PlantSeg lesion masks",
        "",
        "Approximate, unvalidated HSV heuristic (see experiments/LOG.md 2026-10-03) on "
        "close_up-tagged images only. Higher fraction = more of the masked region is "
        "still healthy-looking tissue, i.e. the more the raw mask likely overestimates "
        "true lesion severity.",
        "",
        "| disease | n close_up | n analyzed | mean healthy frac in mask | median |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        mean_s = f"{r['mean_healthy_frac']:.1%}" if r["mean_healthy_frac"] is not None else "n/a"
        median_s = f"{r['median_healthy_frac']:.1%}" if r["median_healthy_frac"] is not None else "n/a"
        lines.append(f"| {r['disease']} | {r['n_close_up']} | {r['n_analyzed']} | {mean_s} | {median_s} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    results = compute_table(config)
    table_md = format_table(results)
    print(table_md)

    out_path = Path("report/tables/mask_coarseness.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(table_md, encoding="utf-8")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
