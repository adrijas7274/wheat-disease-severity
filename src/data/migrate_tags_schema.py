"""One-off migration: add provenance columns (original_tag, tag, tag_source,
review_reason) to an old-schema wheat_tags.csv (name, plant, disease, split,
tag, tagged_at). Every row becomes original_tag=tag, tag_source="human",
review_reason="". Collapses to one row per image first (last-tag-wins, same
resolution load_tags() already used), since the old format allowed repeated
rows for the same image.

Usage:
    python -m src.data.migrate_tags_schema --config configs/config.yaml
"""

import argparse
import csv
from pathlib import Path

from src.data.wheat_tags import TAG_FIELDNAMES
from src.utils.config import load_config

OLD_FIELDNAMES = ["name", "plant", "disease", "split", "tag", "tagged_at"]


def migrate(tags_csv: Path) -> int:
    """Rewrites tags_csv in place to the new schema. Returns the row count."""
    with open(tags_csv, encoding="utf-8") as f:
        old_rows = list(csv.DictReader(f))

    collapsed: dict[str, dict] = {}
    for row in old_rows:
        collapsed[row["name"]] = row  # last row per name wins, matches load_tags()

    new_rows = []
    for row in collapsed.values():
        new_rows.append({
            "name": row["name"], "plant": row["plant"], "disease": row["disease"],
            "split": row["split"], "original_tag": row["tag"], "tag": row["tag"],
            "tag_source": "human", "tagged_at": row["tagged_at"], "review_reason": "",
        })
    new_rows.sort(key=lambda r: r["name"])

    with open(tags_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TAG_FIELDNAMES)
        writer.writeheader()
        writer.writerows(new_rows)

    return len(new_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"

    with open(tags_csv, encoding="utf-8") as f:
        header = next(csv.reader(f))
    if header == TAG_FIELDNAMES:
        print(f"{tags_csv} is already in the new schema - nothing to do.")
        return
    if header != OLD_FIELDNAMES:
        raise ValueError(f"Unexpected header in {tags_csv}: {header}")

    n = migrate(tags_csv)
    print(f"Migrated {tags_csv}: {n} rows, now in new schema with provenance columns.")


if __name__ == "__main__":
    main()
