import numpy as np
import pytest

from src.data.wheat_severity_dataset import WheatSeverityDataset


def test_close_up_train_excludes_wide_non_photo_skip_untagged(tiny_config: dict) -> None:
    ds = WheatSeverityDataset(tiny_config, split="train", subset="close_up")
    ids = {ds[i]["image_id"] for i in range(len(ds))}
    # stripe_6.jpg is disputed but train, so it's included (see test_disputed_images_excluded_from_test_only)
    assert ids == {"stripe_1.jpg", "stripe_6.jpg"}


def test_wide_subset(tiny_config: dict) -> None:
    ds = WheatSeverityDataset(tiny_config, split="train", subset="wide")
    ids = {ds[i]["image_id"] for i in range(len(ds))}
    assert ids == {"stripe_2.jpg"}


def test_excludes_other_disease_and_other_plant(tiny_config: dict) -> None:
    ds = WheatSeverityDataset(tiny_config, split="train", subset="close_up")
    ids = {ds[i]["image_id"] for i in range(len(ds))}
    assert "scab_1.jpg" not in ids  # wheat head scab - not in disease_classes
    assert "tomato_1.jpg" not in ids  # wrong plant


def test_splits_are_not_reshuffled(tiny_config: dict) -> None:
    val_ds = WheatSeverityDataset(tiny_config, split="val", subset="close_up")
    test_ds = WheatSeverityDataset(tiny_config, split="test", subset="close_up")
    assert {val_ds[i]["image_id"] for i in range(len(val_ds))} == {"leaf_1.jpg"}
    # leaf_3.jpg exists in the test split (see test_disputed_images_excluded_from_test_only)
    # but is disputed, so it's excluded here - only leaf_2.jpg remains.
    assert {test_ds[i]["image_id"] for i in range(len(test_ds))} == {"leaf_2.jpg"}


def test_disputed_images_excluded_from_test_only(tiny_config: dict) -> None:
    # leaf_3.jpg is a disputed close_up image in the Test split (conftest.py).
    test_ds = WheatSeverityDataset(tiny_config, split="test", subset="close_up")
    test_ids = {test_ds[i]["image_id"] for i in range(len(test_ds))}
    assert "leaf_3.jpg" not in test_ids
    assert "leaf_2.jpg" in test_ids  # non-disputed test image still included

    # stripe_6.jpg is disputed but in the Training split - still included there.
    train_ds = WheatSeverityDataset(tiny_config, split="train", subset="close_up")
    train_ids = {train_ds[i]["image_id"] for i in range(len(train_ds))}
    assert "stripe_6.jpg" in train_ids


def test_getitem_shape_and_keys(tiny_config: dict) -> None:
    ds = WheatSeverityDataset(tiny_config, split="train", subset="close_up")
    sample = ds[0]
    assert set(sample.keys()) == {"image", "mask", "disease", "image_id"}
    assert isinstance(sample["image"], np.ndarray)
    assert sample["image"].shape == (10, 10, 3)
    assert sample["mask"].shape == (10, 10)
    assert sample["disease"] == "wheat stripe rust"


def test_invalid_split_raises(tiny_config: dict) -> None:
    with pytest.raises(ValueError):
        WheatSeverityDataset(tiny_config, split="bogus", subset="close_up")


def test_invalid_subset_raises(tiny_config: dict) -> None:
    with pytest.raises(ValueError):
        WheatSeverityDataset(tiny_config, split="train", subset="bogus")
