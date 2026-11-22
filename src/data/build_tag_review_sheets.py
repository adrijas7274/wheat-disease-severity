"""Build contact sheets (with each image's current tag printed on it, cyan
lesion outline shown) for a few groups of already-tagged images worth a
second look: the large-mask recheck list, and every image in a given
disease class. Read-only - never writes to data/processed/wheat_tags.csv.

Usage:
    python -m src.data.build_tag_review_sheets --config configs/config.yaml
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from src.data.tag_wheat_images import (
    image_path, large_mask_review_rows, mask_path, overlay_outline, tagged_rows_for_disease,
)
from src.utils.config import load_config

THUMB = 160
COLS = 8
PAD = 4
HEADER_H = 32


def build_sheet(config: dict, rows: list[dict], title: str, out_path: Path) -> None:
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    n = len(rows)
    n_rows = -(-n // COLS)
    sheet = Image.new("RGB", (COLS * (THUMB + PAD) + PAD, HEADER_H + n_rows * (THUMB + PAD) + PAD), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    draw.text((PAD, 8), f"{title} (n={n})", fill=(255, 255, 255))

    for i, row in enumerate(rows):
        _, outlined = overlay_outline(image_path(plantseg_dir, row), mask_path(plantseg_dir, row), max_dim=THUMB)
        thumb = Image.new("RGB", (THUMB, THUMB), (0, 0, 0))
        thumb.paste(outlined, ((THUMB - outlined.width) // 2, (THUMB - outlined.height) // 2))
        td = ImageDraw.Draw(thumb)
        td.rectangle((0, 0, THUMB, 16), fill=(0, 0, 0))
        td.text((2, 2), f"tag: {row['tag']}", fill=(255, 255, 0))
        r, c = divmod(i, COLS)
        sheet.paste(thumb, (PAD + c * (THUMB + PAD), HEADER_H + PAD + r * (THUMB + PAD)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    print(f"Saved {n} images to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    out_dir = Path("report/figures/tag_review")

    build_sheet(
        config, large_mask_review_rows(config, "wheat powdery mildew"),
        "Large-mask (>90%) wheat powdery mildew", out_dir / "large_mask_powdery_mildew.png",
    )
    build_sheet(
        config, tagged_rows_for_disease(config, "wheat stripe rust"),
        "All wheat stripe rust", out_dir / "wheat_stripe_rust.png",
    )
    build_sheet(
        config, tagged_rows_for_disease(config, "wheat bacterial leaf streak (black chaff)"),
        "All wheat bacterial leaf streak", out_dir / "wheat_bacterial_leaf_streak.png",
    )


if __name__ == "__main__":
    main()
