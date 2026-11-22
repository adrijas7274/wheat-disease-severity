"""Phase 5 v2 (POST HOC): one colour-stage variant per refinement group, with guards.

Decided after Phase 7 showed that the Phase 5 v1 stage suppresses the necrotic rule. v1 stays as reported.
Rules: `configs/experiments/phase5_v2.yaml` (committed and tagged `phase5-v2-prereg` before any v2 result).

1. Guard inputs: per-group tuning leave-one-out MAE for every variant (12 tuning images, GPU) and the false
   severity of every variant and group on the healthy guard set (Bangladesh originals, GPU).
2. Per group: guards G1-G3, then selection on the validation split from the saved Phase 5 v1 records
   (per-variant severities of every val image and condition).
3. One evaluation on test, pooled and per disease, v2 against v1 and `none` (from the saved records).

Usage:
    python -m src.severity.phase5_v2 --config configs/config.yaml \
        --experiment configs/experiments/phase5_v2.yaml [--resume experiments/<dir>] [--debug]
"""

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import yaml

from src.corruptions import benchmark as bm
from src.severity import colour_preprocess as cp
from src.severity import phase5_colour_stage as p5
from src.severity import refinement as rf
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

TABLE = Path("report/tables/phase5_v2.md")
DISEASES = list(rf.DISEASE_GROUPS)
V1_SELECTED = "denoise+shades_of_gray+exposure"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


# ----------------------------------------------------------------------------- guard inputs (GPU)

def per_group_loo(items: list[dict], variants: dict, grid: dict) -> dict:
    """{variant: {group: leave-one-out MAE on that group's tuning images}} (same rules as Phase 5 v1)."""
    from src.severity import tune_refinement as tr

    out = {}
    for name, steps in variants.items():
        records = tr.make_records([dict(i, image=cp.apply(i["image"], steps)) for i in items], grid)
        preds = tr.leave_one_out(records, grid, "B")
        out[name] = {g: float(np.mean([abs(p - r["rating"]) for p, r in zip(preds, records) if r["group"] == g]))
                     if any(r["group"] == g for r in records) else float("nan") for g in rf.GROUPS}
    return out


def healthy_entries(root: Path, must_contain: list[str]) -> list[Path]:
    """Photos whose folder path (lower case) contains every substring."""
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES
                  and all(s in "/".join(p.relative_to(root).parts[:-1]).lower() for s in must_contain))


def healthy_record(image: np.ndarray, model, predictor, config: dict, variants: dict, thresholds: dict, device) -> dict:
    """False severity of every variant and group on one healthy photo (automatic click, SAM 2 leaf)."""
    from src.corruptions.cache import model_outputs
    from src.severity.auto_click import click_from_region
    from src.severity.leaf_mask import leaf_from_click

    out = model_outputs(model, image, np.zeros(image.shape[:2], bool), config["image"]["size"], device)
    click = click_from_region(out["region_small"], image.shape)
    predictor.set_image(image)
    leaf = leaf_from_click(predictor, click, config)
    region = out["masks"]["region"] & leaf
    sev = {}
    for v, steps in variants.items():
        pre = cp.apply(image, steps)
        sev[v] = {g: rf.severity_pct(rf.refine_c1(region, pre, g, thresholds[v][g]), leaf) for g in rf.GROUPS}
    return {"click": list(click), "leaf_share": float(leaf.mean()), "severity": sev}


# ----------------------------------------------------------------------------- guards and selection (pure)

def healthy_stats(records: list[dict], variant: str, group: str, above: float) -> dict:
    v = np.array([r["severity"][variant][group] for r in records], dtype=float)
    v = v[np.isfinite(v)]
    return {"n": int(len(v)), "median": float(np.median(v)) if len(v) else float("nan"),
            "share_above": float((v > above).mean()) if len(v) else float("nan"), "zero": float((v == 0).mean()) if len(v) else float("nan")}


def clean_zero_rate(records: list[dict], key: str, disease: str) -> float:
    v = [r["models"][key]["severity"] for r in records if r["corruption"] == "clean" and r["disease"] == disease]
    v = [x for x in v if x is not None and np.isfinite(x)]
    return float(np.mean([x == 0 for x in v])) if v else float("nan")


def subset_summary(records: list[dict], key: str, config: dict, diseases: list[str]) -> dict:
    recs = [r for r in records if r["disease"] in diseases]
    return p5.summarise(bm.aggregate(recs, key, config), recs, key)


def select_group(group: str, variants: list[str], val: list[dict], loo: dict, healthy: list[dict], exp: dict,
                 config: dict, model: str = "segformer", baseline: str = "none") -> dict:
    """Guards G1-G3 and the selection rule of the YAML for one group."""
    g_cfg = exp["guards"]
    diseases = [d for d in DISEASES if rf.DISEASE_GROUPS[d] == group]
    base_h = healthy_stats(healthy, baseline, group, g_cfg["healthy_share_above"])
    base_zero = {d: clean_zero_rate(val, f"{model}|{baseline}", d) for d in diseases}
    rows = {}
    for v in variants:
        key = f"{model}|{v}"
        zero = {d: clean_zero_rate(val, key, d) for d in diseases}
        h = healthy_stats(healthy, v, group, g_cfg["healthy_share_above"])
        s = subset_summary(val, key, config, diseases)
        rows[v] = {"loo": loo[v][group], "zero_rate": zero, "healthy": h, "val_shift": s["mean_shift"], "val_flip": s["mean_flip"],
                   # written so that nan (a group without tuning images, only in --debug) never fails
                   "g1": not (loo[v][group] > loo[baseline][group] + g_cfg["tuning_loo_limit"]),
                   # a disease without val images cannot fail G2; comparisons written so that nan never fails
                   "g2": not any(zero[d] > base_zero[d] for d in diseases),
                   "g3": not (h["median"] > base_h["median"] or h["share_above"] > base_h["share_above"])}
        rows[v]["passes"] = rows[v]["g1"] and rows[v]["g2"] and rows[v]["g3"]
    passing = [v for v in variants if rows[v]["passes"]]
    best = min(passing, key=lambda v: (round(rows[v]["val_shift"], 6), round(rows[v]["val_flip"], 6)))
    replaces = best != baseline and rows[best]["val_shift"] < rows[baseline]["val_shift"] and rows[best]["val_flip"] <= rows[baseline]["val_flip"]
    return {"rows": rows, "passing": passing, "best_passing": best, "selected": best if replaces else baseline, "replaces_baseline": replaces}


def add_stage(records: list[dict], per_group: dict[str, str], name: str, model: str = "segformer") -> list[dict]:
    """Copy of the records with a combined model entry `name` taking each disease's group variant."""
    out = []
    for r in records:
        v = per_group[rf.DISEASE_GROUPS[r["disease"]]]
        out.append(dict(r, models=dict(r["models"], **{name: r["models"][f"{model}|{v}"]})))
    return out


def stage_table(records: list[dict], stages: dict[str, str], config: dict) -> dict:
    """{stage: {"pooled": summary, disease: summary + zero rate}} on one split."""
    out = {}
    for label, key in stages.items():
        out[label] = {"pooled": p5.summarise(bm.aggregate(records, key, config), records, key)}
        for d in DISEASES:
            out[label][d] = dict(subset_summary(records, key, config, [d]), zero_rate=clean_zero_rate(records, key, d),
                                 n=len({r["name"] for r in records if r["disease"] == d}))
    return out


# ----------------------------------------------------------------------------- report

def _p(x: float) -> str:
    return "-" if x is None or not np.isfinite(x) else f"{100 * x:.0f}%"


def format_report(res: dict, exp: dict, commit: str) -> str:
    sel = res["selection"]
    lines = [f"# Phase 5 v2 (POST HOC): per-group colour stage ({date.today().isoformat()})", "",
             f"Commit at run time: `{commit}`; rules tagged `phase5-v2-prereg` before this run. Generated by `python -m src.severity.phase5_v2`.", "",
             "**Post hoc**: decided after Phase 7 showed that the v1 stage (`denoise+shades_of_gray+exposure` for every disease) suppresses the "
             "necrotic rule. v1 is reported unchanged in `report/tables/phase5_colour_stage.md`. Selection used only the tuning images, the "
             "validation split and the healthy guard set (Bangladesh, Mendeley 5gc7hwydwg, original healthy photos, "
             f"n = {res['healthy_n']}). Test was evaluated once, afterwards. Gold not used. Flip rates use the PLACEHOLDER levels and mapping; "
             "corruption levels are placeholders.", "",
             "**Selected per group:** " + "; ".join(f"{g}: `{s['selected']}` (threshold {res['stage'][g]['threshold']:g})" for g, s in sel.items()) + ".", ""]
    for g, s in sel.items():
        diseases = [d for d in DISEASES if rf.DISEASE_GROUPS[d] == g]
        lines += [f"## Group `{g}`: guards and selection (validation)", "",
                  "G1 = tuning leave-one-out MAE within 3.64 of `none`; G2 = clean val zero rate not above `none` for "
                  + ", ".join(diseases) + "; G3 = healthy median and share above 5% not above `none`.", "",
                  "| variant | tuning LOO MAE | " + " | ".join(f"zero rate, {d}" for d in diseases)
                  + " | healthy median % | healthy > 5% | val shift | val flip | G1 | G2 | G3 |",
                  "|---|---:|" + "---:|" * len(diseases) + "---:|---:|---:|---:|:-:|:-:|:-:|"]
        for v, r in sorted(s["rows"].items(), key=lambda kv: (not kv[1]["passes"], kv[1]["val_shift"])):
            mark = " **(selected)**" if v == s["selected"] else ""
            lines.append(f"| `{v}`{mark} | {r['loo']:.2f} | " + " | ".join(_p(r["zero_rate"][d]) for d in diseases)
                         + f" | {r['healthy']['median']:.2f} | {_p(r['healthy']['share_above'])} | {r['val_shift']:.2f} | {r['val_flip']:.2f} | "
                         + " | ".join("yes" if r[k] else "no" for k in ("g1", "g2", "g3")) + " |")
        lines.append("")

    def per_disease(split: str) -> list[str]:
        t = res[split]
        out = [f"## Per disease, {split} split", "",
               "| disease | n | stage | clean zero rate | mean shift, points | mean flip rate | flip at 3% | flip at 5% | flip at 10% | flip at 20% |",
               "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
        for d in DISEASES + ["pooled"]:
            for label in t:
                s = t[label][d]
                zr = _p(s["zero_rate"]) if d != "pooled" else _p(s["clean_zero_share"])
                n = s.get("n", "")
                out.append(f"| {d} | {n} | {label} | {zr} | {s['mean_shift']:.2f} | {s['mean_flip']:.2f} | "
                           + " | ".join(f"{s.get(f'mean_flip_at_{th}', float('nan')):.2f}" for th in (3, 5, 10, 20)) + " |")
        return out + [""]

    lines += per_disease("test") + per_disease("val")
    lines += ["## Healthy guard set: false severity per group (Bangladesh originals)", "",
              "| group | stage | median % | share > 5% | share exactly 0% |", "|---|---|---:|---:|---:|"]
    for g in rf.GROUPS:
        for label, v in (("none", "none"), ("v1", V1_SELECTED), ("v2", res["stage"][g]["variant"])):
            h = res["healthy"][g][v]
            lines.append(f"| {g} | {label} (`{v}`) | {h['median']:.2f} | {_p(h['share_above'])} | {_p(h['zero'])} |")
    lines += ["", "## Test, v2: severity shift (points) and flip rate by corruption and level (pooled)", ""]
    lines += bm._matrix(res["test_agg_v2"], "severity_shift", "{:.1f}", p5.BENCH, p5.LEVELS) + [""]
    lines += bm._matrix(res["test_agg_v2"], "flip_rate", "{:.2f}", p5.BENCH, p5.LEVELS, with_ci=True) + [""]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- main

def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase5_v2.yaml")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--debug", action="store_true", help="3 tuning images, 3 healthy photos, outputs only in the experiment folder")
    args = parser.parse_args()
    config = load_config(args.config)
    exp = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    v1_exp = yaml.safe_load(Path(exp["phase5_v1_experiment"]).read_text(encoding="utf-8"))
    variants, grid = v1_exp["variants"], v1_exp["c1_grid"]
    v1_run = Path(exp["phase5_v1_run"])
    tuning = json.loads((v1_run / "tuning.json").read_text(encoding="utf-8"))
    thresholds = {v: {g: (t["thresholds"][g] if t["thresholds"][g] is not None else grid[g][0]) for g in rf.GROUPS} for v, t in tuning.items()}
    exp_dir = Path(args.resume) if args.resume else create_experiment_dir("phase5_v2" + ("_debug" if args.debug else ""), args.config)
    shutil.copy(args.experiment, exp_dir / Path(args.experiment).name)

    import torch
    from PIL import Image

    from src.external.phase7 import cap_long_side
    from src.models.inference import load_baseline
    from src.severity.sam2_model import load_sam2_predictor

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    spec = v1_exp["models"][exp["model"]]
    model, predictor = None, None

    def load():
        nonlocal model, predictor
        if model is None:
            model, predictor = load_baseline(spec["architecture"], spec["checkpoint"], device), load_sam2_predictor(config)

    loo_file = exp_dir / "tuning_per_group.json"
    if loo_file.exists():
        loo = json.loads(loo_file.read_text(encoding="utf-8"))
    else:
        from src.severity import severity_pipeline as sp
        from src.severity.leaf_mask import tuning_rows

        load()
        rows = tuning_rows(config)[:3] if args.debug else tuning_rows(config)
        items = sp.load_inputs(rows, config, predictor, model, config["image"]["size"], device)
        loo = per_group_loo(items, variants, grid)
        loo_file.write_text(json.dumps(loo, indent=1), encoding="utf-8")

    hs = exp["healthy_set"]
    paths = healthy_entries(Path(hs["dir"]), hs["path_must_contain"])
    paths = paths[:3] if args.debug else paths
    if not paths:
        raise SystemExit(f"No healthy photos under {hs['dir']} matching {hs['path_must_contain']}")
    h_file = exp_dir / "records_healthy.jsonl"
    healthy = _read(h_file) if h_file.exists() else []
    done = {r["name"] for r in healthy}
    for k, p in enumerate(paths, 1):
        name = p.relative_to(hs["dir"]).as_posix()
        if name in done:
            continue
        load()
        image = cap_long_side(np.array(Image.open(p).convert("RGB")), hs["max_long_side"])
        rec = {"name": name} | healthy_record(image, model, predictor, config, variants, thresholds, device)
        with h_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        healthy.append(rec)
        print(f"[healthy] {k}/{len(paths)} {name}", flush=True)
    del model, predictor

    tag = "-".join(v1_exp["models"])
    val, test = _read(v1_run / f"records_val_{tag}.jsonl"), _read(v1_run / f"records_test_{tag}.jsonl")
    if args.debug:  # 3 val and 2 test images per disease
        def few(recs: list[dict], k: int) -> list[dict]:
            names = {d: sorted({r["name"] for r in recs if r["disease"] == d})[:k] for d in DISEASES}
            keep = {n for v in names.values() for n in v}
            return [r for r in recs if r["name"] in keep]

        val = few(val, 3)
        test = val  # --debug never reads test results: the single test evaluation is the real run
    selection = {g: select_group(g, list(variants), val, loo, healthy, exp, config) for g in rf.GROUPS}
    stage = {g: {"variant": s["selected"], "steps": variants[s["selected"]], "threshold": thresholds[s["selected"]][g]} for g, s in selection.items()}
    (exp_dir / "colour_stage_v2.json").write_text(json.dumps(stage, indent=1), encoding="utf-8")

    v2_map, v1_map = {g: stage[g]["variant"] for g in rf.GROUPS}, {g: V1_SELECTED for g in rf.GROUPS}
    stages = {"none": "segformer|none", "v1": "segformer|v1", "v2": "segformer|v2"}

    def prepared(recs: list[dict]) -> list[dict]:
        return add_stage(add_stage(recs, v1_map, "segformer|v1"), v2_map, "segformer|v2")

    val_p, test_p = prepared(val), prepared(test)
    res = {"selection": selection, "stage": stage, "healthy_n": len(healthy),
           "healthy": {g: {v: healthy_stats(healthy, v, g, exp["guards"]["healthy_share_above"]) for v in variants} for g in rf.GROUPS},
           "val": stage_table(val_p, stages, config), "test": stage_table(test_p, stages, config),
           "test_agg_v2": bm.aggregate(test_p, "segformer|v2", config)}
    (exp_dir / "metrics.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    report = format_report(res, exp, get_git_commit_hash())
    out = exp_dir / TABLE.name if args.debug else TABLE
    out.write_text(report, encoding="utf-8")
    print("Selected: " + ", ".join(f"{g}={s['variant']}" for g, s in stage.items()) + f". Wrote {out}; {exp_dir}")


if __name__ == "__main__":
    main()
