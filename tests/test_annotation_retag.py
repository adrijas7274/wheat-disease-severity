from pathlib import Path

import pytest

from src.data.wheat_tags import _latest_row_per_name, append_annotation_retag, load_tags
from src.severity import annotation_core as core
from src.severity.annotation_sets import frozen_queues


def _config(tiny_config: dict) -> dict:
    return tiny_config | {"seed": 42, "annotation": {"sets": {
        "pilot": {"split": "Training", "per_disease": 1},
        "tuning": {"split": "Validation", "per_disease": 1},
        "gold": {"split": "Test", "per_disease": 1},
    }}}


def test_annotation_retag_keeps_original_tag_and_disputed(tiny_tags_csv: Path):
    append_annotation_retag(tiny_tags_csv, "leaf_3.jpg", "Wheat", "wheat leaf rust", "Test",
                            "non_photo", "why", "2026-11-01T00:00:00Z")
    row = _latest_row_per_name(tiny_tags_csv)["leaf_3.jpg"]
    assert (row["tag"], row["original_tag"], row["tag_source"], row["disputed"]) == (
        "non_photo", "close_up", "human_annotation", "true")
    with pytest.raises(ValueError):
        append_annotation_retag(tiny_tags_csv, "stripe_5.jpg", "Wheat", "wheat stripe rust", "Training",
                                "non_photo", "never tagged", "t")


def test_sync_not_photo_retags_is_idempotent_and_reason_specific(tiny_tags_csv: Path, tmp_path: Path):
    log = tmp_path / "log.csv"
    core.append_log(log, {"name": "stripe_1.jpg", "split": "Training", "disease": "wheat stripe rust",
                          "set": "pilot", "status": "skipped", "skip_reason": core.NOT_A_PHOTO})
    core.append_log(log, {"name": "leaf_2.jpg", "split": "Test", "disease": "wheat leaf rust",
                          "set": "gold", "status": "skipped", "skip_reason": "main leaf too blurred"})
    assert core.sync_not_photo_retags(log, tiny_tags_csv) == ["stripe_1.jpg"]
    assert core.sync_not_photo_retags(log, tiny_tags_csv) == []
    tags = load_tags(tiny_tags_csv)
    assert tags["stripe_1.jpg"] == "non_photo" and tags["leaf_2.jpg"] == "close_up"
    assert _latest_row_per_name(tiny_tags_csv)["stripe_1.jpg"]["plant"] == "Wheat"


def test_frozen_queue_survives_retag(tiny_config: dict, tiny_tags_csv: Path, tmp_path: Path):
    config = _config(tiny_config)
    first = frozen_queues(config, "pilot", tmp_path / "queues")
    names = [r["name"] for r in first["wheat stripe rust"]]
    assert names == ["stripe_1.jpg"]  # stripe_6 is disputed: excluded from every annotation set
    append_annotation_retag(tiny_tags_csv, names[0], "Wheat", "wheat stripe rust", "Training",
                            "non_photo", "x", "t")
    again = frozen_queues(config, "pilot", tmp_path / "queues")
    assert [r["name"] for r in again["wheat stripe rust"]] == names  # same order, re-tagged image kept
    assert again == first
