"""Shared Phase 3 pipeline: per-image inputs (photo, SAM 2 leaf, region A, region B)
and the severity of every method, plus the error metrics of the evaluation plan.

Used by the tuning script (tuning images) and by the gold evaluation. It never
decides which images to load: the caller passes rating-log rows.
"""

from pathlib import Path

import numpy as np
from PIL import Image

from src.data.wheat_metadata import image_path, load_metadata_rows, mask_path
from src.models.inference import predict_region, resize_mask
from src.severity import refinement as rf
from src.severity.leaf_mask import leaf_from_click
from src.severity.metrics import bootstrap_ci
from src.severity.recheck_report import severity_level

INPUTS = ("A", "B")
BANDS = (("low (< 10%)", 0.0, 10.0), ("medium (10% to < 20%)", 10.0, 20.0), ("high (>= 20%)", 20.0, float("inf")))


def load_inputs(rows: list[dict], config: dict, predictor, model, image_size: int, device) -> list[dict]:
    """For each rating row: the photo, the SAM 2 leaf from the stored click (frozen rule),
    region A (PlantSeg mask) and region B (model prediction), all at photo resolution."""
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    meta = {r["name"]: r for r in load_metadata_rows(plantseg_dir / "Metadata.csv")}
    out = []
    for row in rows:
        image = np.array(Image.open(image_path(plantseg_dir, row)).convert("RGB"))
        predictor.set_image(image)
        leaf = leaf_from_click(predictor, (int(row["click_x"]), int(row["click_y"])), config)
        region_a = np.array(Image.open(mask_path(plantseg_dir, meta[row["name"]])).convert("L")) > 0
        if region_a.shape != image.shape[:2]:
            region_a = resize_mask(region_a, image.shape)
        region_b = resize_mask(predict_region(model, image, image_size, device), image.shape)
        out.append({"name": row["name"], "disease": row["disease"], "group": rf.DISEASE_GROUPS[row["disease"]],
                    "rating": float(row["severity_pct"]), "image": image, "leaf": leaf,
                    "regions": {"A": region_a & leaf, "B": region_b & leaf}})
    return out


def base_severities(item: dict) -> dict[str, float]:
    """Severity (%) of A, B and C0 on each input, for one image."""
    out = {}
    for key in INPUTS:
        region = item["regions"][key]
        out[key] = rf.severity_pct(region, item["leaf"])
        out[f"C0({key})"] = rf.severity_pct(rf.refine_c0(region, item["image"]), item["leaf"])
    return out


def c1_severity(item: dict, key: str, threshold: float, halo: bool = True) -> float:
    """Severity (%) of C1 on input `key` at one threshold, with or without the chlorotic halo."""
    return rf.severity_pct(rf.refine_c1(item["regions"][key], item["image"], item["group"], threshold, halo), item["leaf"])


def mae(pred: list[float], rating: list[float]) -> float:
    return float(np.mean(np.abs(np.asarray(pred) - np.asarray(rating)))) if len(pred) else float("nan")


def error_summary(pred: list[float], rating: list[float], diseases: list[str], config: dict) -> dict:
    """Evaluation-plan metrics for one method: pooled MAE with bootstrap CI, per disease, by rating
    band, and level / decision agreement (PLACEHOLDER thresholds and mapping)."""
    err = np.abs(np.asarray(pred, dtype=float) - np.asarray(rating, dtype=float))

    def ci(mask: np.ndarray) -> dict:
        m, lo, hi = bootstrap_ci(err[mask].tolist())
        return {"mae": m, "ci_low": lo, "ci_high": hi, "n": int(mask.sum())}

    rating_arr, disease_arr = np.asarray(rating, dtype=float), np.asarray(diseases)
    thresholds, mapping = config["severity_thresholds"], config["decision_mapping"]
    levels_pred = [severity_level(p, thresholds) for p in pred]
    levels_true = [severity_level(r, thresholds) for r in rating]
    confusion: dict[str, dict[str, int]] = {}
    for t, p in zip(levels_true, levels_pred):
        confusion.setdefault(t, {}).setdefault(p, 0)
        confusion[t][p] += 1
    n = max(len(err), 1)
    return {
        "pooled": ci(np.ones(len(err), bool)),
        "mean_signed_error": float(np.mean(np.asarray(pred, dtype=float) - rating_arr)) if len(err) else float("nan"),
        "per_disease": {d: ci(disease_arr == d) for d in sorted(set(diseases))},
        "by_rating_band": {name: ci((rating_arr >= lo) & (rating_arr < hi)) for name, lo, hi in BANDS},
        "level_agreement": sum(a == b for a, b in zip(levels_true, levels_pred)) / n,
        "decision_agreement": sum(mapping[a] == mapping[b] for a, b in zip(levels_true, levels_pred)) / n,
        "level_confusion_rating_then_method": confusion,
    }
