"""One-off: add the 'disputed' column to an existing wheat_tags.csv,
backfilled from report/tables/inter_rater_agreement.md. True on every row
(human and any later claude_review row) for an image where the blind
inter-rater check disagreed with original_tag; false everywhere else,
including images never included in that check.

Never touches original_tag or tag.

Usage:
    python -m src.data.add_disputed_column --config configs/config.yaml
"""

import argparse
import csv
from pathlib import Path

from src.data.wheat_self_check import parse_agreement_report
from src.data.wheat_tags import TAG_FIELDNAMES
from src.utils.config import load_config

OLD_FIELDNAMES_NO_DISPUTED = [f for f in TAG_FIELDNAMES if f != "disputed"]


def disputed_names(agreement_report: Path) -> set[str]:
    results = parse_agreement_report(agreement_report)
    return {name for name, _disease, orig, new in results if orig != new}


def add_column(tags_csv: Path, disputed: set[str]) -> int:
    with open(tags_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        row["disputed"] = "true" if row["name"] in disputed else "false"

    with open(tags_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TAG_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return sum(1 for r in rows if r["disputed"] == "true")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--agreement-report", default="report/tables/inter_rater_agreement.md")
    args = parser.parse_args()

    config = load_config(args.config)
    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"

    with open(tags_csv, encoding="utf-8") as f:
        header = next(csv.reader(f))
    if header == TAG_FIELDNAMES:
        print(f"{tags_csv} already has a disputed column - nothing to do.")
        return
    if header != OLD_FIELDNAMES_NO_DISPUTED:
        raise ValueError(f"Unexpected header in {tags_csv}: {header}")

    disputed = disputed_names(Path(args.agreement_report))
    n_rows_marked = add_column(tags_csv, disputed)
    print(f"Added disputed column to {tags_csv}: {len(disputed)} disputed images, "
          f"{n_rows_marked} rows marked true (incl. any claude_review rows for the same image).")


if __name__ == "__main__":
    main()
