"""Phase 5 (redirected): make the colour stage robust.

Three steps, one command:

1. **Tune.** For every preprocessing variant in the experiment YAML the C1 thresholds are
   re-tuned on the 12 tuning images (same grid and rules as phase3-method-v1), and the
   leave-one-out MAE is recorded. Preprocessing is applied to the image for the colour rule only.
2. **Evaluate.** From the condition cache (`src/corruptions/cache.py`: leaf and region per
   image, corruption and level) the severity of every variant is computed on the val and test
   splits, for every cached model (the Phase 2 SegFormer-B0 and, once trained, the
   corruption-augmented SegFormer-B0 baseline). No GPU is needed for this step.
3. **Report.** Severity shift (primary, threshold-free), decision flip rate and
   single-threshold flip rates per variant; the selection rule of the YAML; the combined-chain
   ablation (noise alone, noise + JPEG, low resolution + noise, full chain); figures.

Gold is not used: only tuning ratings are read (`leaf_mask.tuning_rows`).

Usage:
    python -m src.severity.phase5_colour_stage --config configs/config.yaml \
        --experiment configs/experiments/phase5_colour_stage.yaml [--resume experiments/<dir>] [--debug]
"""

import argparse
import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import yaml

from src.corruptions import benchmark as bm
from src.corruptions.cache import ConditionCache, condition_image, split_entries
from src.corruptions.corruptions import ABLATION_CHAINS, CORRUPTIONS, N_LEVELS
from src.severity import colour_preprocess as cp
from src.severity import refinement as rf
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

TABLE = Path("report/tables/phase5_colour_stage.md")
FIG_DIR = Path("report/figures/phase5")
BENCH = list(CORRUPTIONS)
LEVELS = list(range(1, N_LEVELS + 1))
ABLATION_ROWS = ["sensor_noise", "noise_jpeg", "lowres_noise", "combined"]


# ----------------------------------------------------------------------------- step 1: tuning

def tune_variants(items: list[dict], variants: dict[str, list[str]], grid: dict, limit: float) -> dict:
    """Per variant: thresholds chosen on the tuning images (input B), in-sample and leave-one-out MAE."""
    from src.severity import tune_refinement as tr

    out = {}
    for name, steps in variants.items():
        pre = [dict(i, image=cp.apply(i["image"], steps)) for i in items]
        result = tr.tune(tr.make_records(pre, grid), grid, "B", limit)
        out[name] = {"thresholds": result["thresholds"], "mae_in_sample": result["methods"]["C1(B)"]["mae"],
                     "mae_leave_one_out": result["c1_leave_one_out"]["mae"],
                     "mean_signed_error": result["methods"]["C1(B)"]["mean_signed_error"]}
    return out


# ----------------------------------------------------------------------------- step 2: evaluation from the cache

def variant_severity(image: np.ndarray, leaf: np.ndarray, region: np.ndarray, group: str, steps: list[str], threshold: float) -> float:
    """Severity (%) of C1 with the variant's preprocessing and threshold (nan if the leaf is empty)."""
    return rf.severity_pct(rf.refine_c1(region & leaf, cp.apply(image, steps), group, threshold), leaf)


def evaluate_image(job: dict) -> list[dict]:
    """All records of one image (runs in a worker process). One record per condition, in the shape
    `benchmark.aggregate` expects, with one "model" entry per (model, variant)."""
    from PIL import Image

    cache = ConditionCache(job["cache_dir"], job["split"])
    entry = job["entry"]
    image = np.array(Image.open(entry["image_path"]).convert("RGB"))
    group = rf.DISEASE_GROUPS[entry["disease"]]
    leaf_blob = cache.load(entry["name"], "leaf")
    model_blobs = {m: cache.load(entry["name"], m) for m in job["models"]}
    clean_leaf, records = cache.mask(leaf_blob, "leaf_0"), []
    for i, cond in enumerate(leaf_blob["meta"]["conditions"]):
        img = condition_image(image, (cond[0], cond[1]), job["seed"], entry["name"])
        leaf = cache.mask(leaf_blob, f"leaf_{i}")
        union = leaf | clean_leaf
        pre = {v: cp.apply(img, steps) for v, steps in job["variants"].items()}
        rec = {"name": entry["name"], "disease": entry["disease"], "corruption": cond[0], "level": cond[1],
               "leaf_share": float(leaf.mean()),
               "leaf_iou_vs_clean": float((leaf & clean_leaf).sum() / union.sum()) if union.any() else float("nan"),
               "models": {}}
        for m, blob in model_blobs.items():
            region = cache.mask(blob, f"region_{i}") & leaf
            for v in job["variants"]:
                lesion = rf.refine_c1(region, pre[v], group, job["thresholds"][v][group])
                rec["models"][f"{m}|{v}"] = {"iou": blob["meta"]["stats"][i]["iou"], "severity": rf.severity_pct(lesion, leaf)}
        records.append(rec)
    return records


def evaluate_split(split: str, entries: list[dict], out: Path, job_base: dict, workers: int) -> list[dict]:
    """Records of a split, computed in parallel; images already in `out` are skipped."""
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()] if out.exists() else []
    done = {r["name"] for r in records}
    jobs = [dict(job_base, split=split, entry=e) for e in entries if e["name"] not in done]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for k, new in enumerate(pool.map(evaluate_image, jobs), 1):
            with out.open("a", encoding="utf-8") as f:
                f.writelines(json.dumps(r) + "\n" for r in new)
            records += new
            print(f"[{split}] {k}/{len(jobs)} {new[0]['name']}", flush=True)
    return records


# ----------------------------------------------------------------------------- step 3: summary, selection, report

def summarise(agg: dict, records: list[dict], key: str) -> dict:
    """Means over the 50 benchmark cells for one (model, variant), plus the zero-estimate indicators."""
    cells = [agg[c][str(lv)] for c in BENCH for lv in LEVELS]
    clean = [r["models"][key]["severity"] for r in records if r["corruption"] == "clean"]
    out = {"mean_shift": float(np.mean([c["severity_shift"]["mean"] for c in cells])),
           "mean_flip": float(np.mean([c["flip_rate"]["mean"] for c in cells])),
           "clean_miou": agg["clean"]["0"]["miou"]["mean"],
           "clean_zero_share": float(np.mean([s == 0 for s in clean])), "clean_mean_severity": float(np.nanmean(clean))}
    for t in cells[0].get("flip_at", {}):
        out[f"mean_flip_at_{t}"] = float(np.mean([c["flip_at"][t]["mean"] for c in cells]))
    return out


def select(summary: dict[str, dict], tuning: dict[str, dict], limit: float, baseline: str = "none") -> dict:
    """The YAML's selection rule. `summary` = test summary per variant (one model)."""
    admissible = [v for v in summary if tuning[v]["mae_leave_one_out"] <= tuning[baseline]["mae_leave_one_out"] + limit]
    best = min(admissible, key=lambda v: (round(summary[v]["mean_shift"], 6), round(summary[v]["mean_flip"], 6)))
    replaces = (best != baseline and summary[best]["mean_shift"] < summary[baseline]["mean_shift"]
                and summary[best]["mean_flip"] <= summary[baseline]["mean_flip"])
    return {"admissible": admissible, "best_admissible": best, "selected": best if replaces else baseline, "replaces_baseline": replaces}


def _row(name: str, s: dict, t: dict | None, mark: str = "") -> str:
    ths = " / ".join("-" if t["thresholds"][g] is None else f"{t['thresholds'][g]:g}" for g in ("rust", "necrotic", "mildew")) if t else "-"
    tune = f"{t['mae_leave_one_out']:.2f} | {ths}" if t else "- | -"
    at = " | ".join(f"{s[k]:.2f}" for k in s if k.startswith("mean_flip_at_"))
    return (f"| {name}{mark} | {s['mean_shift']:.2f} | {s['mean_flip']:.2f} | {at} | {tune} | "
            f"{100 * s['clean_zero_share']:.0f}% | {s['clean_mean_severity']:.1f} |")


def format_report(summaries: dict, tuning: dict, selection: dict, aggs: dict, experiment: dict, config: dict, commit: str) -> str:
    """`summaries[split][model][variant]`, `aggs[split]["model|variant"]`."""
    limit = experiment["resolution_limit"]
    ts = [k.replace("mean_flip_at_", "") for k in next(iter(summaries["test"]["segformer"].values())) if k.startswith("mean_flip_at_")]
    head = ("| variant | mean severity shift, points | mean flip rate | " + " | ".join(f"flip at {t}%" for t in ts)
            + " | tuning leave-one-out MAE | thresholds (rust / necrotic / mildew) | clean estimates = 0 | mean clean estimate, % |")
    sep = "|---|---:|---:|" + "---:|" * len(ts) + "---:|---|---:|---:|"
    sel = selection["selected"]
    lines = [
        f"# Phase 5: making the colour stage robust ({date.today().isoformat()})", "",
        f"Commit at run time: `{commit}`. Generated by `python -m src.severity.phase5_colour_stage`.", "",
        "Preprocessing is applied to the image for the colour rule only; the region model and SAM 2 see the photo as it is. "
        "Thresholds are re-tuned per variant on the 12 tuning images. Means are over the 50 corruption x level cells of the "
        "Phase 4 benchmark. **Severity shift (points, against the same method on the clean image) is the primary, "
        "threshold-free metric.** Flip rates use the PLACEHOLDER levels and mapping; corruption levels are placeholders too. "
        "Gold was not used.", "",
        f"**Selection rule** (written before the results): admissible if tuning leave-one-out MAE is at most {limit} points worse "
        "than `none`; among those the lowest mean severity shift on test; it replaces `none` only if its shift is lower and its "
        "flip rate is not higher. The selection uses the test set, so the selected variant's test numbers are optimistic; "
        "the validation split is given as a check.", "",
        f"**Selected: `{sel}`**" + ("" if selection["replaces_baseline"] else " (no variant replaces the baseline)") + ". "
        f"Not admissible: {', '.join(f'`{v}`' for v in tuning if v not in selection['admissible']) or 'none'}.", ""]
    for split in ("test", "val"):
        if split not in summaries:
            continue
        s = summaries[split]["segformer"]
        lines += [f"## SegFormer-B0 regions, {split} split ({aggs[split]['n_images']} images)", "", head, sep]
        for v in sorted(s, key=lambda v: s[v]["mean_shift"]):
            mark = (" **(selected)**" if v == sel else "") + ("" if v in selection["admissible"] else " (not admissible)")
            lines.append(_row(f"`{v}`", s[v], tuning[v], mark))
        lines.append("")
    others = [m for m in summaries["test"] if m != "segformer"]
    if others:
        lines += ["## Corruption-augmented SegFormer-B0 as the region model (test split)", "",
                  "Same colour rule and leaf; only the region model differs. Clean mIoU in brackets.", "",
                  "| region model | colour stage | mean severity shift | mean flip rate | mean mIoU over the 50 cells |", "|---|---|---:|---:|---:|"]
        for m in ["segformer"] + others:
            for v in dict.fromkeys(["none", sel]):
                s, agg = summaries["test"][m][v], aggs["test"][f"{m}|{v}"]
                miou = float(np.mean([agg[c][str(lv)]["miou"]["mean"] for c in BENCH for lv in LEVELS]))
                lines.append(f"| {m} (clean mIoU {s['clean_miou']:.3f}) | `{v}` | {s['mean_shift']:.2f} | {s['mean_flip']:.2f} | {miou:.3f} |")
        lines.append("")
    test = aggs["test"]
    for title, key, fmt in (("Severity shift, points", "severity_shift", "{:.1f}"), ("Decision flip rate", "flip_rate", "{:.2f}")):
        for v in dict.fromkeys(["none", sel]):
            lines += [f"## {title}: SegFormer-B0 regions, colour stage `{v}` (test)", ""]
            lines += bm._matrix(test[f"segformer|{v}"], key, fmt, BENCH, LEVELS, with_ci=key == "flip_rate") + [""]
    lines += ["## Combined-chain ablation (test, SegFormer-B0 regions, colour stage `none`)", "",
              "Does the JPEG step smooth the noise? `noise_jpeg` = sensor noise then JPEG; `lowres_noise` = low resolution then "
              "sensor noise; `combined` = low resolution, sensor noise, JPEG. Same level for every step.", "",
              "**severity shift, points**", ""] + bm._matrix(test["segformer|none"], "severity_shift", "{:.1f}", ABLATION_ROWS, LEVELS)
    lines += ["", "**decision flip rate** (bootstrap 95% CI)", ""] + bm._matrix(test["segformer|none"], "flip_rate", "{:.2f}", ABLATION_ROWS, LEVELS, with_ci=True)
    lines += ["", "**SAM 2 leaf IoU with the clean leaf**", ""] + bm._matrix(test["segformer|none"], "leaf_iou_vs_clean", "{:.2f}", ABLATION_ROWS, LEVELS)
    return "\n".join(lines) + "\n"


def plot(summaries: dict, selection: dict, aggs: dict, fig_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir.mkdir(parents=True, exist_ok=True)
    s = summaries["test"]["segformer"]
    order = sorted(s, key=lambda v: s[v]["mean_shift"])
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, key, label in zip(axes, ("mean_shift", "mean_flip"), ("mean severity shift, points (primary)", "mean decision flip rate (placeholder levels)")):
        colours = ["#0072B2" if v == selection["selected"] else ("#999999" if v in selection["admissible"] else "#DDDDDD") for v in order]
        ax.barh(range(len(order)), [s[v][key] for v in order], color=colours)
        if "val" in summaries:
            ax.plot([summaries["val"]["segformer"][v][key] for v in order], range(len(order)), "k|", ms=12, label="validation split")
            ax.legend(fontsize=8)
        ax.set_yticks(range(len(order)), order, fontsize=8)
        ax.set_xlabel(label)
        ax.grid(axis="x", alpha=0.3)
    axes[0].invert_yaxis()
    fig.suptitle("Phase 5: colour-stage variants on test (blue = selected, light grey = not admissible on tuning)", fontsize=11)
    fig.tight_layout()
    fig.savefig(fig_dir / "variants.png", dpi=130)
    plt.close(fig)
    pair = {v: aggs["test"][f"segformer|{v}"] for v in dict.fromkeys(["none", selection["selected"]])}
    bm.MODEL_LABELS.update({v: f"colour stage: {v}" for v in pair})
    bm.MODEL_COLOURS.update(dict(zip(pair, ("#D55E00", "#0072B2"))))
    bm.plot_set(pair, BENCH, LEVELS, fig_dir, "", "Test, SegFormer-B0 regions")
    abl = {"none": aggs["test"]["segformer|none"]}
    bm.plot_set(abl, ABLATION_ROWS, LEVELS, fig_dir, "_ablation", "Combined-chain ablation (test)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase5_colour_stage.yaml")
    parser.add_argument("--resume", default=None, help="experiment folder to continue (tuning and finished images are reused)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--debug", action="store_true", help="3 tuning images, the debug cache, outputs only in the experiment folder")
    args = parser.parse_args()
    config = load_config(args.config)
    experiment = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    variants, limit = experiment["variants"], experiment["resolution_limit"]
    cache_dir = experiment["cache_dir"] + ("_debug" if args.debug else "")
    exp_dir = Path(args.resume) if args.resume else create_experiment_dir("phase5_colour_stage" + ("_debug" if args.debug else ""), args.config)
    shutil.copy(args.experiment, exp_dir / Path(args.experiment).name)

    tuning_file = exp_dir / "tuning.json"
    if tuning_file.exists():
        tuning = json.loads(tuning_file.read_text(encoding="utf-8"))
    else:
        import torch

        from src.models.inference import load_baseline
        from src.severity import severity_pipeline as sp
        from src.severity.leaf_mask import tuning_rows
        from src.severity.sam2_model import load_sam2_predictor

        rows = tuning_rows(config)[:3] if args.debug else tuning_rows(config)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        spec = experiment["models"]["segformer"]
        model = load_baseline(spec["architecture"], spec["checkpoint"], device)
        items = sp.load_inputs(rows, config, load_sam2_predictor(config), model, config["image"]["size"], device)
        tuning = tune_variants(items, variants, experiment["c1_grid"], limit)
        tuning_file.write_text(json.dumps(tuning, indent=1), encoding="utf-8")
        del model, items
    for v, t in tuning.items():
        print(f"tuning {v}: leave-one-out {t['mae_leave_one_out']:.2f}, thresholds {t['thresholds']}", flush=True)

    job_base = {"cache_dir": cache_dir, "seed": config["seed"], "variants": variants, "models": list(experiment["models"]),
                "thresholds": {v: {g: (t["thresholds"][g] if t["thresholds"][g] is not None else experiment["c1_grid"][g][0])
                                   for g in rf.GROUPS} for v, t in tuning.items()}}
    summaries, aggs = {}, {}
    for split in ("test", "val"):
        cache = ConditionCache(cache_dir, split)
        entries = [e for e in split_entries(config, split) if all(cache.has(e["name"], k) for k in ["leaf"] + job_base["models"])]
        if not entries:
            continue
        tag = "-".join(job_base["models"])
        records = evaluate_split(split, entries, exp_dir / f"records_{split}_{tag}.jsonl", job_base, args.workers)
        aggs[split] = {"n_images": len(entries)}
        summaries[split] = {}
        for m in job_base["models"]:
            summaries[split][m] = {}
            for v in variants:
                key = f"{m}|{v}"
                aggs[split][key] = bm.aggregate(records, key, config)
                summaries[split][m][v] = summarise(aggs[split][key], records, key)
    selection = select(summaries["test"]["segformer"], tuning, limit)
    (exp_dir / "metrics.json").write_text(json.dumps({"tuning": tuning, "selection": selection, "summaries": summaries}, indent=1), encoding="utf-8")
    (exp_dir / "aggregates.json").write_text(json.dumps(aggs), encoding="utf-8")
    report = format_report(summaries, tuning, selection, aggs, experiment, config, get_git_commit_hash())
    out = exp_dir / TABLE.name if args.debug else TABLE
    out.write_text(report, encoding="utf-8")
    plot(summaries, selection, aggs, exp_dir / "figures" if args.debug else FIG_DIR)
    print(f"Selected: {selection['selected']}. Wrote {out}; {exp_dir}")


if __name__ == "__main__":
    main()
