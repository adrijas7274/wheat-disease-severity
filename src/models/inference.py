"""Single-image inference with a Phase 2 baseline, using the same resize, pad and
normalisation as evaluation (`build_transform(image_size, train=False)`)."""

import hashlib
from pathlib import Path

import cv2
import numpy as np
import torch

from src.data.severity_transforms import build_transform
from src.models.segmentation import build_model


def load_baseline(name: str, checkpoint: str | Path, device: torch.device | str) -> torch.nn.Module:
    """Build a baseline, load its weights and put it in eval mode."""
    model = build_model(name, num_classes=2).to(device)
    model.load_state_dict(torch.load(checkpoint, map_location=device, weights_only=True))
    return model.eval()


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@torch.no_grad()
def predict_region(model: torch.nn.Module, image: np.ndarray, image_size: int, device: torch.device | str) -> np.ndarray:
    """Predicted infected region for one RGB uint8 image, as a bool mask at the model's
    output resolution with the padding cut off (so it has the image's aspect ratio)."""
    out = build_transform(image_size, train=False)(image=image, mask=np.ones(image.shape[:2], np.uint8))
    pred = model(out["image"].unsqueeze(0).to(device)).argmax(dim=1)[0].cpu().numpy().astype(bool)
    valid = out["mask"].numpy() > 0  # 1 where the photo is, 0 where it was padded
    ys, xs = np.nonzero(valid)
    return pred[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def resize_mask(mask: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """Nearest-neighbour resize of a bool mask to (H, W) = shape[:2]."""
    return cv2.resize(mask.astype(np.uint8), (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
