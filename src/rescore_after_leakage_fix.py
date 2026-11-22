"""Phase 2 test results before and after the leakage fix (duplicate photos, 2026-11-14).

Scores four checkpoints on the current test set and reports three columns:

- **original**: the first models (trained with duplicate photos in train), all test images;
- **original, no leaked test images**: the same per-image scores without the test images that
  had a copy in the old training set (`test_with_train_copy` in `data.split_exclude_file`);
- **retrained**: the models trained on the cleaned train set, all test images.

Each column has both models, the per-disease IoU and the paired bootstrap on the IoU
difference (SegFormer minus DeepLabV3+). The retrained models on the no-leak subset are
saved in metrics.json as a fourth set, as a cross-check.

Usage:
    python -m src.rescore_after_leakage_fix --config configs/config.yaml \
        --original-deeplabv3plus experiments/<...>/best_model.pt --original-segformer experiments/<...>/best_model.pt \
        --retrained-deeplabv3plus experiments/<...>/best_model.pt --retrained-segformer experiments/<...>/best_model.pt [--debug]
"""

import argparse
import json
from pathlib import Path

import torch
import yaml

from src.evaluate import evaluate, summarize
from src.reevaluate_baselines import paired_summary
from src.utils.config import load_config
from src.utils.experiment import MetricLogger, create_experiment_dir

MODELS = {"deeplabv3plus": "DeepLabV3+MobileNetV3", "segformer": "SegFormer-B0"}
COLUMNS = {"original": "original", "original_no_leak": "original, no leaked test images", "retrained": "retrained"}
PAIRED = "paired_iou_diff_segformer_minus_deeplabv3plus"


def leaked_test_names(config: dict) -> set[str]:
    """Test images that had a copy in the old training set."""
    data = yaml.safe_load(Path(config["data"]["split_exclude_file"]).read_text(encoding="utf-8"))
    return {e["name"] for e in data["test_with_train_copy"]}


def summarize_set(per_image: dict[str, list[dict]]) -> dict:
    """Summary for both models on the same images, plus the paired IoU difference."""
    out = {model: summarize(rows) for model, rows in per_image.items()}
    out[PAIRED] = paired_summary(per_image["deeplabv3plus"], per_image["segformer"])
    return out


def build_sets(original: dict[str, list[dict]], retrained: dict[str, list[dict]], leaked: set[str]) -> dict[str, dict]:
    """The three reported columns and the cross-check set, from per-image scores."""
    def without(per_image: dict[str, list[dict]]) -> dict[str, list[dict]]:
        return {m: [r for r in rows if r["image_id"] not in leaked] for m, rows in per_image.items()}

    return {"original": summarize_set(original), "original_no_leak": summarize_set(without(original)),
            "retrained": summarize_set(retrained), "retrained_no_leak": summarize_set(without(retrained))}


def _ci(v: dict, signed: bool = False) -> str:
    if signed:
        return f"{v['mean']:+.3f} ({v['ci_low']:.3f}, {v['ci_high']:.3f})"
    return f"{v['mean']:.3f} ({v['ci_low']:.3f}-{v['ci_high']:.3f})"


def markdown_tables(sets: dict[str, dict]) -> str:
    """The three-column tables for report/tables/baselines.md."""
    n = {c: sets[c]["segformer"]["n_test_images"] for c in COLUMNS}
    head = "| metric | model | " + " | ".join(f"{label} (n = {n[c]})" for c, label in COLUMNS.items()) + " |"
    lines = [head, "|---|---|" + "---|" * len(COLUMNS)]
    for key, label in (("overall_iou", "overall IoU"), ("overall_dice", "overall Dice"), ("overall_area_err", "area ratio error")):
        for model, model_label in MODELS.items():
            lines.append(f"| {label} | {model_label} | " + " | ".join(_ci(sets[c][model][key]) for c in COLUMNS) + " |")
    lines.append("| paired IoU difference | SegFormer minus DeepLabV3+ | "
                 + " | ".join(_ci(sets[c][PAIRED], signed=True) + (" *" if sets[c][PAIRED]["excludes_zero"] else "")
                              for c in COLUMNS) + " |")
    lines += ["", "\\* 95% CI excludes zero.", "", "Per-disease IoU:", "",
              "| disease | model | " + " | ".join(COLUMNS.values()) + " |", "|---|---|" + "---|" * len(COLUMNS)]
    for disease in sets["original"]["segformer"]["per_disease_iou"]:
        for model, model_label in MODELS.items():
            cells = []
            for c in COLUMNS:
                v = sets[c][model]["per_disease_iou"].get(disease)
                cells.append(f"{_ci(v)}, n = {v['n']}" if v else "-")
            lines.append(f"| {disease.replace('wheat ', '')} | {model_label} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    for which in ("original", "retrained"):
        for model in MODELS:
            parser.add_argument(f"--{which}-{model}", required=True)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    device = torch.device("cpu" if args.debug else ("cuda" if torch.cuda.is_available() else "cpu"))
    image_size = 128 if args.debug else config["image"]["size"]
    per_image: dict[str, dict[str, list[dict]]] = {}
    checkpoints: dict[str, dict[str, str]] = {}
    for which in ("original", "retrained"):
        per_image[which], checkpoints[which] = {}, {}
        for model in MODELS:
            checkpoint = Path(getattr(args, f"{which}_{model}"))
            print(f"{which}: {model}")
            _, per_image[which][model] = evaluate(config, model, checkpoint, image_size, device, debug=args.debug)
            checkpoints[which][model] = checkpoint.as_posix()

    leaked = leaked_test_names(config)
    sets = build_sets(per_image["original"], per_image["retrained"], leaked)
    exp_dir = create_experiment_dir("baselines_leakage_fix" + ("_debug" if args.debug else ""), config_path=args.config)
    (exp_dir / "per_image.json").write_text(json.dumps(per_image, indent=2), encoding="utf-8")
    table = markdown_tables(sets)
    (exp_dir / "tables.md").write_text(table, encoding="utf-8")
    logger = MetricLogger(exp_dir)
    logger.update({"image_size": image_size, "checkpoints": checkpoints, "leaked_test_images": sorted(leaked), **sets})
    print(table)
    print(f"Saved to {logger.save()}")


if __name__ == "__main__":
    main()
