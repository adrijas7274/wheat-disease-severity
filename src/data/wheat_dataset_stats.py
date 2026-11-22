"""Print wheat dataset statistics (per disease / split / tag) and save sample
overlays from the actual Dataset class to report/figures/.

Usage:
    python -m src.data.wheat_dataset_stats --config configs/config.yaml
"""

import argparse
import random
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

from src.data.wheat_metadata import filter_by_crop_and_disease, load_metadata_rows, SPLIT_DIR_MAP
from src.data.wheat_severity_dataset import WheatSeverityDataset
from src.data.wheat_tags import load_disputed, load_tags
from src.utils.config import load_config

ALL_TAG_VALUES = ["close_up", "wide", "non_photo", "skip", "untagged"]


def compute_counts(config: dict) -> dict[tuple[str, str, str], int]:
    """(disease, split, tag) -> count, over every image in config's crop+disease_classes."""
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = load_metadata_rows(plantseg_dir / "Metadata.csv")
    rows = filter_by_crop_and_disease(rows, config["crop"], config["disease_classes"])

    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
    tags = load_tags(tags_csv)

    counts = Counter()
    for r in rows:
        split = SPLIT_DIR_MAP[r["split"]]
        tag = tags.get(r["name"], "untagged")
        counts[(r["disease"], split, tag)] += 1
    return counts


def compute_disputed_counts(config: dict) -> dict[tuple[str, str], int]:
    """(disease, split) -> count of tagged images flagged disputed (blind
    inter-rater disagreement with original_tag). See
    report/tables/inter_rater_agreement.md and experiments/LOG.md.
    """
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = load_metadata_rows(plantseg_dir / "Metadata.csv")
    rows = filter_by_crop_and_disease(rows, config["crop"], config["disease_classes"])

    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
    disputed = load_disputed(tags_csv)

    counts = Counter()
    for r in rows:
        if disputed.get(r["name"], False):
            counts[(r["disease"], SPLIT_DIR_MAP[r["split"]])] += 1
    return counts


def print_table(
    config: dict,
    counts: dict[tuple[str, str, str], int],
    disputed_counts: dict[tuple[str, str], int],
) -> None:
    diseases = config["disease_classes"]
    splits = ["train", "val", "test"]
    columns = ALL_TAG_VALUES + ["disputed"]

    header = f"{'disease':<45}{'split':<8}" + "".join(f"{t:<12}" for t in columns) + "total"
    print(header)
    print("-" * len(header))
    grand_total = Counter()
    grand_disputed = 0
    for disease in diseases:
        for split in splits:
            row_counts = {t: counts.get((disease, split, t), 0) for t in ALL_TAG_VALUES}
            disputed_n = disputed_counts.get((disease, split), 0)
            total = sum(row_counts.values())
            if total == 0:
                continue
            line = (
                f"{disease:<45}{split:<8}"
                + "".join(f"{row_counts[t]:<12}" for t in ALL_TAG_VALUES)
                + f"{disputed_n:<12}" + str(total)
            )
            print(line)
            for t in ALL_TAG_VALUES:
                grand_total[t] += row_counts[t]
            grand_disputed += disputed_n

    print("-" * len(header))
    total_line = (
        f"{'TOTAL':<45}{'':<8}"
        + "".join(f"{grand_total[t]:<12}" for t in ALL_TAG_VALUES)
        + f"{grand_disputed:<12}"
    )
    print(total_line + str(sum(grand_total.values())))


def save_sample_overlays(config: dict, out_path: Path, n: int = 16, cols: int = 4) -> bool:
    """Save a grid of sample images+masks pulled through the real Dataset class
    (close_up/train). Returns False (and prints a message instead) if no
    close_up-tagged images exist yet.
    """
    dataset = WheatSeverityDataset(config, split="train", subset="close_up")
    if len(dataset) == 0:
        print(f"\nNo close_up-tagged train images yet - skipping sample overlays at {out_path}. "
              f"Run `python -m src.data.tag_wheat_images` first.")
        return False

    random.seed(42)
    indices = random.sample(range(len(dataset)), min(n, len(dataset)))

    thumb = 180
    rows_n = -(-len(indices) // cols)
    sheet = Image.new("RGB", (cols * thumb, rows_n * thumb), (30, 30, 30))
    for i, idx in enumerate(indices):
        sample = dataset[idx]
        img = Image.fromarray(sample["image"]).resize((thumb, thumb))
        mask = Image.fromarray(sample["mask"]).resize((thumb, thumb), Image.NEAREST)
        mask_binary = mask.point(lambda p: 255 if p > 0 else 0)
        red = Image.new("RGB", (thumb, thumb), (255, 0, 0))
        blended = Image.composite(Image.blend(img, red, alpha=0.45), img, mask_binary)
        draw = ImageDraw.Draw(blended)
        draw.text((2, 2), sample["disease"][:20], fill=(255, 255, 0))
        r, c = divmod(i, cols)
        sheet.paste(blended, (c * thumb, r * thumb))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    print(f"\nSaved {len(indices)} sample overlays to {out_path}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    counts = compute_counts(config)
    disputed_counts = compute_disputed_counts(config)
    print_table(config, counts, disputed_counts)
    save_sample_overlays(config, Path("report/figures/wheat_sample_overlays.png"))


if __name__ == "__main__":
    main()
