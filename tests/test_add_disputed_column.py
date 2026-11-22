import csv
from pathlib import Path

from src.data.add_disputed_column import add_column, disputed_names
from src.data.wheat_tags import TAG_FIELDNAMES, load_disputed, load_original_tags, load_tags


def _write_old_schema(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f for f in TAG_FIELDNAMES if f != "disputed"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        writer.writerows(rows)


def test_disputed_names_from_agreement_report(tmp_path: Path) -> None:
    report = tmp_path / "inter_rater_agreement.md"
    report.write_text(
        "# Inter-rater agreement\n\n"
        "| name | disease | human (original) | claude | match |\n"
        "|---|---|---|---|---|\n"
        "| a.jpg | wheat stripe rust | close_up | close_up | yes |\n"
        "| b.jpg | wheat leaf rust | wide | close_up | **no** |\n",
        encoding="utf-8",
    )
    assert disputed_names(report) == {"b.jpg"}


def test_add_column_marks_disputed_and_preserves_other_fields(tmp_path: Path) -> None:
    tags_csv = tmp_path / "wheat_tags.csv"
    _write_old_schema(tags_csv, [
        ("a.jpg", "Wheat", "d1", "Training", "close_up", "close_up", "human", "t1", ""),
        ("b.jpg", "Wheat", "d2", "Training", "wide", "wide", "human", "t2", ""),
    ])

    n_marked = add_column(tags_csv, disputed={"b.jpg"})

    assert n_marked == 1
    assert load_disputed(tags_csv) == {"a.jpg": False, "b.jpg": True}
    # original_tag and tag must be completely untouched
    assert load_tags(tags_csv) == {"a.jpg": "close_up", "b.jpg": "wide"}
    assert load_original_tags(tags_csv) == {"a.jpg": "close_up", "b.jpg": "wide"}


def test_add_column_marks_all_historical_rows_for_a_disputed_name(tmp_path: Path) -> None:
    tags_csv = tmp_path / "wheat_tags.csv"
    _write_old_schema(tags_csv, [
        ("a.jpg", "Wheat", "d1", "Training", "close_up", "close_up", "human", "t1", ""),
        ("a.jpg", "Wheat", "d1", "Training", "close_up", "skip", "claude_review", "t2", "bad mask"),
    ])

    add_column(tags_csv, disputed={"a.jpg"})

    with open(tags_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert all(r["disputed"] == "true" for r in rows)  # both historical rows marked, not just the latest
