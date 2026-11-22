"""Pre-gold round 2: stage-by-stage diagnosis of the worst tuning images.

For the tuning images with the largest error of the frozen method (C on input
B), one figure each with four panels side by side:

    photo + click | leaf outline (SAM 2) | model region (B) on the leaf | refined lesions

and per-stage numbers (leaf share of the image, region share of the leaf,
lesion-colour and halo share of the leaf), so the failing stage (leaf, region
or colour) can be named. Only tuning images are read (`leaf_mask.tuning_rows`);
nothing here can load a gold image.

Usage:
    python -m src.severity.diagnose_tuning --config configs/config.yaml [--n 3] [--debug]
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from src.severity import refinement as rf
from src.severity import severity_pipeline as sp
from src.severity.leaf_mask import tuning_rows
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir

FIG_DIR = Path("report/figures/pregold_round2")
PANEL_SIDE = 520


def stage_numbers(item: dict, threshold: float) -> dict:
    """Per-stage shares for one image, on input B with the C1 threshold given."""
    image, leaf, region = item["image"], item["leaf"], item["regions"]["B"]
    lesion = region & rf.lesion_colour(image, item["group"], threshold)
    refined = rf.refine_c1(region, image, item["group"], threshold)
    n_leaf = max(int(leaf.sum()), 1)
    L, a, b = rf.lab(image)
    inside = leaf & region
    return {
        "name": item["name"], "disease": item["disease"], "group": item["group"], "rating": item["rating"],
        "threshold": threshold,
        "leaf_share_of_image_pct": 100.0 * float(leaf.mean()),
        "region_share_of_leaf_pct": 100.0 * int(region.sum()) / n_leaf,
        "lesion_colour_share_of_leaf_pct": 100.0 * int(lesion.sum()) / n_leaf,
        "halo_share_of_leaf_pct": 100.0 * int((refined & ~lesion).sum()) / n_leaf,
        "c1_severity_pct": rf.severity_pct(refined, leaf),
        "error_points": rf.severity_pct(refined, leaf) - item["rating"],
        "lab_in_region_percentiles_5_25_50_75_95": {
            ch: [float(np.percentile(v[inside], p)) for p in (5, 25, 50, 75, 95)] if inside.any() else []
            for ch, v in (("L", L), ("a", a), ("b", b), ("chroma", np.hypot(a, b)))},
    }


def _fit(img: np.ndarray) -> np.ndarray:
    scale = PANEL_SIDE / max(img.shape[:2])
    small = cv2.resize(img, (max(1, round(img.shape[1] * scale)), max(1, round(img.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((PANEL_SIDE + 34, PANEL_SIDE, 3), 255, np.uint8)
    canvas[34:34 + small.shape[0], :small.shape[1]] = small
    return canvas


def _outline(img: np.ndarray, mask: np.ndarray, colour: tuple[int, int, int]) -> np.ndarray:
    out = img.copy()
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, cs, -1, colour, max(2, round(max(img.shape[:2]) / 250)))
    return out


def _tint(img: np.ndarray, mask: np.ndarray, colour: tuple[int, int, int], alpha: float = 0.55) -> np.ndarray:
    out = img.astype(np.float32)
    out[mask] = (1 - alpha) * out[mask] + alpha * np.array(colour, np.float32)
    return out.astype(np.uint8)


def _title(panel: np.ndarray, text: str) -> np.ndarray:
    cv2.putText(panel, text, (6, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 1, cv2.LINE_AA)
    return panel


def figure(item: dict, click: tuple[int, int], numbers: dict) -> np.ndarray:
    """Four panels: photo + click, leaf outline, model region, refined lesions (lesion colour red, halo yellow)."""
    image, leaf, region = item["image"], item["leaf"], item["regions"]["B"]
    lesion = region & rf.lesion_colour(image, item["group"], numbers["threshold"])
    refined = rf.refine_c1(region, image, item["group"], numbers["threshold"])
    photo = image.copy()
    r = max(6, round(max(image.shape[:2]) / 70))
    cv2.circle(photo, click, r, (255, 255, 0), -1)
    cv2.circle(photo, click, r, (0, 0, 0), max(1, r // 4))
    leaf_panel = _outline(image, leaf, (0, 200, 255))
    region_panel = _outline(_tint(image, region, (255, 0, 255), 0.4), leaf, (0, 200, 255))
    refined_panel = _outline(_tint(_tint(image, refined & ~lesion, (255, 230, 0)), lesion, (255, 0, 0)), leaf, (0, 200, 255))
    n = numbers
    panels = [
        _title(_fit(photo), f"photo + click   rating {n['rating']:.1f}%"),
        _title(_fit(leaf_panel), f"leaf (SAM 2)   {n['leaf_share_of_image_pct']:.0f}% of image"),
        _title(_fit(region_panel), f"model region   {n['region_share_of_leaf_pct']:.0f}% of leaf"),
        _title(_fit(refined_panel), f"refined {n['c1_severity_pct']:.1f}% (red {n['lesion_colour_share_of_leaf_pct']:.1f} + halo {n['halo_share_of_leaf_pct']:.1f})"),
    ]
    return np.hstack(panels)


def main() -> None:
    import torch
    from PIL import Image

    from src.models.inference import load_baseline
    from src.severity.sam2_model import load_sam2_predictor

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--n", type=int, default=3, help="number of worst images to draw")
    parser.add_argument("--debug", action="store_true", help="first 3 tuning images, figures only in the experiment folder")
    args = parser.parse_args()
    config = load_config(args.config)
    method = config["severity_method"]

    rows = tuning_rows(config)[:3] if args.debug else tuning_rows(config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_baseline(method["model"], method["checkpoint"], device)
    items = sp.load_inputs(rows, config, load_sam2_predictor(config), model, config["image"]["size"], device)
    clicks = {r["name"]: (int(r["click_x"]), int(r["click_y"])) for r in rows}

    numbers = [stage_numbers(i, method["c1_thresholds"][i["group"]]) for i in items]
    order = sorted(range(len(items)), key=lambda k: -abs(numbers[k]["error_points"]))[:args.n]
    exp_dir = create_experiment_dir("pregold_round2_diagnosis" + ("_debug" if args.debug else ""), args.config)
    fig_dir = exp_dir if args.debug else FIG_DIR
    fig_dir.mkdir(parents=True, exist_ok=True)
    for rank, k in enumerate(order, 1):
        out = fig_dir / f"diagnosis_{rank}.png"
        Image.fromarray(figure(items[k], clicks[items[k]["name"]], numbers[k])).save(out)
        numbers[k]["figure"] = out.as_posix()
        print(f"{rank}. {items[k]['name']}  error {numbers[k]['error_points']:+.1f}  -> {out}")
    (exp_dir / "metrics.json").write_text(json.dumps({"worst": [numbers[k] for k in order], "all": numbers}, indent=2), encoding="utf-8")
    print(json.dumps([numbers[k] for k in order], indent=1))
    print(f"Wrote {exp_dir}")


if __name__ == "__main__":
    main()
