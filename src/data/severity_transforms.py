"""Resize/augment/tensor-conversion wrapper around WheatSeverityDataset for
Phase 2 infected-region segmentation training and evaluation.
"""

import os

# Must be set before `import albumentations`: its own update check does a
# DNS lookup with no timeout, which hung a test run for 3 hours in a
# network-restricted environment (see experiments/LOG.md, 2026-10-05).
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")

import albumentations as A
import numpy as np
from albumentations.pytorch import ToTensorV2
from torch.utils.data import Dataset

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def build_transform(image_size: int, train: bool) -> A.Compose:
    """Standard augmentations only (flip, scale, crop, colour jitter) - no
    phone corruptions yet, those are Phase 4/5.
    """
    if train:
        return A.Compose([
            A.LongestMaxSize(max_size=image_size),
            A.PadIfNeeded(image_size, image_size, border_mode=0, value=0, mask_value=0),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.RandomScale(scale_limit=0.2, p=0.5),
            A.PadIfNeeded(image_size, image_size, border_mode=0, value=0, mask_value=0),
            A.RandomCrop(image_size, image_size),
            A.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05, p=0.5),
            A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ToTensorV2(),
        ])
    return A.Compose([
        A.LongestMaxSize(max_size=image_size),
        A.PadIfNeeded(image_size, image_size, border_mode=0, value=0, mask_value=0),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ToTensorV2(),
    ])


class TransformedSeverityDataset(Dataset):
    """Wraps a WheatSeverityDataset, applying resize/pad/augmentation and
    converting to tensors. The mask is already binary (0=background,
    1=infected region) in PlantSeg, so no remapping is needed here.
    """

    def __init__(self, base_dataset, image_size: int, train: bool):
        self.base = base_dataset
        self.transform = build_transform(image_size, train)

    def __len__(self) -> int:
        return len(self.base)

    def __getitem__(self, idx: int) -> dict:
        sample = self.base[idx]
        mask_binary = (sample["mask"] > 0).astype(np.uint8)
        augmented = self.transform(image=sample["image"], mask=mask_binary)
        return {
            "image": augmented["image"],
            "mask": augmented["mask"].long(),
            "disease": sample["disease"],
            "image_id": sample["image_id"],
        }


class CorruptionAugmentedDataset(Dataset):
    """Phase 5: wraps a WheatSeverityDataset and, with probability `p`, replaces the photo by a
    phone-corrupted copy (random corruption type and level, `src/corruptions`). The mask is unchanged.
    Randomness comes from one generator seeded with `seed`, so a run is reproducible."""

    def __init__(self, base_dataset, p: float, seed: int):
        from src.corruptions.corruptions import CORRUPTIONS, N_LEVELS

        self.base, self.p = base_dataset, p
        self.names, self.n_levels = sorted(CORRUPTIONS), N_LEVELS
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return len(self.base)

    def __getitem__(self, idx: int) -> dict:
        from src.corruptions.corruptions import corrupt

        sample = self.base[idx]
        if self.rng.random() < self.p:
            name = self.names[int(self.rng.integers(len(self.names)))]
            level = int(self.rng.integers(1, self.n_levels + 1))
            draw = int(self.rng.integers(1 << 30))  # a new noise pattern / direction on every visit
            sample = dict(sample, image=corrupt(sample["image"], name, level, draw, sample["image_id"]))
        return sample
