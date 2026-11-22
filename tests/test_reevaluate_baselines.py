import csv
from pathlib import Path

from src.data.wheat_tags import load_tags
from src.reevaluate_baselines import write_tags_without_test_retags

FIELDS = ["name", "plant", "disease", "split", "original_tag", "tag", "tag_source", "tagged_at", "review_reason", "disputed"]


def _row(name: str, split: str, tag: str, source: str) -> dict:
    return {"name": name, "plant": "Wheat", "disease": "d", "split": split, "original_tag": "close_up", "tag": tag,
            "tag_source": source, "tagged_at": "t", "review_reason": "", "disputed": "false"}


def test_only_test_retags_are_undone(tmp_path: Path):
    tags = tmp_path / "tags.csv"
    with open(tags, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows([
            _row("test.jpg", "Test", "close_up", "human"),
            _row("test.jpg", "Test", "non_photo", "human_annotation"),
            _row("val.jpg", "Validation", "close_up", "human"),
            _row("val.jpg", "Validation", "non_photo", "human_annotation"),
            _row("plate.jpg", "Test", "non_photo", "human"),  # tagged by hand, not re-tagged while rating
        ])
    out = tmp_path / "pre" / "tags.csv"
    assert write_tags_without_test_retags(tags, out) == ["test.jpg"]
    restored = load_tags(out)
    assert restored["test.jpg"] == "close_up"
    assert restored["val.jpg"] == "non_photo"
    assert restored["plate.jpg"] == "non_photo"
    assert load_tags(tags)["test.jpg"] == "non_photo"  # input left as it is
