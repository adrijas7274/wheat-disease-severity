"""Thin wrapper around SAM 2's image predictor, configured from config.yaml.

SAM 2 is used in Phase 3 for leaf masks and as one of the interactive tools
in the annotation app (src/severity/annotation_tool.py). Point prompts only:
positive clicks are on the object, negative clicks are off it.
"""

from pathlib import Path

import numpy as np
import torch


def resolve_device(device: str) -> str:
    """'auto' -> 'cuda' if a GPU is available, else 'cpu'; anything else is returned as-is."""
    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device


def load_sam2_predictor(config: dict):
    """Build a SAM2ImagePredictor from the config's `sam2` section.

    Raises FileNotFoundError with the download hint if the checkpoint is missing.
    """
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    cfg = config["sam2"]
    ckpt = Path(cfg["checkpoint"])
    if not ckpt.exists():
        raise FileNotFoundError(
            f"SAM 2 checkpoint not found at {ckpt}. Download sam2.1_hiera_tiny.pt "
            "(URL and SHA-256 in experiments/LOG.md, 2026-11-01)."
        )
    device = resolve_device(cfg.get("device", "auto"))
    model = build_sam2(cfg["model_cfg"], str(ckpt), device=device)
    return SAM2ImagePredictor(model)


def predict_from_points(
    predictor, points: list[tuple[int, int, int]]
) -> np.ndarray:
    """Return a boolean HxW mask from (x, y, label) clicks; label 1 = positive, 0 = negative.

    Assumes predictor.set_image() was already called for the current image.
    With a single click SAM is ambiguous (part vs whole object), so it returns
    3 candidates and we keep the highest-scoring one; with 2+ clicks a single
    mask is requested, as the SAM 2 authors recommend.
    """
    if not points:
        raise ValueError("Need at least one click.")
    coords = np.array([[x, y] for x, y, _ in points], dtype=np.float32)
    labels = np.array([lab for _, _, lab in points], dtype=np.int32)
    multimask = len(points) == 1
    with torch.inference_mode():
        masks, scores, _ = predictor.predict(
            point_coords=coords, point_labels=labels, multimask_output=multimask
        )
    return masks[int(np.argmax(scores))].astype(bool)
