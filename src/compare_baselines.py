"""Compare the two Phase 2 baselines: a paired bootstrap CI on the test IoU
difference (same test images, both models), plus measured model stats
(parameter count, FLOPs at the configured image size, CPU inference time,
checkpoint file size).

Usage:
    python -m src.compare_baselines --config configs/config.yaml \
        --deeplabv3plus-checkpoint experiments/<...>/best_model.pt \
        --segformer-checkpoint experiments/<...>/best_model.pt

FLOPs use torch's built-in torch.utils.flop_counter (no extra dependency).
CPU inference time is always measured on CPU regardless of what the IoU
evaluation ran on, since that's the deployment-relevant number for Phase 8.
"""

import argparse
import json
import time
from pathlib import Path

import torch

from src.evaluate import evaluate
from src.models.segmentation import MODEL_NAMES, build_model
from src.severity.metrics import bootstrap_ci
from src.utils.config import load_config
from src.utils.experiment import MetricLogger, create_experiment_dir


def paired_iou_differences(per_image_a: list[dict], per_image_b: list[dict]) -> list[float]:
    """per_image_b's IoU minus per_image_a's IoU, paired by image_id.

    Raises if the two don't cover exactly the same images - they should,
    since both come from the same deterministic test-set filter.
    """
    a_by_id = {r["image_id"]: r["iou"] for r in per_image_a}
    b_by_id = {r["image_id"]: r["iou"] for r in per_image_b}
    if set(a_by_id) != set(b_by_id):
        raise ValueError("per_image_a and per_image_b must cover exactly the same image_ids")
    return [b_by_id[img_id] - a_by_id[img_id] for img_id in a_by_id]


def count_params(model: torch.nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def measure_flops(model: torch.nn.Module, image_size: int) -> int:
    from torch.utils.flop_counter import FlopCounterMode

    model.eval()
    x = torch.randn(1, 3, image_size, image_size)
    with FlopCounterMode(display=False) as counter, torch.no_grad():
        model(x)
    return counter.get_total_flops()


def measure_cpu_inference_time(model: torch.nn.Module, image_size: int, n_runs: int = 20, n_warmup: int = 5) -> float:
    """Mean wall-clock seconds for one single-image forward pass on CPU."""
    model = model.to("cpu").eval()
    x = torch.randn(1, 3, image_size, image_size)
    with torch.no_grad():
        for _ in range(n_warmup):
            model(x)
        times = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            model(x)
            times.append(time.perf_counter() - t0)
    return sum(times) / len(times)


def measure_model_stats(model_name: str, checkpoint_path: Path, image_size: int) -> dict:
    model = build_model(model_name, num_classes=2)
    model.load_state_dict(torch.load(checkpoint_path, map_location="cpu", weights_only=True))
    return {
        "params": count_params(model),
        "flops_at_image_size": measure_flops(model, image_size),
        "cpu_inference_s": measure_cpu_inference_time(model, image_size),
        "file_size_mb": checkpoint_path.stat().st_size / 1e6,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--deeplabv3plus-checkpoint", required=True)
    parser.add_argument("--segformer-checkpoint", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    image_size = config["image"]["size"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    deeplab_ckpt = Path(args.deeplabv3plus_checkpoint)
    segformer_ckpt = Path(args.segformer_checkpoint)

    print("Evaluating DeepLabV3+MobileNetV3 on test set...")
    _, deeplab_per_image = evaluate(config, "deeplabv3plus", deeplab_ckpt, image_size, device)
    print("Evaluating SegFormer-B0 on test set...")
    _, segformer_per_image = evaluate(config, "segformer", segformer_ckpt, image_size, device)

    diffs = paired_iou_differences(deeplab_per_image, segformer_per_image)
    mean_diff, ci_low, ci_high = bootstrap_ci(diffs)
    excludes_zero = ci_low > 0 or ci_high < 0
    print(f"\nPaired test IoU difference (SegFormer - DeepLabV3+): "
          f"{mean_diff:.4f} ({ci_low:.4f}, {ci_high:.4f}), excludes zero: {excludes_zero}")

    print("\nMeasuring DeepLabV3+MobileNetV3 model stats (CPU)...")
    deeplab_stats = measure_model_stats("deeplabv3plus", deeplab_ckpt, image_size)
    print("Measuring SegFormer-B0 model stats (CPU)...")
    segformer_stats = measure_model_stats("segformer", segformer_ckpt, image_size)

    results = {
        "image_size": image_size,
        "paired_iou_diff_segformer_minus_deeplabv3plus": {
            "mean": mean_diff, "ci_low": ci_low, "ci_high": ci_high, "excludes_zero": excludes_zero,
        },
        "deeplabv3plus_stats": deeplab_stats,
        "segformer_stats": segformer_stats,
    }
    print(json.dumps(results, indent=2))

    exp_dir = create_experiment_dir("baseline_comparison", config_path=args.config)
    logger = MetricLogger(exp_dir)
    logger.update(results)
    out_path = logger.save()
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
