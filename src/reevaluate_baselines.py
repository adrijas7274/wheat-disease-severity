"""Re-run the Phase 2 test evaluation after Test images were re-tagged non_photo.

No retraining: the same checkpoints are scored on the current test set and, as
a control, on the original test set (current tags minus the Test re-tags). The
control should reproduce the numbers first reported in
report/tables/baselines.md, so any change on the new set comes from removing
those images. Writes to a new experiments/ folder; the test_metrics.json next
to each checkpoint is left as it is.

Usage:
    python -m src.reevaluate_baselines --config configs/config.yaml \
        --deeplabv3plus-checkpoint experiments/<...>/best_model.pt \
        --segformer-checkpoint experiments/<...>/best_model.pt [--debug]
"""

import argparse
import csv
import json
from pathlib import Path

import torch

from src.compare_baselines import paired_iou_differences
from src.evaluate import evaluate
from src.severity.metrics import bootstrap_ci
from src.utils.config import load_config
from src.utils.experiment import MetricLogger, create_experiment_dir

IOU_NOISE_TOLERANCE = 1e-3


def is_test_retag(row: dict) -> bool:
    """True for a re-tag row made while rating: a Test image moved to non_photo."""
    return row["split"] == "Test" and row["tag_source"] == "human_annotation" and row["tag"] == "non_photo"


def write_tags_without_test_retags(tags_csv: Path, out_csv: Path) -> list[str]:
    """Copy the tags CSV without the Test re-tag rows, which restores those
    images' earlier tags (the latest row per image wins). Returns their names."""
    with open(tags_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(r for r in rows if not is_test_retag(r))
    return sorted(r["name"] for r in rows if is_test_retag(r))


def paired_summary(per_image_a: list[dict], per_image_b: list[dict]) -> dict:
    """Paired bootstrap CI on the IoU difference, b minus a."""
    mean, low, high = bootstrap_ci(paired_iou_differences(per_image_a, per_image_b))
    return {"mean": mean, "ci_low": low, "ci_high": high, "excludes_zero": bool(low > 0 or high < 0)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--deeplabv3plus-checkpoint", required=True)
    parser.add_argument("--segformer-checkpoint", required=True)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    device = torch.device("cpu" if args.debug else ("cuda" if torch.cuda.is_available() else "cpu"))
    image_size = 128 if args.debug else config["image"]["size"]
    checkpoints = {"deeplabv3plus": Path(args.deeplabv3plus_checkpoint), "segformer": Path(args.segformer_checkpoint)}

    name = "baselines_retest_after_retags" + ("_debug" if args.debug else "")
    exp_dir = create_experiment_dir(name, config_path=args.config)
    tags_name = f"{config['crop']}_tags.csv"
    pre_dir = exp_dir / "pre_retag_tags"
    removed = write_tags_without_test_retags(Path(config["data"]["processed_dir"]) / tags_name, pre_dir / tags_name)
    configs = {"new_test_set": config, "original_test_set": config | {"data": {**config["data"], "processed_dir": str(pre_dir)}}}

    results: dict = {"image_size": image_size, "removed_images": removed}
    per_image: dict = {}
    for set_name, set_config in configs.items():
        per_image[set_name] = {}
        results[set_name] = {}
        for model_name, checkpoint in checkpoints.items():
            print(f"{set_name}: {model_name}")
            summary, rows = evaluate(set_config, model_name, checkpoint, image_size, device, debug=args.debug)
            per_image[set_name][model_name] = rows
            results[set_name][model_name] = summary
        results[set_name]["paired_iou_diff_segformer_minus_deeplabv3plus"] = paired_summary(
            per_image[set_name]["deeplabv3plus"], per_image[set_name]["segformer"])

    results["removed_images_scores"] = {
        model_name: [r for r in per_image["original_test_set"][model_name] if r["image_id"] in removed]
        for model_name in checkpoints
    }
    if not args.debug:
        for model_name in checkpoints:
            n_old = results["original_test_set"][model_name]["n_test_images"]
            n_new = results["new_test_set"][model_name]["n_test_images"]
            if n_old - n_new != len(removed):
                raise ValueError(f"{model_name}: {n_old} -> {n_new} images, but {len(removed)} were re-tagged")
            # Images in both sets should score the same. Batches are composed differently
            # between the sets, so allow for numerical noise (about 5e-5 IoU when measured).
            original = {r["image_id"]: r["iou"] for r in per_image["original_test_set"][model_name]}
            drift = max(abs(r["iou"] - original[r["image_id"]]) for r in per_image["new_test_set"][model_name])
            if drift > IOU_NOISE_TOLERANCE:
                raise ValueError(f"{model_name}: an image's IoU changed by {drift} between the two sets")

    (exp_dir / "per_image.json").write_text(json.dumps(per_image, indent=2), encoding="utf-8")
    logger = MetricLogger(exp_dir)
    logger.update(results)
    print(f"Saved to {logger.save()}")


if __name__ == "__main__":
    main()
