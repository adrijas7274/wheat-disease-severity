from pathlib import Path

import pytest

from src.data.wheat_tags import (
    append_review_tag, append_tag, load_original_tags, load_tags, next_untagged_index, remove_last_tag,
)


def test_load_tags_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_tags(tmp_path / "missing.csv") == {}


def test_append_tag_and_load_roundtrip(tmp_path: Path) -> None:
    csv_path = tmp_path / "wheat_tags.csv"
    append_tag(csv_path, "a.jpg", "Wheat", "wheat stripe rust", "train", "close_up", "2026-10-01T00:00:00Z")
    append_tag(csv_path, "b.jpg", "Wheat", "wheat leaf rust", "val", "wide", "2026-10-01T00:00:01Z")

    tags = load_tags(csv_path)
    assert tags == {"a.jpg": "close_up", "b.jpg": "wide"}


def test_append_tag_rejects_invalid_tag(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        append_tag(tmp_path / "wheat_tags.csv", "a.jpg", "Wheat", "d", "train", "bogus", "ts")


def test_remove_last_tag(tmp_path: Path) -> None:
    csv_path = tmp_path / "wheat_tags.csv"
    append_tag(csv_path, "a.jpg", "Wheat", "d", "train", "close_up", "ts1")
    append_tag(csv_path, "b.jpg", "Wheat", "d", "train", "wide", "ts2")

    removed = remove_last_tag(csv_path)

    assert removed == "b.jpg"
    assert load_tags(csv_path) == {"a.jpg": "close_up"}


def test_remove_last_tag_on_empty_or_missing(tmp_path: Path) -> None:
    assert remove_last_tag(tmp_path / "missing.csv") is None

    csv_path = tmp_path / "wheat_tags.csv"
    append_tag(csv_path, "a.jpg", "Wheat", "d", "train", "close_up", "ts1")
    remove_last_tag(csv_path)
    assert remove_last_tag(csv_path) is None


def test_next_untagged_index() -> None:
    rows = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    tags = {"a": "close_up"}
    assert next_untagged_index(rows, tags) == 1
    assert next_untagged_index(rows, tags, start=2) == 2
    assert next_untagged_index(rows, {"a": "x", "b": "x", "c": "x"}) is None


def test_append_tag_sets_original_tag_on_first_write(tmp_path: Path) -> None:
    csv_path = tmp_path / "wheat_tags.csv"
    append_tag(csv_path, "a.jpg", "Wheat", "d", "train", "close_up", "ts1")

    assert load_tags(csv_path) == {"a.jpg": "close_up"}
    assert load_original_tags(csv_path) == {"a.jpg": "close_up"}


def test_append_tag_preserves_original_tag_on_retag(tmp_path: Path) -> None:
    csv_path = tmp_path / "wheat_tags.csv"
    append_tag(csv_path, "a.jpg", "Wheat", "d", "train", "close_up", "ts1")
    append_tag(csv_path, "a.jpg", "Wheat", "d", "train", "wide", "ts2")  # human re-tags via the live tool

    assert load_tags(csv_path) == {"a.jpg": "wide"}
    assert load_original_tags(csv_path) == {"a.jpg": "close_up"}  # untouched


def test_append_review_tag_changes_tag_not_original(tmp_path: Path) -> None:
    csv_path = tmp_path / "wheat_tags.csv"
    append_tag(csv_path, "a.jpg", "Wheat", "d", "train", "close_up", "ts1")

    append_review_tag(csv_path, "a.jpg", "Wheat", "d", "train", "skip", "mask is a box", "ts2")

    assert load_tags(csv_path) == {"a.jpg": "skip"}
    assert load_original_tags(csv_path) == {"a.jpg": "close_up"}

    with open(csv_path, encoding="utf-8") as f:
        import csv as _csv
        rows = list(_csv.DictReader(f))
    last = rows[-1]
    assert last["tag_source"] == "claude_review"
    assert last["review_reason"] == "mask is a box"


def test_append_review_tag_rejects_never_tagged_image(tmp_path: Path) -> None:
    csv_path = tmp_path / "wheat_tags.csv"
    with pytest.raises(ValueError, match="never been tagged"):
        append_review_tag(csv_path, "a.jpg", "Wheat", "d", "train", "skip", "reason", "ts")


def test_append_review_tag_rejects_invalid_tag(tmp_path: Path) -> None:
    csv_path = tmp_path / "wheat_tags.csv"
    append_tag(csv_path, "a.jpg", "Wheat", "d", "train", "close_up", "ts1")
    with pytest.raises(ValueError):
        append_review_tag(csv_path, "a.jpg", "Wheat", "d", "train", "bogus", "reason", "ts2")
