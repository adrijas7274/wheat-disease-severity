"""Phase 3 step 3: tune the C1 lesion refinement on the tuning images and apply the C0 fallback rule.

Only tuning images are read here (`leaf_mask.tuning_rows`). Nothing in this
script can load a gold image.

Per `docs/phase3_plan.md` section 4:
- one threshold per disease group, from the grid in the experiment YAML (written
  before any result was looked at);
- objective: severity MAE against the tuning ratings, on the input named by
  `tune_on` in the YAML; ties go to the value listed first;
- leave-one-out error is reported to show how stable the choice is;
- **fallback rule:** C1 is used only if it beats C0 on tuning MAE by more than
  the resolution limit (3.64 points). Otherwise C0 is the method.

Usage:
    python -m src.severity.tune_refinement --config configs/config.yaml \
        --experiment configs/experiments/phase3_refinement.yaml [--debug]
"""

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import yaml

from src.severity import severity_pipeline as sp
from src.severity.leaf_mask import tuning_rows
from src.severity.metrics import bootstrap_ci
from src.severity.refinement import GROUPS
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

TABLE = Path("report/tables/refinement_tuning.md")


def make_records(items: list[dict], grid: dict[str, list[float]]) -> list[dict]:
    """Per image: rating, group, severity of A, B, C0 on each, and C1 on each input at every grid value."""
    records = []
    for item in items:
        rec = {"name": item["name"], "disease": item["disease"], "group": item["group"], "rating": item["rating"],
               "sev": sp.base_severities(item),
               "c1": {key: {t: sp.c1_severity(item, key, t) for t in grid[item["group"]]} for key in sp.INPUTS}}
        records.append(rec)
    return records


def choose_thresholds(records: list[dict], grid: dict[str, list[float]], key: str) -> dict[str, float | None]:
    """Per group, the grid value with the lowest MAE on input `key` (first listed wins ties; None if the group has no image)."""
    out: dict[str, float | None] = {}
    for group in GROUPS:
        recs = [r for r in records if r["group"] == group]
        scores = [sp.mae([r["c1"][key][t] for r in recs], [r["rating"] for r in recs]) for t in grid[group]]
        out[group] = grid[group][int(np.argmin(scores))] if recs else None
    return out


def c1_predictions(records: list[dict], thresholds: dict[str, float | None], key: str) -> list[float]:
    return [r["c1"][key][thresholds[r["group"]]] for r in records]


def leave_one_out(records: list[dict], grid: dict[str, list[float]], key: str) -> list[float]:
    """C1 severity of each image on input `key`, with its group's threshold chosen without that image.
    If the image is the only one of its group, the first grid value is used."""
    preds = []
    for i, rec in enumerate(records):
        others = [r for j, r in enumerate(records) if j != i]
        t = choose_thresholds(others, grid, key)[rec["group"]]
        preds.append(rec["c1"][key][grid[rec["group"]][0] if t is None else t])
    return preds


def apply_fallback(mae_c0: float, mae_c1: float, resolution_limit: float) -> str:
    """'C1' only if it beats C0 by more than the resolution limit, else 'C0'."""
    return "C1" if (mae_c0 - mae_c1) > resolution_limit else "C0"


def tune(records: list[dict], grid: dict[str, list[float]], key: str, resolution_limit: float) -> dict:
    """Everything the tuning report needs, from the per-image records."""
    ratings = [r["rating"] for r in records]
    thresholds = choose_thresholds(records, grid, key)

    def summary(pred: list[float]) -> dict:
        m, lo, hi = bootstrap_ci(np.abs(np.asarray(pred) - np.asarray(ratings)).tolist())
        return {"mae": m, "ci_low": lo, "ci_high": hi, "mean_signed_error": float(np.mean(np.asarray(pred) - np.asarray(ratings)))}

    methods = {name: summary([r["sev"][name] for r in records]) for name in ("A", "B", "C0(A)", "C0(B)")}
    for k in sp.INPUTS:
        methods[f"C1({k})"] = summary(c1_predictions(records, thresholds, k))
    loo = summary(leave_one_out(records, grid, key))
    grid_mae = {g: {str(t): sp.mae([r["c1"][key][t] for r in records if r["group"] == g],
                                   [r["rating"] for r in records if r["group"] == g]) for t in grid[g]} for g in GROUPS}
    gain = methods[f"C0({key})"]["mae"] - methods[f"C1({key})"]["mae"]
    return {
        "n_images": len(records), "tune_on": key, "resolution_limit": resolution_limit, "thresholds": thresholds,
        "n_per_group": {g: sum(r["group"] == g for r in records) for g in GROUPS},
        "grid_mae": grid_mae, "methods": methods, "c1_leave_one_out": loo,
        "c1_gain_over_c0": gain, "c1_gain_over_c0_leave_one_out": methods[f"C0({key})"]["mae"] - loo["mae"],
        "chosen_method": apply_fallback(methods[f"C0({key})"]["mae"], methods[f"C1({key})"]["mae"], resolution_limit),
    }


def format_report(result: dict, records: list[dict], experiment: dict, commit: str) -> str:
    key = result["tune_on"]
    lines = [
        f"# Refinement tuning on the tuning set ({date.today().isoformat()})", "",
        f"Commit at run time: `{commit}`. Generated by `python -m src.severity.tune_refinement`.", "",
        f"{result['n_images']} tuning images (rust {result['n_per_group']['rust']}, necrotic "
        f"{result['n_per_group']['necrotic']}, mildew {result['n_per_group']['mildew']}). Leaf: SAM 2 with the frozen rule. "
        f"B uses `{experiment['model']}` (`{experiment['checkpoint']}`). Thresholds were tuned on input **{key}**. "
        "Severity is in % of leaf area; MAE is against the single rater's tuning ratings.", "",
        f"**Resolution limit: {result['resolution_limit']} points** (rater test-retest). Differences smaller than this are not "
        "distinguishable.", "",
        "## Tuning MAE by method", "",
        "| method | MAE (bootstrap 95% CI) | mean signed error (method minus rating) |", "|---|---|---:|"]
    for name, m in result["methods"].items():
        lines.append(f"| {name} | {m['mae']:.2f} ({m['ci_low']:.2f}-{m['ci_high']:.2f}) | {m['mean_signed_error']:+.2f} |")
    loo = result["c1_leave_one_out"]
    lines += [f"| C1({key}), leave-one-out | {loo['mae']:.2f} ({loo['ci_low']:.2f}-{loo['ci_high']:.2f}) | {loo['mean_signed_error']:+.2f} |", "",
              "C1 rows without \"leave-one-out\" are in-sample: the thresholds were chosen on these same images.", "",
              f"## C1 grid: MAE on input {key}, per disease group", ""]
    for g in GROUPS:
        cells = " | ".join(f"{t}: {v:.2f}" for t, v in result["grid_mae"][g].items())
        lines.append(f"- **{g}** (n = {result['n_per_group'][g]}): {cells}. Chosen: **{result['thresholds'][g]}**")
    lines += ["", "## Fallback rule", "",
              f"C1 beats C0 on input {key} by **{result['c1_gain_over_c0']:.2f} points** in-sample "
              f"({result['c1_gain_over_c0_leave_one_out']:.2f} leave-one-out). The rule needs more than "
              f"{result['resolution_limit']} points.", "",
              f"**Method chosen: {result['chosen_method']}.**", "",
              "## Per image (severity %)", "",
              f"| image | disease | rating | A | B | C0(A) | C0(B) | C1(A) | C1(B) |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in records:
        t = result["thresholds"][r["group"]]
        lines.append(f"| `{r['name']}` | {r['disease'].replace('wheat ', '')} | {r['rating']:.1f} | "
                     + " | ".join(f"{r['sev'][m]:.1f}" for m in ("A", "B", "C0(A)", "C0(B)"))
                     + f" | {r['c1']['A'][t]:.1f} | {r['c1']['B'][t]:.1f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    import torch

    from src.models.inference import load_baseline
    from src.severity.sam2_model import load_sam2_predictor

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase3_refinement.yaml")
    parser.add_argument("--debug", action="store_true", help="first 3 tuning images, CPU-sized model input, outputs only in the experiment folder")
    args = parser.parse_args()
    config = load_config(args.config)
    experiment = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    grid = experiment["c1_grid"]

    rows = tuning_rows(config)[:3] if args.debug else tuning_rows(config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_baseline(experiment["model"], experiment["checkpoint"], device)
    items = sp.load_inputs(rows, config, load_sam2_predictor(config), model, config["image"]["size"], device)
    records = make_records(items, grid)
    result = tune(records, grid, experiment["tune_on"], experiment["resolution_limit"])

    exp_dir = create_experiment_dir("refinement_tuning" + ("_debug" if args.debug else ""), args.config)
    shutil.copy(args.experiment, exp_dir / Path(args.experiment).name)
    (exp_dir / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (exp_dir / "per_image.json").write_text(json.dumps(
        [{k: v for k, v in r.items()} | {"c1": {k: {str(t): s for t, s in d.items()} for k, d in r["c1"].items()}} for r in records],
        indent=1), encoding="utf-8")
    report = format_report(result, records, experiment, get_git_commit_hash())
    out = exp_dir / TABLE.name if args.debug else TABLE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out}; {exp_dir}")


if __name__ == "__main__":
    main()
