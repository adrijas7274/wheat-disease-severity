import csv
from pathlib import Path

from src.data.migrate_tags_schema import migrate
from src.data.wheat_tags import TAG_FIELDNAMES, load_original_tags, load_tags


def _write_old_schema(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "plant", "disease", "split", "tag", "tagged_at"])
        writer.writerows(rows)


def test_migrate_simple_one_row_per_name(tmp_path: Path) -> None:
    tags_csv = tmp_path / "tags.csv"
    _write_old_schema(tags_csv, [
        ("a.jpg", "Wheat", "d1", "Training", "close_up", "t1"),
        ("b.jpg", "Wheat", "d2", "Training", "wide", "t2"),
    ])

    n = migrate(tags_csv)

    assert n == 2
    with open(tags_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == TAG_FIELDNAMES
        rows = list(reader)
    by_name = {r["name"]: r for r in rows}
    assert by_name["a.jpg"]["original_tag"] == "close_up"
    assert by_name["a.jpg"]["tag"] == "close_up"
    assert by_name["a.jpg"]["tag_source"] == "human"
    assert by_name["a.jpg"]["review_reason"] == ""


def test_migrate_collapses_duplicate_names_last_wins(tmp_path: Path) -> None:
    tags_csv = tmp_path / "tags.csv"
    _write_old_schema(tags_csv, [
        ("a.jpg", "Wheat", "d1", "Training", "close_up", "t1"),
        ("a.jpg", "Wheat", "d1", "Training", "wide", "t2"),  # re-tagged later
    ])

    n = migrate(tags_csv)

    assert n == 1
    assert load_tags(tags_csv) == {"a.jpg": "wide"}
    assert load_original_tags(tags_csv) == {"a.jpg": "wide"}  # old schema had no original_tag concept


def test_migrate_preserves_load_tags_contract(tmp_path: Path) -> None:
    tags_csv = tmp_path / "tags.csv"
    _write_old_schema(tags_csv, [
        ("a.jpg", "Wheat", "d1", "Training", "close_up", "t1"),
        ("b.jpg", "Wheat", "d2", "Validation", "skip", "t2"),
    ])

    migrate(tags_csv)

    assert load_tags(tags_csv) == {"a.jpg": "close_up", "b.jpg": "skip"}
