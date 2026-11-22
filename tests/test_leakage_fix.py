"""Leakage fix (2026-11-14): exclusion list built from near-duplicate groups, and its use by the dataset."""
from pathlib import Path

import pytest
import yaml

from src.data import near_duplicates as nd
from src.data.wheat_severity_dataset import WheatSeverityDataset, load_split_exclusions
from src.data.wheat_tags import _latest_row_per_name, append_decision_retag
from src.utils.config import load_config


def _row(name: str, split: str, tag: str = "close_up", rated: str = "") -> dict:
    return {"name": name, "split": split, "tag": tag, "rated_set": rated, "disease": "d",
            "phase2": tag == "close_up"}


def _pairs(*idx: tuple[int, int]) -> list[tuple[int, int, int, float]]:
    return [(i, j, 0, 0.0) for i, j in idx]


def test_train_copies_of_held_out_images_are_all_removed():
    rows = [_row("tr1", "Training"), _row("tr2", "Training"), _row("te", "Test"), _row("va", "Validation"),
            _row("tr3", "Training")]
    out = nd.build_exclusions(rows, _pairs((0, 2), (1, 2), (3, 4)))
    assert [(e["name"], e["split"]) for e in out["exclude"]] == [("tr1", "Training"), ("tr2", "Training"), ("tr3", "Training")]
    assert out["test_with_train_copy"] == [{"name": "te", "train_copy": "tr1"}]


def test_train_only_group_keeps_one_close_up_copy():
    rows = [_row("a", "Training", tag="wide"), _row("b", "Training"), _row("c", "Training")]
    out = nd.build_exclusions(rows, _pairs((0, 1), (1, 2)))
    assert sorted(e["name"] for e in out["exclude"]) == ["a", "c"]
    assert all("b" in e["reason"] for e in out["exclude"])


def test_val_copy_of_a_test_image_is_removed_unless_rated():
    rows = [_row("va", "Validation"), _row("te", "Test")]
    out = nd.build_exclusions(rows, _pairs((0, 1)))
    assert out["exclude"] == [{"name": "va", "split": "Validation", "reason": "copy of te (Test)"}]
    assert out["test_with_train_copy"] == []
    rows[0]["rated_set"] = "tuning"
    with pytest.raises(ValueError):
        nd.build_exclusions(rows, _pairs((0, 1)))


def test_test_and_val_duplicates_within_their_own_split_are_left_alone():
    rows = [_row("te1", "Test"), _row("te2", "Test"), _row("va1", "Validation"), _row("va2", "Validation")]
    assert nd.build_exclusions(rows, _pairs((0, 1), (2, 3)))["exclude"] == []


def test_dataset_applies_exclusions_to_train_and_val_only(tiny_config: dict, tmp_path: Path):
    before = {s: [r["name"] for r in WheatSeverityDataset(tiny_config, split=s).rows] for s in ("train", "val", "test")}
    assert all(before.values())
    drop = [before[s][0] for s in ("train", "val", "test")]
    path = tmp_path / "split_exclude.yaml"
    path.write_text(yaml.safe_dump({"exclude": [{"name": n, "split": "x", "reason": "r"} for n in drop]}), encoding="utf-8")
    config = tiny_config | {"data": tiny_config["data"] | {"split_exclude_file": str(path)}}
    assert load_split_exclusions(config) == set(drop)
    after = {s: [r["name"] for r in WheatSeverityDataset(config, split=s).rows] for s in ("train", "val", "test")}
    assert after["train"] == before["train"][1:]
    assert after["val"] == before["val"][1:]
    assert after["test"] == before["test"]


def test_real_exclusion_list_is_consistent():
    config = load_config("configs/config.yaml")
    if not Path(config["data"]["plantseg_dir"]).exists():
        pytest.skip("needs the PlantSeg v7 data (not in the repository)")
    data = yaml.safe_load(Path(config["data"]["split_exclude_file"]).read_text(encoding="utf-8"))
    splits = [e["split"] for e in data["exclude"]]
    assert set(splits) <= {"Training", "Validation"}  # test is never changed
    assert all(e["reason"] for e in data["exclude"])
    assert len({e["name"] for e in data["exclude"]}) == len(data["exclude"])
    test_names = {r["name"] for r in WheatSeverityDataset(config, split="test").rows}
    assert {e["name"] for e in data["test_with_train_copy"]} <= test_names
    excluded = {e["name"] for e in data["exclude"]}
    assert excluded >= {e["train_copy"] for e in data["test_with_train_copy"]}


def test_decision_retag_keeps_original_tag_and_disputed(tiny_tags_csv: Path):
    before = _latest_row_per_name(tiny_tags_csv)["leaf_3.jpg"]
    append_decision_retag(tiny_tags_csv, "leaf_3.jpg", "non_photo", "collage", "2026-11-14T00:00:00Z")
    row = _latest_row_per_name(tiny_tags_csv)["leaf_3.jpg"]
    assert (row["tag"], row["tag_source"], row["review_reason"]) == ("non_photo", "human_decision", "collage")
    assert (row["original_tag"], row["disputed"], row["split"]) == (before["original_tag"], before["disputed"], before["split"])
    with pytest.raises(ValueError):
        append_decision_retag(tiny_tags_csv, "never_tagged.jpg", "non_photo", "x", "t")
