"""Phase 4: cheap-phone corruption benchmark. One command, test set then gold cross-check.

For every model x corruption x level it reports
    mIoU                 infected-region IoU against the PlantSeg mask (as in Phase 2: 512 px, padded)
    severity shift       mean |severity(corrupted) - severity(clean)| in points, same image and model
    level accuracy       share of images whose severity level equals the clean image's level
    decision flip rate   share of images whose decision differs from the clean image's decision
and, model-independent, the IoU of the SAM 2 leaf with the clean image's leaf.

**Reference = the same model on the clean image**, not a human rating: test images
have no ratings, and the research question is how far the estimate moves. On the
gold images (real clicks) the error against the rating is reported as well.

Severity is the frozen Phase 3 method (`severity_method` in the config) run end to
end on the corrupted image: the model's region, the SAM 2 leaf and the colour
refinement all see the corrupted pixels.

Click (rule fixed 2026-11-11): on test images, the deepest point of the largest
infected component predicted by `click_model` on the clean image (image centre if
none); on gold images the rater's stored click. The same click is reused for every
corrupted version and SAM 2 is re-run on each.

A corrupted image with no estimate (empty leaf) counts as a flip and as a level
miss. Images whose clean estimate is missing are left out and counted.

Severity levels and the decision mapping are **PLACEHOLDERS** (config), not
validated against an agronomy source. The corruption levels are placeholders too.

Usage:
    python -m src.corruptions.benchmark --config configs/config.yaml \
        --experiment configs/experiments/phase4_benchmark.yaml [--debug] [--resume experiments/<dir>]
"""

import argparse
import json
import math
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import yaml

from src.severity.metrics import binary_iou, bootstrap_ci
from src.severity.recheck_report import severity_level
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

TABLE = Path("report/tables/robustness.md")
FIG_DIR = Path("report/figures/robustness")
CLEAN = "clean"
METRICS = (("miou", "mIoU (infected region)", "{:.3f}"), ("severity_shift", "severity shift, points", "{:.1f}"),
           ("level_accuracy", "severity-level accuracy vs clean", "{:.2f}"), ("flip_rate", "decision flip rate", "{:.2f}"))
MODEL_LABELS = {"segformer": "SegFormer-B0", "deeplabv3plus": "DeepLabV3+ MobileNetV3"}
MODEL_COLOURS = {"segformer": "#0072B2", "deeplabv3plus": "#D55E00"}  # colour-blind safe pair


# ----------------------------------------------------------------------------- per-image work (needs torch)

def predict_with_iou(model, image: np.ndarray, mask: np.ndarray, image_size: int, device) -> tuple[np.ndarray, float]:
    """(predicted region at output resolution with padding cut off, IoU against the mask in the padded
    model space - the same space as Phase 2's test IoU)."""
    import torch

    from src.data.severity_transforms import build_transform

    out = build_transform(image_size, train=False)(image=image, masks=[mask.astype(np.uint8), np.ones(image.shape[:2], np.uint8)])
    with torch.no_grad():
        pred = model(out["image"].unsqueeze(0).to(device)).argmax(dim=1)[0].cpu().numpy().astype(bool)
    true, valid = np.asarray(out["masks"][0]) > 0, np.asarray(out["masks"][1]) > 0
    ys, xs = np.nonzero(valid)
    return pred[ys.min():ys.max() + 1, xs.min():xs.max() + 1], binary_iou(pred, true)


def frozen_severity(image: np.ndarray, leaf: np.ndarray, region: np.ndarray, group: str, method: dict) -> float:
    """Severity (%) of the frozen Phase 3 method for one image, leaf and region (nan if the leaf is empty)."""
    from src.severity import refinement as rf

    region = region & leaf
    if method["refinement"] == "C0":
        lesion = rf.refine_c0(region, image)
    else:
        lesion = rf.refine_c1(region, image, group, method["c1_thresholds"][group],
                              halo=(method.get("c1_halo") or {}).get(group, True))
    return rf.severity_pct(lesion, leaf)


def process_image(entry: dict, models: dict, click_model: str, predictor, conditions: list[tuple[str, int]],
                  config: dict, image_size: int, device) -> list[dict]:
    """All records of one image: the clean image first, then every (corruption, level)."""
    from PIL import Image

    from src.corruptions.corruptions import corrupt
    from src.models.inference import resize_mask
    from src.severity.auto_click import click_from_region
    from src.severity.leaf_mask import leaf_from_click, mask_iou
    from src.severity.refinement import DISEASE_GROUPS

    image = np.array(Image.open(entry["image_path"]).convert("RGB"))
    mask = np.array(Image.open(entry["mask_path"]).convert("L")) > 0
    if mask.shape != image.shape[:2]:
        mask = resize_mask(mask, image.shape)
    group, method = DISEASE_GROUPS[entry["disease"]], config["severity_method"]
    click, clean_leaf, records = entry.get("click"), None, []
    for name, level in [(CLEAN, 0)] + conditions:
        img = image if name == CLEAN else corrupt(image, name, level, config["seed"], entry["name"])
        preds = {m: predict_with_iou(model, img, mask, image_size, device) for m, model in models.items()}
        if click is None:  # only on the clean image, which comes first
            click = click_from_region(preds[click_model][0], image.shape)
        predictor.set_image(img)
        leaf = leaf_from_click(predictor, click, config)
        if name == CLEAN:
            clean_leaf = leaf
        rec = {"name": entry["name"], "disease": entry["disease"], "corruption": name, "level": level,
               "click": list(click), "leaf_share": float(leaf.mean()), "leaf_iou_vs_clean": mask_iou(leaf, clean_leaf),
               "models": {}}
        for m, (region, iou) in preds.items():
            rec["models"][m] = {"iou": iou, "severity": frozen_severity(img, leaf, resize_mask(region, image.shape), group, method)}
        if entry.get("rating") is not None:
            rec["rating"] = entry["rating"]
        records.append(rec)
    return records


# ----------------------------------------------------------------------------- image lists

def test_entries(config: dict) -> list[dict]:
    """The Phase 2 test set (close_up, non-disputed), no stored clicks."""
    from src.data.wheat_metadata import image_path, mask_path
    from src.data.wheat_severity_dataset import WheatSeverityDataset

    ds = WheatSeverityDataset(config, split="test", subset="close_up")
    return [{"name": r["name"], "disease": r["disease"], "image_path": str(image_path(ds.plantseg_dir, r)),
             "mask_path": str(mask_path(ds.plantseg_dir, r))} for r in ds.rows]


def rated_entries(rows: list[dict], config: dict) -> list[dict]:
    """Rating-log rows (gold or tuning) with their stored click and rating."""
    from src.data.wheat_metadata import image_path, load_metadata_rows, mask_path

    plantseg_dir = Path(config["data"]["plantseg_dir"])
    meta = {r["name"]: r for r in load_metadata_rows(plantseg_dir / "Metadata.csv")}
    return [{"name": r["name"], "disease": r["disease"], "image_path": str(image_path(plantseg_dir, r)),
             "mask_path": str(mask_path(plantseg_dir, meta[r["name"]])),
             "click": (int(r["click_x"]), int(r["click_y"])), "rating": float(r["severity_pct"])} for r in rows]


# ----------------------------------------------------------------------------- aggregation (pure)

def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _ci(values: list[float]) -> dict:
    m, lo, hi = bootstrap_ci(values)
    return {"mean": m, "ci_low": lo, "ci_high": hi, "n": len(values)}


def decision(severity: float, config: dict) -> str | None:
    """Decision for a severity in % (None if there is no estimate). PLACEHOLDER thresholds and mapping."""
    return None if _nan(severity) else config["decision_mapping"][severity_level(severity, config["severity_thresholds"])]


def aggregate(records: list[dict], model: str, config: dict) -> dict:
    """{corruption: {level: metrics}} for one model, plus the clean row under 'clean'.

    Each metric is {"mean", "ci_low", "ci_high", "n"} (bootstrap 95% CI over images).
    """
    clean = {r["name"]: r for r in records if r["corruption"] == CLEAN}
    usable = {n for n, r in clean.items() if not _nan(r["models"][model]["severity"])}
    thresholds = config["severity_thresholds"]
    flip_thresholds = list((config.get("phase4") or {}).get("flip_thresholds", []))
    cells: dict[tuple[str, int], list[dict]] = {}
    for r in records:
        cells.setdefault((r["corruption"], r["level"]), []).append(r)
    out: dict = {"n_images": len(clean), "n_without_clean_estimate": len(clean) - len(usable)}
    for (name, level), recs in sorted(cells.items()):
        shift, level_ok, flip, rating_err, rating_dec = [], [], [], [], []
        flip_at: dict[str, list[float]] = {str(t): [] for t in flip_thresholds}
        n_no_estimate = 0
        for r in recs:
            if r["name"] not in usable:
                continue
            ref, sev = clean[r["name"]]["models"][model]["severity"], r["models"][model]["severity"]
            if _nan(sev):
                n_no_estimate += 1
                level_ok.append(0.0)
                flip.append(1.0)
                for t in flip_thresholds:
                    flip_at[str(t)].append(1.0)
            else:
                shift.append(abs(sev - ref))
                level_ok.append(float(severity_level(sev, thresholds) == severity_level(ref, thresholds)))
                flip.append(float(decision(sev, config) != decision(ref, config)))
                for t in flip_thresholds:  # the estimate crosses a single threshold
                    flip_at[str(t)].append(float((sev >= t) != (ref >= t)))
                if "rating" in r:
                    rating_err.append(abs(sev - r["rating"]))
            if "rating" in r:
                rating_dec.append(float(decision(sev, config) == decision(r["rating"], config)))
        cell = {"miou": _ci([r["models"][model]["iou"] for r in recs]), "severity_shift": _ci(shift),
                "level_accuracy": _ci(level_ok), "flip_rate": _ci(flip), "n_no_estimate": n_no_estimate,
                "flip_at": {t: _ci(v) for t, v in flip_at.items()},
                "leaf_iou_vs_clean": _ci([r["leaf_iou_vs_clean"] for r in recs if not _nan(r["leaf_iou_vs_clean"])])}
        if rating_dec:
            cell["mae_vs_rating"] = _ci(rating_err)
            cell["decision_agreement_with_rating"] = _ci(rating_dec)
        out.setdefault(name, {})[str(level)] = cell
    return out


# ----------------------------------------------------------------------------- report

def _matrix(agg: dict, metric: str, fmt: str, corruptions: list[str], levels: list[int], with_ci: bool = False) -> list[str]:
    lines = ["| corruption | " + " | ".join(f"level {lv}" for lv in levels) + " |", "|---|" + "---:|" * len(levels)]
    for c in corruptions:
        cells = []
        for lv in levels:
            v = agg[c][str(lv)][metric]
            cells.append(fmt.format(v["mean"]) + (f" ({fmt.format(v['ci_low'])}-{fmt.format(v['ci_high'])})" if with_ci else ""))
        lines.append(f"| {c} | " + " | ".join(cells) + " |")
    return lines


def _threshold_flip_lines(agg: dict, corruptions: list[str], levels: list[int]) -> list[str]:
    """Flip rate at each single threshold, at the middle and the highest level."""
    ts = list(agg[corruptions[0]][str(levels[0])].get("flip_at", {}))
    if not ts:
        return []
    shown = sorted({levels[len(levels) // 2], levels[-1]})
    head = [f"{t}% (level {lv})" for lv in shown for t in ts]
    lines = ["", "**flip rate at a single threshold** (the estimate crosses the threshold between clean and corrupted)", "",
             "| corruption | " + " | ".join(head) + " |", "|---|" + "---:|" * len(head)]
    for c in corruptions:
        lines.append(f"| {c} | " + " | ".join(f"{agg[c][str(lv)]['flip_at'][t]['mean']:.2f}" for lv in shown for t in ts) + " |")
    return lines


def format_set(title: str, aggs: dict[str, dict], corruptions: list[str], levels: list[int], rated: bool) -> list[str]:
    """Markdown for one image set: the clean row, then one matrix per model and metric."""
    first = next(iter(aggs.values()))
    lines = [f"## {title}", "", f"{first['n_images']} images.", "",
             "Clean images (level 0):", "", "| model | mIoU (95% CI) | images without a clean estimate |" + (" MAE vs rating | decision agreement with rating |" if rated else ""),
             "|---|---|---:|" + ("---|---:|" if rated else "")]
    for m, agg in aggs.items():
        c = agg[CLEAN]["0"]
        row = f"| {MODEL_LABELS.get(m, m)} | {c['miou']['mean']:.3f} ({c['miou']['ci_low']:.3f}-{c['miou']['ci_high']:.3f}) | {agg['n_without_clean_estimate']} |"
        if rated:
            row += (f" {c['mae_vs_rating']['mean']:.2f} ({c['mae_vs_rating']['ci_low']:.2f}-{c['mae_vs_rating']['ci_high']:.2f}) |"
                    f" {100 * c['decision_agreement_with_rating']['mean']:.0f}% |")
        lines.append(row)
    for m, agg in aggs.items():
        lines += ["", f"### {MODEL_LABELS.get(m, m)}"]
        for key, label, fmt in METRICS:
            ci = key == "flip_rate"
            lines += ["", f"**{label}**" + (" (bootstrap 95% CI)" if ci else ""), ""] + _matrix(agg, key, fmt, corruptions, levels, with_ci=ci)
        lines += _threshold_flip_lines(agg, corruptions, levels)
        if rated:
            lines += ["", "**severity MAE against the rating, points** (resolution limit 3.64)", ""] + _matrix(agg, "mae_vs_rating", "{:.1f}", corruptions, levels)
    lines += ["", "### SAM 2 leaf: IoU with the clean image's leaf (same click; model-independent)", ""]
    lines += _matrix(first, "leaf_iou_vs_clean", "{:.2f}", corruptions, levels)
    no_est = {m: sum(agg[c][str(lv)]["n_no_estimate"] for c in corruptions for lv in levels) for m, agg in aggs.items()}
    lines += ["", "Corrupted images with no estimate (empty leaf; counted as flips): "
              + ", ".join(f"{MODEL_LABELS.get(m, m)} {n}" for m, n in no_est.items()) + "."]
    return lines


def format_report(sets: dict[str, dict], corruptions: list[str], levels: list[int], config: dict, experiment: dict, commit: str) -> str:
    t, method = config["severity_thresholds"], config["severity_method"]
    lines = [
        f"# Phase 4: cheap-phone corruption benchmark ({date.today().isoformat()})", "",
        f"Commit at run time: `{commit}`. Generated by `python -m src.corruptions.benchmark`.", "",
        "Every number compares a corrupted image with **the same model's result on the clean image** (severity shift, "
        "level accuracy, flip rate) or with the PlantSeg region mask (mIoU). Severity is the frozen Phase 3 method "
        f"({method['refinement']}, leaf from SAM 2) run end to end on the corrupted image. Click: on test images the "
        f"automatic rule on `{experiment['click_model']}`'s clean prediction; on gold images the rater's click.", "",
        f"**Placeholders:** the corruption levels (hand-set, not calibrated on real phones; level 3 of one corruption is "
        f"not comparable with level 3 of another), the severity levels (none = 0%, low below {100 * t['low_max']:g}%, medium below "
        f"{100 * t['medium_max']:g}%, high above) and the decision mapping. The decision is one-to-one with the level, so "
        "flip rate = 1 - level accuracy. **Severity shift in points is the primary metric: it does not depend on any threshold.**", "",
        "**The frozen severity method is about 14 points from the gold ratings** (`report/tables/gold_evaluation.md`), so "
        "this benchmark measures how stable the estimate is, not how correct it is.", "",
        "Figures: `report/figures/robustness/`.", ""]
    for title, payload in sets.items():
        lines += format_set(title, payload["aggs"], corruptions, levels, payload["rated"]) + [""]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- figures

def plot_set(aggs: dict[str, dict], corruptions: list[str], levels: list[int], out_dir: Path, suffix: str, title: str) -> list[Path]:
    """One figure per metric (metric vs level, a panel per corruption) and the flip-rate heatmap."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    x = [0] + levels
    for key, label, _ in METRICS:
        fig, axes = plt.subplots(2, 5, figsize=(16, 6.2), sharex=True, sharey=True)
        for ax, c in zip(axes.ravel(), corruptions + [None] * (10 - len(corruptions))):
            if c is None:
                ax.axis("off")
                continue
            for m, agg in aggs.items():
                cells = [agg[CLEAN]["0"][key]] + [agg[c][str(lv)][key] for lv in levels]
                if key != "miou":  # the clean image compared with itself
                    cells[0] = {"mean": 1.0 if key == "level_accuracy" else 0.0, "ci_low": float("nan"), "ci_high": float("nan")}
                mean = [v["mean"] for v in cells]
                ax.plot(x, mean, marker="o", ms=4, lw=1.8, color=MODEL_COLOURS.get(m), label=MODEL_LABELS.get(m, m))
                ax.fill_between(x, [v["ci_low"] for v in cells], [v["ci_high"] for v in cells], color=MODEL_COLOURS.get(m), alpha=0.15, lw=0)
            ax.set_title(c.replace("_", " "), fontsize=10)
            ax.grid(alpha=0.3)
            ax.set_xticks(x)
        for ax in axes[-1]:
            ax.set_xlabel("corruption level (0 = clean)")
        for ax in axes[:, 0]:
            ax.set_ylabel(label, fontsize=9)
        axes[0, 0].legend(fontsize=8, loc="best")
        fig.suptitle(f"{title}: {label} (band = bootstrap 95% CI; levels are placeholders)", fontsize=11)
        fig.tight_layout()
        paths.append(out_dir / f"{key}_vs_level{suffix}.png")
        fig.savefig(paths[-1], dpi=130)
        plt.close(fig)

    fig, axes = plt.subplots(1, len(aggs), figsize=(6.2 * len(aggs), 5), squeeze=False)
    for ax, (m, agg) in zip(axes[0], aggs.items()):
        grid = np.array([[agg[c][str(lv)]["flip_rate"]["mean"] for lv in levels] for c in corruptions])
        im = ax.imshow(grid, cmap="viridis", vmin=0, vmax=max(0.5, float(np.nanmax(grid))), aspect="auto")
        ax.set_xticks(range(len(levels)), [str(lv) for lv in levels])
        ax.set_yticks(range(len(corruptions)), [c.replace("_", " ") for c in corruptions])
        ax.set_xlabel("corruption level")
        ax.set_title(MODEL_LABELS.get(m, m), fontsize=10)
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if grid[i, j] < 0.6 * im.get_clim()[1] else "black")
        fig.colorbar(im, ax=ax, fraction=0.046, label="decision flip rate")
    fig.suptitle(f"{title}: decision flip rate vs the clean image (PLACEHOLDER thresholds and levels)", fontsize=11)
    fig.tight_layout()
    paths.append(out_dir / f"flip_rate_heatmap{suffix}.png")
    fig.savefig(paths[-1], dpi=130)
    plt.close(fig)
    return paths


# ----------------------------------------------------------------------------- main

def run_set(entries: list[dict], cache: Path, models: dict, experiment: dict, predictor, conditions, config, image_size, device) -> list[dict]:
    """Process every image not yet in the cache (one JSON line per record), return all records."""
    records = [json.loads(line) for line in cache.read_text(encoding="utf-8").splitlines()] if cache.exists() else []
    n_per_image = 1 + len(conditions)
    counts: dict[str, int] = {}
    for r in records:
        counts[r["name"]] = counts.get(r["name"], 0) + 1
    done = {n for n, c in counts.items() if c == n_per_image}
    records = [r for r in records if r["name"] in done]  # drop an image cut off mid-way
    cache.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    for k, entry in enumerate(entries, 1):
        if entry["name"] in done:
            continue
        new = process_image(entry, models, experiment["click_model"], predictor, conditions, config, image_size, device)
        with cache.open("a", encoding="utf-8") as f:
            f.writelines(json.dumps(r) + "\n" for r in new)
        records += new
        print(f"[{cache.stem}] {k}/{len(entries)} {entry['name']}", flush=True)
    return records


def main() -> None:
    import torch

    from src.models.inference import file_sha256, load_baseline
    from src.severity import leaf_check_tool as lc
    from src.severity.leaf_mask import tuning_rows
    from src.severity.sam2_model import load_sam2_predictor

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase4_benchmark.yaml")
    parser.add_argument("--debug", action="store_true", help="3 test + 3 tuning images, 2 corruptions, 2 levels; never touches gold; outputs only in the experiment folder")
    parser.add_argument("--resume", default=None, help="experiment folder of an interrupted run to continue")
    parser.add_argument("--report-only", default=None, help="experiment folder of a finished run: rebuild the table and figures "
                        "from its records with the current config (levels, mapping, thresholds); no image is processed")
    parser.add_argument("--table", default=None, help="write the table here instead of the default path")
    parser.add_argument("--figures", default=None, help="write the figures here instead of the default folder")
    args = parser.parse_args()
    config = load_config(args.config)
    experiment = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    part = experiment["debug"] if args.debug else experiment
    corruptions, levels = list(part["corruptions"]), list(part["levels"])
    conditions = [(c, lv) for c in corruptions for lv in levels]

    titles = (("Test set (debug: 3 images)", "Tuning images with real clicks (debug stand-in for gold)") if args.debug
              else ("Test set (automatic click)", "Gold cross-check (rater's real clicks)"))
    wanted = list(experiment.get("sets", ["test", "gold"]))
    fig_dir = Path(args.figures) if args.figures else None
    payloads, metrics = {}, {}
    if args.report_only:
        exp_dir = Path(args.report_only)
        fig_dir = fig_dir or FIG_DIR
        for title, suffix, key in zip(titles, ("", "_gold"), ("test", "gold")):
            cache = exp_dir / f"records{suffix or '_test'}.jsonl"
            if not cache.exists():
                continue
            records = [json.loads(line) for line in cache.read_text(encoding="utf-8").splitlines()]
            aggs = {m: aggregate(records, m, config) for m in records[0]["models"]}
            payloads[title] = {"aggs": aggs, "rated": key == "gold"}
            metrics[title] = aggs
            plot_set(aggs, corruptions, levels, fig_dir, suffix, title)
        (exp_dir / "metrics_rereport.json").write_text(json.dumps(metrics, indent=1), encoding="utf-8")
    else:
        method = config["severity_method"]
        if not method.get("frozen"):
            raise RuntimeError("The severity method is not frozen in the config.")
        if method["model"] in experiment["models"] and file_sha256(experiment["models"][method["model"]]) != method["checkpoint_sha256"]:
            raise RuntimeError("The benchmark's checkpoint for the frozen method's model does not match the frozen SHA-256.")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        models = {m: load_baseline(experiment.get("architectures", {}).get(m, m), ckpt, device) for m, ckpt in experiment["models"].items()}
        predictor = load_sam2_predictor(config)
        if args.debug:
            sets = {"test": (test_entries(config)[:3], False), "gold": (rated_entries(tuning_rows(config)[:3], config), True)}
        else:
            sets = {"test": (test_entries(config), False)}
            if "gold" in wanted:
                sets["gold"] = (rated_entries(lc.evaluated_gold_rows(config), config), True)
        exp_dir = Path(args.resume) if args.resume else create_experiment_dir(
            experiment.get("name", "phase4_benchmark") + ("_debug" if args.debug else ""), args.config)
        shutil.copy(args.experiment, exp_dir / Path(args.experiment).name)
        fig_dir = fig_dir or (exp_dir / "figures" if args.debug else FIG_DIR)
        for title, suffix, key in zip(titles, ("", "_gold"), ("test", "gold")):
            if key not in sets or key not in wanted:
                continue
            entries, rated = sets[key]
            records = run_set(entries, exp_dir / f"records{suffix or '_test'}.jsonl", models, experiment, predictor, conditions,
                              config, config["image"]["size"], device)
            aggs = {m: aggregate(records, m, config) for m in models}
            payloads[title] = {"aggs": aggs, "rated": rated}
            metrics[title] = aggs
            plot_set(aggs, corruptions, levels, fig_dir, suffix, title)
    if not args.report_only:
        (exp_dir / "metrics.json").write_text(json.dumps(metrics, indent=1), encoding="utf-8")
    report = format_report(payloads, corruptions, levels, config, experiment, get_git_commit_hash())
    out = Path(args.table) if args.table else (exp_dir / TABLE.name if args.debug else TABLE)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Wrote {out}; figures in {fig_dir}; {exp_dir}")


if __name__ == "__main__":
    main()
