"""Evaluate a trained Phase 2 checkpoint on the (non-disputed) test set.

Usage:
    python -m src.evaluate --config configs/config.yaml --model deeplabv3plus --checkpoint experiments/<...>/best_model.pt

Reports overall IoU/Dice for the infected class, per-disease IoU (test
images grouped by their known disease, from metadata), and infected-area
ratio error, each with a bootstrap 95% CI. See src/severity/metrics.py.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from src.data.severity_transforms import TransformedSeverityDataset
from src.data.wheat_severity_dataset import WheatSeverityDataset
from src.models.segmentation import MODEL_NAMES, build_model
from src.severity.metrics import binary_dice, binary_iou, bootstrap_ci, infected_area_ratio_error
from src.utils.config import load_config


@torch.no_grad()
def collect_per_image_metrics(model, loader, device) -> list[dict]:
    model.eval()
    per_image = []
    for batch in loader:
        images = batch["image"].to(device)
        masks = batch["mask"].numpy()
        diseases = batch["disease"]
        image_ids = batch["image_id"]
        preds = model(images).argmax(dim=1).cpu().numpy()
        for p, m, d, img_id in zip(preds, masks, diseases, image_ids):
            per_image.append({
                "image_id": img_id,
                "disease": d,
                "iou": binary_iou(p, m),
                "dice": binary_dice(p, m),
                "area_err": infected_area_ratio_error(p, m),
            })
    return per_image


def summarize(per_image: list[dict]) -> dict:
    overall_iou = bootstrap_ci([r["iou"] for r in per_image])
    overall_dice = bootstrap_ci([r["dice"] for r in per_image])
    overall_area_err = bootstrap_ci([r["area_err"] for r in per_image])

    by_disease = defaultdict(list)
    for r in per_image:
        by_disease[r["disease"]].append(r["iou"])
    per_disease_iou = {disease: bootstrap_ci(ious) for disease, ious in sorted(by_disease.items())}

    return {
        "n_test_images": len(per_image),
        "overall_iou": {"mean": overall_iou[0], "ci_low": overall_iou[1], "ci_high": overall_iou[2]},
        "overall_dice": {"mean": overall_dice[0], "ci_low": overall_dice[1], "ci_high": overall_dice[2]},
        "overall_area_err": {"mean": overall_area_err[0], "ci_low": overall_area_err[1], "ci_high": overall_area_err[2]},
        "per_disease_iou": {
            disease: {"mean": v[0], "ci_low": v[1], "ci_high": v[2], "n": sum(1 for r in per_image if r["disease"] == disease)}
            for disease, v in per_disease_iou.items()
        },
    }


def evaluate(
    config: dict, model_name: str, checkpoint_path: Path, image_size: int, device: torch.device, debug: bool = False,
) -> tuple[dict, list[dict]]:
    """Returns (summary, per_image) - per_image includes "image_id" for pairing
    across models (see src/compare_baselines.py).
    """
    model = build_model(model_name, num_classes=2).to(device)
    model.load_state_dict(torch.load(checkpoint_path, map_location=device, weights_only=True))

    test_base = WheatSeverityDataset(config, split="test", subset="close_up")
    if debug:
        test_base.rows = test_base.rows[:20]
    test_ds = TransformedSeverityDataset(test_base, image_size, train=False)
    loader = DataLoader(test_ds, batch_size=8, shuffle=False, num_workers=0)

    per_image = collect_per_image_metrics(model, loader, device)
    return summarize(per_image), per_image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--model", required=True, choices=MODEL_NAMES)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    device = torch.device("cpu" if args.debug else ("cuda" if torch.cuda.is_available() else "cpu"))
    image_size = 128 if args.debug else config["image"]["size"]

    checkpoint_path = Path(args.checkpoint)
    results, _per_image = evaluate(config, args.model, checkpoint_path, image_size, device, debug=args.debug)
    print(json.dumps(results, indent=2))

    out_path = checkpoint_path.parent / "test_metrics.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
