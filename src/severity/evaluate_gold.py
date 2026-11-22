"""Phase 3 step 4: the single evaluation of the frozen severity method against the gold ratings.

**This is run once.** The method (`severity_method` in the config) is frozen and
tagged before any gold image is scored; there is no re-tuning afterwards. The
script refuses to score gold unless `--gold` is given, the wrong-leaf check is
locked, the model checkpoint matches the frozen SHA-256, and no gold report
exists yet. `--debug` scores 3 **tuning** images instead and writes only to the
experiment folder, so the code path can be tested without touching gold.

Methods, all on the same SAM 2 leaf (`docs/annotation_guidelines.md`, *Evaluation plan*):
    A      PlantSeg's infected-region mask clipped to the leaf
    B      the frozen Phase 2 model's predicted region clipped to the leaf
    C(A)   the frozen refinement applied to A
    C(B)   the frozen refinement applied to B (what the app would run)

Usage:
    python -m src.severity.evaluate_gold --config configs/config.yaml --debug
    python -m src.severity.evaluate_gold --config configs/config.yaml --gold
"""

import argparse
import json
from datetime import date
from pathlib import Path

from src.severity import refinement as rf
from src.severity import severity_pipeline as sp
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

TABLE = Path("report/tables/gold_evaluation.md")
METHODS = ("A", "B", "C(A)", "C(B)")


def check_may_score_gold(config: dict, table: Path, checkpoint_sha256: str) -> None:
    """Raise unless every condition for the single gold run holds."""
    method = config.get("severity_method") or {}
    if not method.get("frozen"):
        raise RuntimeError("The severity method is not frozen in the config.")
    if not config["annotation"].get("leaf_check_locked"):
        raise RuntimeError("The wrong-leaf check is not locked.")
    if checkpoint_sha256 != method["checkpoint_sha256"]:
        raise RuntimeError("The model checkpoint does not match the frozen SHA-256.")
    if table.exists():
        raise RuntimeError(f"{table} exists: gold has already been evaluated. It is evaluated once.")


def method_severities(item: dict, method: dict) -> dict[str, float]:
    """Severity (%) of A, B, C(A), C(B) for one image with the frozen method."""
    out = {}
    for key in sp.INPUTS:
        region = item["regions"][key]
        out[key] = rf.severity_pct(region, item["leaf"])
        if method["refinement"] == "C0":
            lesion = rf.refine_c0(region, item["image"])
        elif method["refinement"] == "C1":
            lesion = rf.refine_c1(region, item["image"], item["group"], method["c1_thresholds"][item["group"]],
                                  halo=(method.get("c1_halo") or {}).get(item["group"], True))
        else:
            raise ValueError(f"Unknown refinement '{method['refinement']}'")
        out[f"C({key})"] = rf.severity_pct(lesion, item["leaf"])
    return out


def evaluate(items: list[dict], config: dict) -> tuple[dict, list[dict]]:
    """(summary per method, per-image rows)."""
    method = config["severity_method"]
    per_image = [{"name": i["name"], "disease": i["disease"], "rating": i["rating"], **method_severities(i, method)} for i in items]
    return summarise(per_image, config), per_image


def summarise(per_image: list[dict], config: dict) -> dict:
    """Evaluation-plan metrics per method for the given per-image rows."""
    ratings, diseases = [r["rating"] for r in per_image], [r["disease"] for r in per_image]
    return {m: sp.error_summary([r[m] for r in per_image], ratings, diseases, config) for m in METHODS}


def _pooled_lines(summary: dict, limit: float) -> list[str]:
    lines = ["| method | MAE, points (bootstrap 95% CI) | mean signed error | resolution limit |", "|---|---|---:|---:|"]
    return lines + [f"| {m} | {s['pooled']['mae']:.2f} ({s['pooled']['ci_low']:.2f}-{s['pooled']['ci_high']:.2f}) | "
                    f"{s['mean_signed_error']:+.2f} | {limit} |" for m, s in summary.items()]


def _group_lines(summary: dict, key: str) -> list[str]:
    groups = list(next(iter(summary.values()))[key])
    lines = ["| group | n | " + " | ".join(METHODS) + " |", "|---|---:|" + "---|" * len(METHODS)]
    for g in groups:
        cells = []
        for m in METHODS:
            v = summary[m][key][g]
            cells.append(f"{v['mae']:.2f} ({v['ci_low']:.2f}-{v['ci_high']:.2f})" if v["n"] else "-")
        lines.append(f"| {g.replace('wheat ', '')} | {summary[METHODS[0]][key][g]['n']} | " + " | ".join(cells) + " |")
    return lines


def _agreement_lines(summary: dict) -> list[str]:
    lines = ["| method | same level | same decision |", "|---|---:|---:|"]
    return lines + [f"| {m} | {100 * s['level_agreement']:.0f}% | {100 * s['decision_agreement']:.0f}% |" for m, s in summary.items()]


def format_report(summary: dict, config: dict, n: int, set_name: str, commit: str, exclusions: str = "",
                  without: dict | None = None) -> str:
    """Markdown report. `without` = {"names", "reason", "n", "summary"}: the same metrics with some images left out."""
    method = config["severity_method"]
    limit = method["resolution_limit"]
    refinement = method["refinement"] + (f", thresholds {method['c1_thresholds']}" if method["refinement"] == "C1" else "")
    t = config["severity_thresholds"]
    limit_note = f"Resolution limit: {limit} points."
    lines = [
        f"# Severity against the {set_name} ratings ({date.today().isoformat()})", "",
        f"Commit at run time: `{commit}`. Generated by `python -m src.severity.evaluate_gold`.", "",
        f"{n} images. Leaf: SAM 2, frozen rule. B: `{method['model']}`. C: {refinement}. "
        "Severity = lesion pixels on leaf / leaf pixels, in %. Ratings come from one rater.", "",
        f"**Resolution limit: {limit} points** (the rater's own test-retest difference). Methods whose MAE differs by less "
        "are not distinguishable at the gold standard's resolution.", "",
        "## Pooled severity MAE (main metric)", ""]
    lines += _pooled_lines(summary, limit)
    for title, key, note in (("Per disease", "per_disease", "Low n per disease, leaf rust lowest."),
                             ("By gold rating band", "by_rating_band", "The medium and high bands are low-n.")):
        lines += ["", f"## {title}", "", f"{note} {limit_note}", ""] + _group_lines(summary, key)
    lines += ["", "## Level and decision agreement (PLACEHOLDER thresholds and mapping)", "",
              f"Levels use the config thresholds ({100 * t['low_max']:g}% and {100 * t['medium_max']:g}%), which are "
              "**placeholders, not validated against an agronomy source**. The same holds for the decision mapping. "
              f"A rating within {limit} points of a threshold can change level from rating noise alone.", ""]
    lines += _agreement_lines(summary)
    lines += ["", "Level confusion (rating level -> method level: count):", ""]
    lines += [f"- {m}: " + "; ".join(f"{a} -> {b}: {c}" for a, row in sorted(s["level_confusion_rating_then_method"].items())
                                     for b, c in sorted(row.items())) for m, s in summary.items()]
    if without:
        names = ", ".join(f"`{x}`" for x in without["names"])
        lines += ["", f"## Sensitivity: without {names} ({without['n']} images)", "", without["reason"], "",
                  f"Pooled MAE. {limit_note}", ""] + _pooled_lines(without["summary"], limit)
        lines += ["", f"By gold rating band. {limit_note}", ""] + _group_lines(without["summary"], "by_rating_band")
        lines += ["", "Per disease.", ""] + _group_lines(without["summary"], "per_disease")
        lines += ["", "Level and decision agreement (PLACEHOLDER thresholds and mapping).", ""] + _agreement_lines(without["summary"])
    if exclusions:
        lines += ["", "## Exclusions", "", exclusions]
    return "\n".join(lines) + "\n"


def main() -> None:
    import torch

    from src.models.inference import file_sha256, load_baseline
    from src.severity import leaf_check_tool as lc
    from src.severity.leaf_mask import tuning_rows
    from src.severity.sam2_model import load_sam2_predictor

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--gold", action="store_true", help="the single gold evaluation")
    mode.add_argument("--debug", action="store_true", help="3 tuning images; never touches gold")
    args = parser.parse_args()
    config = load_config(args.config)
    method = config["severity_method"]
    sha = file_sha256(method["checkpoint"])

    exclusions = ""
    if args.gold:
        check_may_score_gold(config, TABLE, sha)
        rows = lc.evaluated_gold_rows(config)
        checked = lc.checked_rows(config)
        cats = lc.categories(checked, lc.load_verdicts(lc._paths(config)["log"]), config["annotation"].get("gold_exclude_reasons", {}))
        total = lc.count_categories(checked, cats)["total"]
        exclusions = (f"Of the {len(checked)} checked gold images, {total['correct']} are evaluated. Excluded: "
                      f"{total['wrong']} wrong leaf, {total['not_a_leaf']} not a leaf, {total['duplicate']} duplicate, "
                      f"{total['collage']} collage. One more image was excluded before the check (`annotation.gold_exclude`). "
                      "Names and reasons: `report/tables/leaf_check_notes.csv` and the config.")
    else:
        rows = tuning_rows(config)[:3]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_baseline(method["model"], method["checkpoint"], device)
    items = sp.load_inputs(rows, config, load_sam2_predictor(config), model, config["image"]["size"], device)
    summary, per_image = evaluate(items, config)
    without = None
    sens = config["annotation"].get("gold_sensitivity_without") or {}
    left_out = [n for n in sens.get("names", []) if any(r["name"] == n for r in per_image)]
    if left_out:
        kept = [r for r in per_image if r["name"] not in left_out]
        without = {"names": left_out, "reason": sens["reason"], "n": len(kept), "summary": summarise(kept, config)}

    set_name = "gold" if args.gold else "tuning (debug)"
    exp_dir = create_experiment_dir("gold_evaluation" if args.gold else "gold_evaluation_debug", args.config)
    (exp_dir / "metrics.json").write_text(json.dumps({"set": set_name, "n": len(per_image), "checkpoint_sha256": sha,
                                                      "summary": summary,
                                                      "without": without}, indent=2), encoding="utf-8")
    (exp_dir / "per_image.json").write_text(json.dumps(per_image, indent=1), encoding="utf-8")
    report = format_report(summary, config, len(per_image), set_name, get_git_commit_hash(), exclusions, without)
    out = TABLE if args.gold else exp_dir / TABLE.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out}; {exp_dir}")


if __name__ == "__main__":
    main()
