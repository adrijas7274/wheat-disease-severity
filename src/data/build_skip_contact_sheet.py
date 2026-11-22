"""Build a contact sheet of every image tagged "skip", for review.

Usage:
    python -m src.data.build_skip_contact_sheet --config configs/config.yaml
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from src.data.wheat_metadata import image_path, load_metadata_rows, mask_path
from src.data.wheat_tags import load_tags
from src.utils.config import load_config

THUMB = 220
COLS = 5
PAD = 4
HEADER_H = 30


def skip_rows(config: dict) -> list[dict]:
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = load_metadata_rows(plantseg_dir / "Metadata.csv")
    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
    tags = load_tags(tags_csv)
    return [r for r in rows if tags.get(r["name"]) == "skip"]


def build_sheet(config: dict, rows: list[dict], out_path: Path) -> None:
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    n = len(rows)
    n_rows = -(-n // COLS)
    sheet = Image.new("RGB", (COLS * (THUMB + PAD) + PAD, HEADER_H + n_rows * (THUMB + PAD) + PAD), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    draw.text((PAD, 6), f"skip-tagged images (n={n})", fill=(255, 255, 255))

    for i, row in enumerate(rows):
        img = Image.open(image_path(plantseg_dir, row)).convert("RGB")
        img.thumbnail((THUMB, THUMB))
        thumb = Image.new("RGB", (THUMB, THUMB), (0, 0, 0))
        thumb.paste(img, ((THUMB - img.width) // 2, (THUMB - img.height) // 2))
        td = ImageDraw.Draw(thumb)
        td.text((2, 2), row["disease"][:22], fill=(255, 255, 0))
        r, c = divmod(i, COLS)
        sheet.paste(thumb, (PAD + c * (THUMB + PAD), HEADER_H + PAD + r * (THUMB + PAD)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    rows = skip_rows(config)
    out_path = Path("report/figures/skipped/skip_contact_sheet.png")

    if not rows:
        print("No images tagged 'skip' yet - nothing to generate.")
        return

    build_sheet(config, rows, out_path)
    print(f"Saved {len(rows)} skip-tagged images to {out_path}")


if __name__ == "__main__":
    main()
