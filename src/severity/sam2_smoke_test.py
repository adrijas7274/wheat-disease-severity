"""SAM 2 smoke test: load the configured checkpoint, segment a few real wheat
images from point clicks, and measure load time, per-image latency and peak
GPU memory.

Uses the 5 pilot-set images (Training split; no tuning or gold images). The
click is placed at a pixel inside PlantSeg's infected-region mask, which is
fine for a smoke test (we only check that SAM runs and returns a sensible
mask) and is not how any annotation or pipeline mask is made.

Usage:
    python -m src.severity.sam2_smoke_test --config configs/config.yaml
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from src.data.wheat_metadata import image_path, mask_path
from src.severity.annotation_sets import build_queues
from src.severity.sam2_model import load_sam2_predictor, predict_from_points, resolve_device
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir


def click_inside(mask: np.ndarray) -> tuple[int, int]:
    """A pixel guaranteed inside `mask`: the foreground pixel nearest its centroid."""
    ys, xs = np.nonzero(mask)
    cy, cx = ys.mean(), xs.mean()
    i = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
    return int(xs[i]), int(ys[i])


def overlay(image: np.ndarray, mask: np.ndarray, click: tuple[int, int]) -> Image.Image:
    """Image with `mask` tinted blue and the click marked red, for eyeballing."""
    out = image.astype(np.float32).copy()
    out[mask] = 0.5 * out[mask] + 0.5 * np.array([30, 144, 255])
    x, y = click
    r = max(4, image.shape[1] // 150)
    out[max(0, y - r): y + r, max(0, x - r): x + r] = [255, 0, 0]
    return Image.fromarray(out.astype(np.uint8))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    device = resolve_device(config["sam2"].get("device", "auto"))
    exp_dir = create_experiment_dir("sam2_smoke_test", args.config)
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = [q[0] for q in build_queues(config, "pilot").values()]

    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    predictor = load_sam2_predictor(config)
    load_s = time.perf_counter() - t0
    weights_mb = torch.cuda.memory_allocated() / 2**20 if device == "cuda" else None

    per_image = []
    for i, row in enumerate(rows):
        image = np.array(Image.open(image_path(plantseg_dir, row)).convert("RGB"))
        region = np.array(Image.open(mask_path(plantseg_dir, row)).convert("L")) > 0
        click = click_inside(region)

        if device == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        predictor.set_image(image)  # image encoder: the expensive step, once per image
        if device == "cuda":
            torch.cuda.synchronize()
        t1 = time.perf_counter()
        mask = predict_from_points(predictor, [(click[0], click[1], 1)])  # decoder: cheap, once per click
        if device == "cuda":
            torch.cuda.synchronize()
        t2 = time.perf_counter()

        overlay(image, mask, click).save(exp_dir / f"overlay_{i}_{row['name']}.png")
        per_image.append({
            "name": row["name"],
            "disease": row["disease"],
            "image_hw": list(image.shape[:2]),
            "encode_s": round(t1 - t0, 3),
            "click_s": round(t2 - t1, 3),
            "mask_fraction": round(float(mask.mean()), 4),
        })
        print(per_image[-1])

    metrics = {
        "device": device,
        "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
        "checkpoint": config["sam2"]["checkpoint"],
        "model_load_s": round(load_s, 2),
        "weights_vram_mb": round(weights_mb, 1) if weights_mb is not None else None,
        "peak_vram_allocated_mb": round(torch.cuda.max_memory_allocated() / 2**20, 1) if device == "cuda" else None,
        "peak_vram_reserved_mb": round(torch.cuda.max_memory_reserved() / 2**20, 1) if device == "cuda" else None,
        # first image includes CUDA warm-up, so it's excluded from the steady-state mean
        "mean_encode_s_excl_first": round(float(np.mean([p["encode_s"] for p in per_image[1:]])), 3),
        "mean_click_s_excl_first": round(float(np.mean([p["click_s"] for p in per_image[1:]])), 3),
        "images": per_image,
    }
    (exp_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in metrics.items() if k != "images"}, indent=2))
    print(f"Overlays and metrics.json in {exp_dir}")


if __name__ == "__main__":
    main()
