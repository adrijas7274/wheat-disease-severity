"""Blind recheck report: self-consistency of the gold severity ratings.

Compares each recheck rating with the gold rating of the same image
(latest row per set + image in the rating log) and checks with SAM 2 whether
the two clicks picked the same leaf. Writes a markdown table, a scatter plot
and an overlay sheet; prints the summary.

Usage:
    python -m src.severity.recheck_report --config configs/config.yaml

Severity levels use `severity_thresholds` from the config, which are
PLACEHOLDERS (not validated against an agronomy source).
"""

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

from src.severity import annotation_core as core
from src.severity.metrics import bootstrap_ci
from src.utils.config import load_config
from src.utils.git import get_git_commit_hash

LEVELS = ("none", "low", "medium", "high")


def severity_level(severity_pct: float, thresholds: dict) -> str:
    """Bin a severity in percent into none/low/medium/high using config
    thresholds given as fractions (PLACEHOLDER thresholds).

    Mapping since 2026-11-14 (Adrija): none = exactly 0 (no lesion found),
    low = above 0 and below `low_max`, medium = below `medium_max`, high = the rest.
    """
    s = severity_pct / 100.0
    if s <= 0:
        return "none"
    if s < thresholds["low_max"]:
        return "low"
    if s < thresholds["medium_max"]:
        return "medium"
    return "high"


def lins_ccc(x: np.ndarray, y: np.ndarray) -> float:
    """Lin's concordance correlation coefficient (Lin 1989), population
    (1/n) moments: 2*cov / (var_x + var_y + (mean_x - mean_y)^2)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    cov = np.mean((x - x.mean()) * (y - y.mean()))
    denom = x.var() + y.var() + (x.mean() - y.mean()) ** 2
    return float(2 * cov / denom) if denom > 0 else float("nan")


def bootstrap_ccc(x: np.ndarray, y: np.ndarray, n_bootstrap: int = 1000, seed: int = 42) -> tuple[float, float]:
    """Percentile 95% CI for Lin's CCC, resampling image pairs."""
    rng = np.random.default_rng(seed)
    n = len(x)
    vals = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        v = lins_ccc(x[idx], y[idx])
        if not np.isnan(v):
            vals.append(v)
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def same_leaf(mask_a: np.ndarray, mask_b: np.ndarray, click_a: tuple[int, int], click_b: tuple[int, int]) -> bool:
    """Same leaf if each click lies inside the leaf SAM found from the other
    click. Clicks are (x, y) in original pixels; masks are HxW bool."""
    (xa, ya), (xb, yb) = click_a, click_b
    return bool(mask_b[ya, xa] and mask_a[yb, xb])


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else float("nan")


def paired_rows(log_csv: Path) -> list[dict]:
    """One dict per image with a done recheck row and a done gold row."""
    gold = core.load_status(log_csv, "gold")
    rech = core.load_status(log_csv, "recheck")
    out = []
    for name, r in sorted(rech.items()):
        g = gold.get(name)
        if r["status"] != "done" or g is None or g["status"] != "done":
            continue
        out.append({
            "name": name, "split": g["split"], "disease": g["disease"],
            "gold": float(g["severity_pct"]), "recheck": float(r["severity_pct"]),
            "gold_click": (int(g["click_x"]), int(g["click_y"])),
            "recheck_click": (int(r["click_x"]), int(r["click_y"])),
        })
    return out


def agreement(pairs: list[dict], thresholds: dict, seed: int) -> dict:
    g = np.array([p["gold"] for p in pairs])
    r = np.array([p["recheck"] for p in pairs])
    mad, lo, hi = bootstrap_ci(list(np.abs(g - r)), seed=seed)
    ccc_lo, ccc_hi = bootstrap_ccc(g, r, seed=seed)
    same = [severity_level(a, thresholds) == severity_level(b, thresholds) for a, b in zip(g, r)]
    return {
        "n": len(pairs), "mad": mad, "mad_ci": [lo, hi],
        "mean_signed_diff_recheck_minus_gold": float(np.mean(r - g)),
        "ccc": lins_ccc(g, r), "ccc_ci": [ccc_lo, ccc_hi],
        "pearson_r": float(np.corrcoef(g, r)[0, 1]),
        "same_level": int(sum(same)), "same_level_frac": float(np.mean(same)),
    }


def scatter(pairs: list[dict], out: Path, thresholds: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    g = [p["gold"] for p in pairs]
    r = [p["recheck"] for p in pairs]
    top = max(max(g), max(r)) * 1.08 + 1
    fig, ax = plt.subplots(figsize=(5, 5), dpi=150)
    ax.plot([0, top], [0, top], color="0.6", lw=1, ls="--", label="perfect agreement")
    for t in (thresholds["low_max"], thresholds["medium_max"]):
        if t * 100 < top:
            ax.axvline(t * 100, color="0.85", lw=0.8)
            ax.axhline(t * 100, color="0.85", lw=0.8)
    diseases = sorted({p["disease"] for p in pairs})
    for d in diseases:
        xs = [p["gold"] for p in pairs if p["disease"] == d]
        ys = [p["recheck"] for p in pairs if p["disease"] == d]
        ax.scatter(xs, ys, s=28, label=d.replace("wheat ", "").replace(" (black chaff)", ""))
    ax.set_xlim(0, top)
    ax.set_ylim(0, top)
    ax.set_aspect("equal")
    ax.set_xlabel("Gold rating (% leaf area)")
    ax.set_ylabel("Blind recheck rating (% leaf area)")
    ax.set_title(f"Gold vs blind recheck (n = {len(pairs)})")
    ax.legend(fontsize=7, loc="upper left")
    ax.text(0.99, 0.01, "grey lines: placeholder level thresholds", transform=ax.transAxes,
            fontsize=6, ha="right", va="bottom", color="0.4")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)


def leaf_check(pairs: list[dict], config: dict, sheet_out: Path) -> list[dict]:
    """Run SAM 2 from each click (single positive point, best of 3 masks) and
    compare the two leaves. Saves an overlay sheet (clicks + leaf outlines, no
    severities) for visual checking."""
    import cv2
    from PIL import Image

    from src.data.wheat_metadata import image_path
    from src.severity.sam2_model import load_sam2_predictor, predict_from_points

    predictor = load_sam2_predictor(config)
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    results, tiles = [], []
    for p in pairs:
        img = np.array(Image.open(image_path(plantseg_dir, p)).convert("RGB"))
        predictor.set_image(img)
        mg = predict_from_points(predictor, [(*p["gold_click"], 1)])
        mr = predict_from_points(predictor, [(*p["recheck_click"], 1)])
        res = {"name": p["name"], "same_leaf": same_leaf(mg, mr, p["gold_click"], p["recheck_click"]),
               "iou": mask_iou(mg, mr),
               "gold_leaf_frac": float(mg.mean()), "recheck_leaf_frac": float(mr.mean())}
        results.append(res)

        vis = img.copy()
        scale = 360 / max(vis.shape[:2])
        for mask, colour in ((mg, (0, 200, 255)), (mr, (255, 60, 200))):
            cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(vis, cs, -1, colour, max(2, int(3 / scale)))
        for (x, y), colour in ((p["gold_click"], (0, 200, 255)), (p["recheck_click"], (255, 60, 200))):
            cv2.circle(vis, (x, y), max(5, int(7 / scale)), colour, -1)
            cv2.circle(vis, (x, y), max(5, int(7 / scale)), (0, 0, 0), max(1, int(2 / scale)))
        tile = cv2.resize(vis, (round(vis.shape[1] * scale), round(vis.shape[0] * scale)))
        canvas = np.full((400, 380, 3), 255, np.uint8)
        canvas[: tile.shape[0], : tile.shape[1]] = tile
        label = f"{len(tiles) + 1}. {'same' if res['same_leaf'] else 'DIFFERENT'} IoU {res['iou']:.2f}"
        cv2.putText(canvas, label, (4, 392), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        tiles.append(canvas)

    cols = 5
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 255))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    sheet_out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.vstack(rows)).save(sheet_out)
    return results


def write_table(pairs, stats, leaves, thresholds, out: Path, commit: str, figs: dict) -> None:
    by = {l["name"]: l for l in leaves}
    lv = lambda s: severity_level(s, thresholds)  # noqa: E731
    n_same = sum(l["same_leaf"] for l in leaves)
    lines = [
        f"# Blind recheck: gold vs recheck ({date.today().isoformat()})",
        "",
        f"Source: `data/annotations/rating_log.csv`, latest row per set + image. "
        f"Commit at run time: `{commit}`. Generated by `python -m src.severity.recheck_report`.",
        "",
        "## Agreement",
        "",
        "| metric | value |",
        "|---|---|",
        f"| images | {stats['n']} |",
        f"| mean absolute difference (pts) | {stats['mad']:.2f} (95% CI {stats['mad_ci'][0]:.2f} to {stats['mad_ci'][1]:.2f}) |",
        f"| mean signed difference, recheck - gold (pts) | {stats['mean_signed_diff_recheck_minus_gold']:+.2f} |",
        f"| Lin's CCC | {stats['ccc']:.3f} (95% CI {stats['ccc_ci'][0]:.3f} to {stats['ccc_ci'][1]:.3f}) |",
        f"| Pearson r | {stats['pearson_r']:.3f} |",
        f"| same severity level (PLACEHOLDER thresholds) | {stats['same_level']} / {stats['n']} |",
        f"| same leaf (SAM 2 from each click) | {n_same} / {len(leaves)} |",
        "",
        "Bootstrap: 1000 percentile resamples of images, seed from config. With n = 15 the "
        "CIs are wide. Levels: none < "
        f"{thresholds['low_max']*100:g}%, low < {thresholds['medium_max']*100:g}%, "
        f"else high. **These thresholds are "
        "placeholders, not validated against an agronomy source.**",
        "",
        "Same leaf = each click lies inside the leaf SAM 2 (hiera tiny, one positive point, "
        "highest-scoring of 3 masks) finds from the other click. IoU is between the two SAM leaves.",
        "",
        "## Per image",
        "",
        "| # | image | disease | gold % | recheck % | diff | gold level | recheck level | same leaf | leaf IoU |",
        "|---:|---|---|---:|---:|---:|---|---|---|---:|",
    ]
    for i, p in enumerate(pairs, 1):
        l = by[p["name"]]
        lines.append(
            f"| {i} | `{p['name']}` | {p['disease'].replace('wheat ', '')} | {p['gold']:g} | {p['recheck']:g} | "
            f"{p['recheck'] - p['gold']:+g} | {lv(p['gold'])} | {lv(p['recheck'])} | "
            f"{'yes' if l['same_leaf'] else '**no**'} | {l['iou']:.2f} |")
    lines += ["", "## Figures", "",
              f"- `{figs['scatter']}`: gold vs recheck scatter.",
              f"- `{figs['sheet']}`: SAM 2 leaves from the gold click (cyan) and recheck click "
              "(magenta), numbered as in the table. No severities shown. Derived from PlantSeg, "
              "see `report/figures/ATTRIBUTION.md`.", ""]
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    ann = config["annotation"]
    log_csv = Path(ann["out_dir"]) / ann["rating_log"]
    thresholds = config["severity_thresholds"]

    pairs = paired_rows(log_csv)
    if len(pairs) != ann["recheck_n"]:
        raise ValueError(f"Expected {ann['recheck_n']} gold/recheck pairs, found {len(pairs)}.")
    stats = agreement(pairs, thresholds, config["seed"])
    figs = {"scatter": "report/figures/recheck/gold_vs_recheck_scatter.png",
            "sheet": "report/figures/recheck/same_leaf_check.png"}
    scatter(pairs, Path(figs["scatter"]), thresholds)
    leaves = leaf_check(pairs, config, Path(figs["sheet"]))
    stats["same_leaf"] = sum(l["same_leaf"] for l in leaves)
    table = Path("report/tables/recheck_agreement.md")
    write_table(pairs, stats, leaves, thresholds, table, get_git_commit_hash(), figs)
    print(json.dumps(stats, indent=2))
    for l in leaves:
        print(f"{'same' if l['same_leaf'] else 'DIFF'}  IoU {l['iou']:.2f}  {l['name']}")
    print(f"Wrote {table}, {figs['scatter']}, {figs['sheet']}")


if __name__ == "__main__":
    main()
