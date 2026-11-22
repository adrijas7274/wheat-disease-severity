"""Leaf mask from one click (Phase 3, work order step 1).

SAM 2 gets the rater's stored click as a single positive point and returns 3
candidate masks. A *leaf rule* picks one of them:

    best_score               highest SAM score (the rule fixed in the guidelines)
    largest_containing_click largest candidate that contains the click
                             (falls back to best_score if none does)
    min_area                 highest-scoring candidate covering at least
                             `min_share` of the image (falls back to the
                             largest candidate if none does)

Run on the tuning set to compare the two rules. It writes an overlay sheet and
a table and shows no severities. Only tuning images are allowed here: the rule
must be decided before any gold image is processed.

Usage:
    python -m src.severity.leaf_mask --config configs/config.yaml [--debug]
"""

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

from src.severity import annotation_core as core
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

LEAF_RULES = ("best_score", "largest_containing_click", "min_area")
COLOURS = {"best_score": (0, 200, 255), "largest_containing_click": (255, 60, 200)}
SHEET = Path("report/figures/leaf_masks/tuning_rules.png")
TABLE = Path("report/tables/leaf_mask_tuning.md")


def select_leaf(
    masks: np.ndarray, scores: np.ndarray, click: tuple[int, int], rule: str, min_share: float | None = None,
) -> int:
    """Index of the candidate mask chosen by `rule`.

    masks: (N, H, W) bool; scores: (N,); click: (x, y) in mask pixels;
    min_share: minimum mask share of the image, required by rule 'min_area'.
    """
    if rule not in LEAF_RULES:
        raise ValueError(f"Unknown leaf rule '{rule}'. Expected one of {LEAF_RULES}.")
    best = int(np.argmax(scores))
    if rule == "best_score":
        return best
    if rule == "min_area":
        if min_share is None:
            raise ValueError("Rule 'min_area' needs min_share.")
        shares = [float(m.mean()) for m in masks]
        big = [i for i in range(len(masks)) if shares[i] >= min_share]
        if not big:
            return int(np.argmax(shares))
        return max(big, key=lambda i: float(scores[i]))
    x, y = click
    containing = [i for i in range(len(masks)) if masks[i][y, x]]
    if not containing:
        return best
    return max(containing, key=lambda i: int(masks[i].sum()))


def candidate_masks(predictor, click: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """SAM 2's 3 candidate masks (bool) and scores for one positive click.

    Assumes predictor.set_image() was already called for the current image.
    """
    import torch

    with torch.inference_mode():
        masks, scores, _ = predictor.predict(
            point_coords=np.array([click], dtype=np.float32),
            point_labels=np.array([1], dtype=np.int32),
            multimask_output=True,
        )
    return masks.astype(bool), np.asarray(scores, dtype=float)


def leaf_from_click(predictor, click: tuple[int, int], config: dict) -> np.ndarray:
    """Boolean HxW leaf mask for one click, using the frozen rule in the
    config (`sam2.leaf_rule`, `sam2.leaf_min_area_share`).

    Assumes predictor.set_image() was already called for the current image.
    """
    cfg = config["sam2"]
    masks, scores = candidate_masks(predictor, click)
    return masks[select_leaf(masks, scores, click, cfg["leaf_rule"], cfg.get("leaf_min_area_share"))]


def tuning_rows(config: dict) -> list[dict]:
    """Finished tuning ratings, minus `annotation.tuning_exclude`, in log order."""
    ann = config["annotation"]
    status = core.load_status(Path(ann["out_dir"]) / ann["rating_log"], "tuning")
    exclude = set(ann.get("tuning_exclude", []))
    return [r for n, r in status.items() if r["status"] == "done" and n not in exclude]


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection over union of two boolean masks (nan if both are empty)."""
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else float("nan")


def _tile(img: np.ndarray, leaves: dict[str, np.ndarray], click: tuple[int, int], label: str) -> np.ndarray:
    """One sheet tile: the photo with each rule's leaf outline and the click."""
    import cv2

    vis = img.copy()
    scale = 360 / max(vis.shape[:2])
    for rule, width in (("largest_containing_click", 5), ("best_score", 2)):
        cs, _ = cv2.findContours(leaves[rule].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, cs, -1, COLOURS[rule], max(width, int(width / scale)))
    r = max(5, int(7 / scale))
    cv2.circle(vis, click, r, (255, 255, 0), -1)
    cv2.circle(vis, click, r, (0, 0, 0), max(1, int(2 / scale)))
    small = cv2.resize(vis, (round(vis.shape[1] * scale), round(vis.shape[0] * scale)))
    canvas = np.full((400, 380, 3), 255, np.uint8)
    canvas[: small.shape[0], : small.shape[1]] = small
    cv2.putText(canvas, label, (4, 392), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    return canvas


def compare_rules(rows: list[dict], config: dict, sheet_out: Path) -> list[dict]:
    """Run both leaf rules on each row's click; save the overlay sheet.

    Returns one dict per image: name, disease, each rule's leaf share of the
    image, IoU between the two leaves, and whether the rules chose the same
    candidate.
    """
    from PIL import Image

    from src.data.wheat_metadata import image_path
    from src.severity.sam2_model import load_sam2_predictor

    predictor = load_sam2_predictor(config)
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    results, tiles = [], []
    for row in rows:
        img = np.array(Image.open(image_path(plantseg_dir, row)).convert("RGB"))
        click = (int(row["click_x"]), int(row["click_y"]))
        predictor.set_image(img)
        masks, scores = candidate_masks(predictor, click)
        picks = {rule: select_leaf(masks, scores, click, rule) for rule in COLOURS}
        leaves = {rule: masks[i] for rule, i in picks.items()}
        res = {
            "name": row["name"], "disease": row["disease"],
            "same_candidate": picks["best_score"] == picks["largest_containing_click"],
            "iou": mask_iou(leaves["best_score"], leaves["largest_containing_click"]),
            "click_in_best_score": bool(leaves["best_score"][click[1], click[0]]),
            **{f"{rule}_frac": float(leaves[rule].mean()) for rule in COLOURS},
        }
        results.append(res)
        label = f"{len(tiles) + 1}. {'same' if res['same_candidate'] else 'DIFFERENT'}"
        tiles.append(_tile(img, leaves, click, label))

    cols = 5
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 255))
    sheet_out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])).save(sheet_out)
    return results


def write_table(results: list[dict], out: Path, sheet: Path, commit: str) -> None:
    """Markdown table of the rule comparison (no severities)."""
    n_diff = sum(not r["same_candidate"] for r in results)
    lines = [
        f"# Leaf mask rules on the tuning set ({date.today().isoformat()})",
        "",
        f"Commit at run time: `{commit}`. Generated by `python -m src.severity.leaf_mask`.",
        "",
        "SAM 2 (config `sam2` model), the stored click as one positive point, 3 candidate masks. "
        "`best_score` keeps the highest-scoring candidate. `largest_containing_click` keeps the "
        "largest candidate that contains the click. Leaf % is the leaf's share of the image area. "
        "No severities are used or shown.",
        "",
        f"The two rules chose different candidates on **{n_diff} of {len(results)}** images.",
        "",
        "| # | image | disease | best_score leaf % | largest leaf % | IoU | same candidate |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for i, r in enumerate(results, 1):
        lines.append(
            f"| {i} | `{r['name']}` | {r['disease'].replace('wheat ', '')} | "
            f"{100 * r['best_score_frac']:.1f} | {100 * r['largest_containing_click_frac']:.1f} | "
            f"{r['iou']:.2f} | {'yes' if r['same_candidate'] else '**no**'} |")
    lines += ["", f"Overlay sheet: `{sheet.as_posix()}`. Thin cyan = `best_score`, thick magenta = "
              "`largest_containing_click`, yellow dot = click, numbered as in the table. Where the "
              "rules agree the two outlines coincide. Derived from PlantSeg, see "
              "`report/figures/ATTRIBUTION.md`.", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--debug", action="store_true", help="first 3 tuning images, outputs only in the experiment folder")
    args = parser.parse_args()
    config = load_config(args.config)

    rows = tuning_rows(config)
    exp_dir = create_experiment_dir("leaf_mask_tuning_debug" if args.debug else "leaf_mask_tuning", args.config)
    sheet, table = (exp_dir / SHEET.name, exp_dir / TABLE.name) if args.debug else (SHEET, TABLE)
    results = compare_rules(rows[:3] if args.debug else rows, config, sheet)
    write_table(results, table, sheet, get_git_commit_hash())
    (exp_dir / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for r in results:
        print(f"{'same' if r['same_candidate'] else 'DIFF'}  IoU {r['iou']:.2f}  "
              f"{100 * r['best_score_frac']:5.1f}% vs {100 * r['largest_containing_click_frac']:5.1f}%  {r['name']}")
    print(f"Wrote {table}, {sheet}, {exp_dir}")


if __name__ == "__main__":
    main()
