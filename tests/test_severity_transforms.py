import torch

from src.data.severity_transforms import TransformedSeverityDataset
from src.data.wheat_severity_dataset import WheatSeverityDataset


def test_transformed_dataset_shapes_and_dtypes(tiny_config: dict) -> None:
    base = WheatSeverityDataset(tiny_config, split="train", subset="close_up")
    ds = TransformedSeverityDataset(base, image_size=64, train=True)

    sample = ds[0]

    assert sample["image"].shape == (3, 64, 64)
    assert sample["image"].dtype == torch.float32
    assert sample["mask"].shape == (64, 64)
    assert sample["mask"].dtype == torch.long
    assert set(torch.unique(sample["mask"]).tolist()) <= {0, 1}


def test_transformed_dataset_eval_mode_deterministic(tiny_config: dict) -> None:
    base = WheatSeverityDataset(tiny_config, split="train", subset="close_up")
    ds = TransformedSeverityDataset(base, image_size=32, train=False)

    sample1 = ds[0]
    sample2 = ds[0]

    assert torch.equal(sample1["image"], sample2["image"])
    assert torch.equal(sample1["mask"], sample2["mask"])


def test_transformed_dataset_length_matches_base(tiny_config: dict) -> None:
    base = WheatSeverityDataset(tiny_config, split="train", subset="close_up")
    ds = TransformedSeverityDataset(base, image_size=32, train=True)
    assert len(ds) == len(base)


def test_corruption_augmented_dataset_changes_only_the_photo():
    import numpy as np

    from src.data.severity_transforms import CorruptionAugmentedDataset

    rng = np.random.default_rng(0)
    photo, mask = rng.integers(0, 255, (40, 60, 3), dtype=np.uint8), np.ones((40, 60), np.uint8)
    base = [{"image": photo, "mask": mask, "disease": "d", "image_id": "a.jpg"}]
    always, never = CorruptionAugmentedDataset(base, 1.0, 42), CorruptionAugmentedDataset(base, 0.0, 42)
    out = always[0]
    assert out["image"].shape == photo.shape and not np.array_equal(out["image"], photo)
    assert out["mask"] is mask and np.array_equal(base[0]["image"], photo)  # the base sample is not modified
    assert np.array_equal(never[0]["image"], photo)
    again = CorruptionAugmentedDataset(base, 1.0, 42)[0]
    assert np.array_equal(again["image"], out["image"])  # same seed, same draw
