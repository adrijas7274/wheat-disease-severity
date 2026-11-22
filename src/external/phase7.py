"""Phase 7: the final pipeline on external wheat field photos that were never trained or tuned on.

Two sets (PlantDoc has no wheat, see experiments/LOG.md 2026-11-17):

* **Mendeley Wheat Leaf Dataset** (Getachew, 2021, CC BY 4.0; stripe rust, septoria, healthy;
  image-level labels only). The whole final pipeline runs on every photo: SegFormer-B0 region,
  automatic click, SAM 2 leaf, Phase 5 colour stage, Phase 6 v2 gate and policy. Checks:
  healthy leaves (share at about 0%, distribution of false severity), diseased leaves (share
  detected, severity per disease), and the gate retake and consult-expert rates.
* **NWRD** (Sensors 2023; stripe rust, binary masks). Region check only: infected-region IoU of
  SegFormer-B0 against the masks, as in Phase 2.

Severity levels, decisions and the policy's coverage targets use PLACEHOLDER thresholds.

Usage:
    python -m src.external.phase7 --part mendeley|nwrd [--resume experiments/<dir>] [--debug]
"""

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import yaml

from src.severity import colour_preprocess as cp
from src.severity import refinement as rf
from src.uncertainty import quality_gate as qg
from src.uncertainty import scores as sc
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

TABLE_DIR = Path("report/tables")
FIG_DIR = Path("report/figures/phase7")
MENDELEY_SOURCE = ("Held-out field photos from Holeta, Ethiopia (Getachew, 2021, CC BY 4.0, DOI 10.17632/wgd66f8n6h.1), never trained or tuned on. Image-level labels only (stripe rust, septoria, healthy), so these checks cannot measure severity error. ")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


# ----------------------------------------------------------------------------- data

def label_of(rel_path: Path, classes: list[dict]) -> str | None:
    """Class of a photo from its folder path: the first keyword (in config order) found in it."""
    folders = "/".join(rel_path.parts[:-1]).lower()
    for c in classes:
        if c["keyword"] in folders:
            return c["label"]
    return None


def list_mendeley(root: Path, classes: list[dict]) -> tuple[list[dict], dict]:
    """Every photo under `root` with its class; byte-identical copies are kept once (first path in
    sorted order). Returns (entries, counts of skipped files)."""
    import hashlib

    entries, seen, skipped = [], {}, {"no_class": 0, "duplicate": 0}
    for path in sorted(p for p in root.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES):
        rel = path.relative_to(root)
        label = label_of(rel, classes)
        if label is None:
            skipped["no_class"] += 1
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            skipped["duplicate"] += 1
            continue
        seen[digest] = rel.as_posix()
        entries.append({"name": rel.as_posix(), "path": str(path), "label": label})
    return entries, skipped


def cap_long_side(image: np.ndarray, max_long_side: int | None) -> np.ndarray:
    """Downscale (area interpolation) so the long side is at most `max_long_side` px; smaller photos unchanged."""
    import cv2

    h, w = image.shape[:2]
    if not max_long_side or max(h, w) <= max_long_side:
        return image
    scale = max_long_side / max(h, w)
    return cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)


def list_nwrd(root: Path) -> list[dict]:
    """(image, mask) pairs: every `images/<stem>.*` with a `masks/<stem>.*` next to it."""
    pairs = []
    for img in sorted(p for p in root.rglob("*") if p.parent.name.lower() == "images" and p.suffix.lower() in IMAGE_SUFFIXES):
        masks = [m for m in (img.parent.parent / "masks").glob(img.stem + ".*") if m.suffix.lower() in IMAGE_SUFFIXES]
        if masks:
            pairs.append({"name": img.relative_to(root).as_posix(), "image_path": str(img), "mask_path": str(masks[0])})
    return pairs


# ----------------------------------------------------------------------------- the final pipeline on one photo

def score_photo(image: np.ndarray, model, predictor, config: dict, steps: list[str] | dict[str, list[str]], thresholds: dict,
                groups: list[str], device, click: tuple[int, int] | None = None, return_masks: bool = False) -> dict:
    """Gate features, leaf, and per colour-rule group the severity and the uncertainty scores, exactly as
    in Phase 6 (`phase6.score_image`) but on a clean photo with the automatic click.

    click: (x, y) in image pixels to use instead of the automatic click (the demo's tap on the leaf).
    return_masks: also return the leaf, region and per-group lesion masks (for overlays)."""
    from src.corruptions.cache import model_outputs
    from src.severity.auto_click import click_from_region
    from src.severity.leaf_mask import leaf_from_click

    out = model_outputs(model, image, np.zeros(image.shape[:2], bool), config["image"]["size"], device)
    click = click_from_region(out["region_small"], image.shape) if click is None else (int(click[0]), int(click[1]))
    predictor.set_image(image)
    leaf = leaf_from_click(predictor, click, config)
    steps_of = steps if isinstance(steps, dict) else {g: steps for g in groups}
    raw_views = sc.photometric_views(image)
    region = out["masks"]["region"]
    per_group, lesions = {}, {}
    for g in groups:
        pre = cp.apply(image, steps_of[g])
        views = [cp.apply(v, steps_of[g]) for v in raw_views]

        def sev(reg: np.ndarray, picture: np.ndarray) -> float:
            return rf.severity_pct(rf.refine_c1(reg & leaf, picture, g, thresholds[g]), leaf)

        s = sev(region, pre)
        if return_masks:
            lesions[g] = rf.refine_c1(region & leaf, pre, g, thresholds[g]) & leaf
        per_group[g] = {"severity": s, "tta": sc.spread([s, sev(out["masks"]["tta_lr"], pre), sev(out["masks"]["tta_ud"], pre)]),
                        "photometric": sc.spread([s] + [sev(region, v) for v in views])}
    entropy = out["entropy_region"]
    masks = {"masks": {"leaf": leaf, "region": region, "lesion": lesions}} if return_masks else {}
    return masks | {"features": qg.features(image) | {"blockiness": qg.blockiness(image)}, "click": list(click),
            "leaf_share": float(leaf.mean()), "region_share_of_leaf": float((region & leaf).sum() / max(int(leaf.sum()), 1)),
            "entropy": 0.0 if entropy is None or not np.isfinite(entropy) else float(entropy), "groups": per_group}


def policy_record(rec: dict, group: str, severity_thresholds: dict) -> dict:
    """The record shape the Phase 6 classifiers read, for one colour-rule group."""
    g = rec["groups"][group]
    sev = g["severity"]
    ok = sev is not None and np.isfinite(sev)
    return {"features": rec["features"], "entropy": rec["entropy"], "tta": g["tta"], "photometric": g["photometric"],
            "margin": -sc.threshold_margin(sev, severity_thresholds) if ok else 0.0, "severity": sev if ok else float("nan")}


def load_v2_policy(config: dict, exp: dict) -> dict:
    """Gate ranges, policy thresholds and the refitted v2 classifier (deterministic; C checked against the run)."""
    from src.uncertainty import phase6 as p6
    from src.uncertainty import phase6_v2 as v2

    run = Path(exp["phase6_v2_run"])
    v2_exp = yaml.safe_load(Path(exp["phase6_v2_experiment"]).read_text(encoding="utf-8"))
    v1_exp = yaml.safe_load(Path(v2_exp["v1_experiment"]).read_text(encoding="utf-8"))
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    steps, thresholds = p6.colour_stage(v1_exp)
    common = {"ranges": metrics["gate"]["ranges"], "thresholds": metrics["thresholds"], "policy_score": metrics["policy_score"],
              "steps": steps, "colour_thresholds": thresholds, "colour_stage_text": p6.describe_colour_stage(v1_exp)}
    if metrics["policy_score"] in p6.RAW_SCORES:  # a raw uncertainty score chosen by the frozen rule: no classifier
        name = metrics["policy_score"]
        return common | {"predict": lambda recs: np.array([r[name] for r in recs], dtype=float)}
    if metrics["policy_score"] != "full_classifier":
        raise RuntimeError(f"Unsupported policy score {metrics['policy_score']}")
    val_v1 = v2._read(Path(v2_exp["v1_run"]) / "records_val.jsonl")
    block = {(r["name"], r["corruption"], r["level"]): r["blockiness"] for r in v2._read(run / "blockiness_val.jsonl")}
    val = v2.attach_clean(p6.add_errors(v2.with_blockiness(val_v1, block), config, v1_exp["unreliable_shift"]))
    fit_on = p6.corrupted(val) + [r for r in val if r["corruption"] == "clean"]
    predict, info, _ = v2.fit_classifier_cv(fit_on, True, config["seed"], v2_exp["cv_folds"], v2_exp["c_grid"])
    if info["C"] != metrics["cv"]["full_classifier"]["C"]:
        raise RuntimeError("Refitted classifier does not match the v2 run")
    return common | {"predict": predict}


def decide(rec: dict, group: str, policy: dict, config: dict) -> dict:
    """Gate, then uncertainty: 'retake' / 'consult' / 'answer' per coverage target, plus the placeholder level."""
    from src.severity.recheck_report import severity_level

    failed = qg.failed_checks(rec["features"], policy["ranges"])
    score = float(policy["predict"]([policy_record(rec, group, config["severity_thresholds"])])[0])
    sev = rec["groups"][group]["severity"]
    out = {"failed_checks": failed, "score": score,
           "level": severity_level(sev, config["severity_thresholds"]) if sev is not None and np.isfinite(sev) else None}
    for c, thr in policy["thresholds"].items():
        out[f"action_{c}"] = "retake" if failed else ("consult" if score > thr else "answer")
    return out


# ----------------------------------------------------------------------------- summaries (pure)

def describe(values: list[float]) -> dict:
    v = np.array([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if not len(v):
        return {"n": 0}
    q = np.percentile(v, [10, 25, 50, 75, 90])
    return {"n": int(len(v)), "mean": float(v.mean()), "p10": float(q[0]), "p25": float(q[1]), "median": float(q[2]),
            "p75": float(q[3]), "p90": float(q[4]), "max": float(v.max()), "zero": float((v == 0).mean()),
            "le_1": float((v <= 1).mean()), "lt_5": float((v < 5).mean()), "gt_0": float((v > 0).mean())}


def share_ci(flags: list[bool], n_boot: int, seed: int) -> dict:
    from src.severity.metrics import bootstrap_ci

    m, lo, hi = bootstrap_ci([float(f) for f in flags], n_bootstrap=n_boot, seed=seed)
    return {"share": m, "ci_low": lo, "ci_high": hi, "n": len(flags)}


def summarise_mendeley(records: list[dict], healthy_groups: list[str], coverages: list[str], n_boot: int, seed: int) -> dict:
    """Per class (and, for healthy leaves, per colour-rule group): severity distribution, detection or
    zero share with bootstrap CIs, level counts, and the policy's actions."""
    out: dict = {}
    for label in sorted({r["label"] for r in records}):
        recs = [r for r in records if r["label"] == label]
        groups = healthy_groups if label == "healthy" else [rf.DISEASE_GROUPS[label]]
        out[label] = {"n": len(recs), "empty_leaf": int(sum(not np.isfinite(r["groups"][groups[0]]["severity"]) for r in recs)),
                      "leaf_share": describe([r["leaf_share"] for r in recs]), "groups": {}}
        for g in groups:
            sev = [r["groups"][g]["severity"] for r in recs]
            finite = [s for s in sev if s is not None and np.isfinite(s)]
            o = {"severity": describe(sev),
                 "zero": share_ci([s == 0 for s in finite], n_boot, seed), "detected": share_ci([s > 0 for s in finite], n_boot, seed),
                 "le_1": share_ci([s <= 1 for s in finite], n_boot, seed),
                 "levels": {lv: int(sum(r["decision"][g]["level"] == lv for r in recs)) for lv in ("none", "low", "medium", "high")},
                 "actions": {}}
            for c in coverages:
                acts = [r["decision"][g][f"action_{c}"] for r in recs]
                o["actions"][c] = {a: float(np.mean([x == a for x in acts])) for a in ("retake", "consult", "answer")}
                answered = [r["groups"][g]["severity"] for r in recs if r["decision"][g][f"action_{c}"] == "answer"]
                o["actions"][c]["answered_severity"] = describe(answered)
            fails = [r["decision"][g]["failed_checks"] for r in recs]
            o["failed_checks"] = {k: float(np.mean([k in f for f in fails])) for k in sorted({k for f in fails for k in f})}
            out[label]["groups"][g] = o
    return out


def iou_dice(pred: np.ndarray, true: np.ndarray) -> tuple[float, float]:
    from src.severity.metrics import binary_dice, binary_iou

    return binary_iou(pred, true), binary_dice(pred, true)


# ----------------------------------------------------------------------------- report

def _pct(x) -> str:
    return "-" if x is None or not np.isfinite(x) else f"{100 * x:.0f}%"


def _ci(o: dict) -> str:
    return f"{_pct(o['share'])} ({_pct(o['ci_low'])}-{_pct(o['ci_high'])})"


def _dist(d: dict) -> str:
    if not d.get("n"):
        return "-"
    return f"{d['median']:.1f} ({d['p25']:.1f}-{d['p75']:.1f}) | {d['p90']:.1f} | {d['max']:.1f}"


def format_mendeley(summary: dict, skipped: dict, coverages: list[str], commit: str,
                    stage_text: str = "Phase 5 colour stage (`denoise+shades_of_gray+exposure`)", note: str = "",
                    title_suffix: str = "", dataset: str = "the Mendeley Wheat Leaf Dataset", source: str | None = None) -> str:
    source = source if source is not None else MENDELEY_SOURCE
    lines = [f"# Phase 7: final pipeline on {dataset}{title_suffix} ({date.today().isoformat()})", "",
             *([f"**{note}**", ""] if note else []),
             f"Commit at run time: `{commit}`. Generated by `python -m src.external.phase7 --part mendeley`.", "",
             source + "Pipeline: SegFormer-B0 region, "
             f"automatic click, SAM 2 leaf, colour stage {stage_text}, Phase 6 v2 gate and policy (post hoc). "
             "Levels, decisions and coverage targets use PLACEHOLDER thresholds. For healthy leaves every colour rule is shown, because a healthy "
             "leaf has no disease to choose one. Every photo was downscaled to a long side of at most 2048 px before the pipeline "
             "(decided for memory and runtime, before any full-run result).", "",
             f"Files skipped: {skipped.get('no_class', 0)} without a class folder, {skipped.get('duplicate', 0)} byte-identical copies.", "",
             "## Severity", "",
             "| class | colour rule | n | exactly 0% (95% CI) | at most 1% (95% CI) | detected, > 0% (95% CI) | severity %: median (IQR) | p90 | max | levels none / low / medium / high |",
             "|---|---|---:|---|---|---|---|---:|---:|---|"]
    for label, o in summary.items():
        for g, s in o["groups"].items():
            lv = s["levels"]
            lines.append(f"| {label} | {g} | {s['severity'].get('n', 0)} | {_ci(s['zero'])} | {_ci(s['le_1'])} | {_ci(s['detected'])} | "
                         f"{_dist(s['severity'])} | {lv['none']} / {lv['low']} / {lv['medium']} / {lv['high']} |")
    lines += ["", "Empty leaf masks (no estimate): " + ", ".join(f"{k} {o['empty_leaf']}" for k, o in summary.items()) + ".", "",
              "## Gate and policy on these clean photos", "",
              "| class | colour rule | target coverage | retake | consult an expert | answered | answered severity: median (IQR) | p90 | max |",
              "|---|---|---:|---:|---:|---:|---|---:|---:|"]
    for label, o in summary.items():
        for g, s in o["groups"].items():
            for c in coverages:
                a = s["actions"][c]
                lines.append(f"| {label} | {g} | {int(100 * float(c))}% | {_pct(a['retake'])} | {_pct(a['consult'])} | {_pct(a['answer'])} | "
                             f"{_dist(a['answered_severity'])} |")
    lines += ["", "Failed gate checks (share of photos):", "", "| class | " + "check | share |", "|---|---|---:|"]
    for label, o in summary.items():
        g = next(iter(o["groups"]))
        for k, v in o["groups"][g]["failed_checks"].items():
            lines.append(f"| {label} | {qg.REASONS.get(k, k)} (`{k}`) | {_pct(v)} |")
    lines += ["", "Leaf share of the photo (SAM 2 leaf from the automatic click): "
              + "; ".join(f"{k} median {o['leaf_share']['median']:.2f} (IQR {o['leaf_share']['p25']:.2f}-{o['leaf_share']['p75']:.2f})"
                          for k, o in summary.items() if o["leaf_share"].get("n")) + ".", ""]
    return "\n".join(lines)


def format_nwrd(summary: dict, commit: str) -> str:
    return "\n".join([
        f"# Phase 7: SegFormer-B0 infected region on NWRD ({date.today().isoformat()})", "",
        f"Commit at run time: `{commit}`. Generated by `python -m src.external.phase7 --part nwrd`.", "",
        "NWRD (Sensors 2023): stripe rust field photos with binary rust masks, never trained or tuned on. Region check only: IoU of the "
        "predicted infected region against the NWRD masks (mask > 0 = rust), in the model's 512 px padded space as in Phase 2. NWRD masks "
        "mark rust pixels, while PlantSeg masks (what the model learnt) are coarse infected regions, so a low IoU partly reflects the "
        "different annotation style.", "",
        f"| n images | IoU (95% CI) | Dice (95% CI) | predicted region share | mask share |", "|---:|---|---|---:|---:|",
        f"| {summary['n']} | {summary['iou']['mean']:.3f} ({summary['iou']['ci_low']:.3f}-{summary['iou']['ci_high']:.3f}) | "
        f"{summary['dice']['mean']:.3f} ({summary['dice']['ci_low']:.3f}-{summary['dice']['ci_high']:.3f}) | "
        f"{summary['pred_share']:.3f} | {summary['true_share']:.3f} |", "",
        "For reference, the same model's test IoU on PlantSeg is 0.658.", ""])


def plot_mendeley(records: list[dict], healthy_groups: list[str], fig_dir: Path, dataset: str = "Mendeley Wheat Leaf Dataset") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir.mkdir(parents=True, exist_ok=True)
    panels = [("healthy", g) for g in healthy_groups] + [(lab, rf.DISEASE_GROUPS[lab]) for lab in sorted({r["label"] for r in records}) if lab != "healthy"]
    fig, axes = plt.subplots(1, len(panels), figsize=(3.6 * len(panels), 3.4), sharey=False)
    bins = np.arange(0, 102, 2)
    for ax, (label, g) in zip(np.atleast_1d(axes), panels):
        v = [r["groups"][g]["severity"] for r in records if r["label"] == label]
        v = [x for x in v if x is not None and np.isfinite(x)]
        ax.hist(v, bins=bins, color="#0072B2" if label != "healthy" else "#D55E00")
        for t in (5, 20):
            ax.axvline(t, color="grey", lw=0.8, ls=":")
        ax.set_title(f"{label}\n(colour rule: {g}, n = {len(v)})", fontsize=9)
        ax.set_xlabel("estimated severity, %")
    np.atleast_1d(axes)[0].set_ylabel("photos")
    fig.suptitle(f"{dataset}: estimated severity (dotted: placeholder 5% and 20%)", fontsize=10)
    fig.tight_layout()
    fig.savefig(fig_dir / "mendeley_severity.png", dpi=130)
    plt.close(fig)


def save_overlay(image: np.ndarray, leaf: np.ndarray, lesion: np.ndarray, click: list[int], title: str, path: Path) -> None:
    import cv2

    scale = 768 / max(image.shape[:2])
    size = (round(image.shape[1] * scale), round(image.shape[0] * scale))
    img = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    les = cv2.resize(lesion.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
    lf = cv2.resize(leaf.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST)
    out = img.copy()
    out[les] = (0.5 * out[les] + 0.5 * np.array([255, 0, 255])).astype(np.uint8)
    contours, _ = cv2.findContours(lf, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, (0, 255, 255), 2)
    cv2.drawMarker(out, (round(click[0] * scale), round(click[1] * scale)), (255, 255, 255), cv2.MARKER_CROSS, 18, 2)
    cv2.putText(out, title, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(out, cv2.COLOR_RGB2BGR))


# ----------------------------------------------------------------------------- main

def run_mendeley(config: dict, exp: dict, exp_dir: Path, debug: bool) -> None:
    import torch
    from PIL import Image

    from src.models.inference import load_baseline
    from src.severity.sam2_model import load_sam2_predictor

    m = exp["mendeley"]
    entries, skipped = list_mendeley(Path(m["dir"]), m["classes"])
    if debug:  # one photo per class
        entries = [next(e for e in entries if e["label"] == lab) for lab in sorted({e["label"] for e in entries})]
    policy = load_v2_policy(config, exp)
    steps, thresholds = policy["steps"], policy["colour_thresholds"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_baseline(exp["model"]["architecture"], exp["model"]["checkpoint"], device)
    predictor = load_sam2_predictor(config)

    out = exp_dir / "records_mendeley.jsonl"
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()] if out.exists() else []
    done = {r["name"] for r in records}
    overlays: dict[str, int] = {}
    fig_dir = (exp_dir / "figures") if debug else Path(exp.get("fig_dir", FIG_DIR))
    for k, e in enumerate(entries, 1):
        if e["name"] in done:
            continue
        image = np.array(Image.open(e["path"]).convert("RGB"))
        original_shape = list(image.shape[:2])
        image = cap_long_side(image, m.get("max_long_side"))
        groups = m["healthy_groups"] if e["label"] == "healthy" else [rf.DISEASE_GROUPS[e["label"]]]
        rec = {"name": e["name"], "label": e["label"], "original_shape": original_shape, "shape": list(image.shape[:2])}
        rec |= score_photo(image, model, predictor, config, steps, thresholds, groups, device)
        rec["decision"] = {g: decide(rec, g, policy, config) for g in groups}
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        records.append(rec)
        if overlays.get(e["label"], 0) < m["n_overlays_per_class"]:
            from src.corruptions.cache import model_outputs
            from src.severity.leaf_mask import leaf_from_click

            o = model_outputs(model, image, np.zeros(image.shape[:2], bool), config["image"]["size"], device)
            predictor.set_image(image)
            leaf = leaf_from_click(predictor, tuple(rec["click"]), config)
            g = groups[0]
            lesion = rf.refine_c1(o["masks"]["region"] & leaf, cp.apply(image, steps[g]), g, thresholds[g])
            title = f"{e['label']} | {g} | {rec['groups'][g]['severity']:.1f}% | {rec['decision'][g]['action_0.8']}"
            save_overlay(image, leaf, lesion, rec["click"], title, fig_dir / "overlays" / f"{e['label'].replace(' ', '_')}_{overlays.get(e['label'], 0)}.jpg")
            overlays[e["label"]] = overlays.get(e["label"], 0) + 1
        print(f"[mendeley] {k}/{len(entries)} {e['name']}", flush=True)

    coverages = list(policy["thresholds"])
    summary = summarise_mendeley(records, m["healthy_groups"], coverages, exp["n_bootstrap"], config["seed"])
    (exp_dir / "metrics_mendeley.json").write_text(json.dumps({"skipped": skipped, "summary": summary}, indent=1), encoding="utf-8")
    report = format_mendeley(summary, skipped, coverages, get_git_commit_hash(), policy["colour_stage_text"], exp.get("note", ""),
                             exp.get("title_suffix", ""), exp.get("dataset", "the Mendeley Wheat Leaf Dataset"), exp.get("source"))
    table = (exp_dir if debug else TABLE_DIR) / exp.get("table_name", "phase7_mendeley.md")
    table.write_text(report, encoding="utf-8")
    plot_mendeley(records, m["healthy_groups"], fig_dir, exp.get("dataset_plot", "Mendeley Wheat Leaf Dataset"))
    print(f"Wrote {table}; {exp_dir}")


def run_nwrd(config: dict, exp: dict, exp_dir: Path, debug: bool) -> None:
    import torch
    from PIL import Image

    from src.corruptions.cache import model_outputs
    from src.models.inference import load_baseline, resize_mask
    from src.severity.metrics import bootstrap_ci

    pairs = list_nwrd(Path(exp["nwrd"]["dir"]))
    if not pairs:
        raise SystemExit(f"No NWRD image/mask pairs under {exp['nwrd']['dir']}")
    pairs = pairs[:3] if debug else pairs
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_baseline(exp["model"]["architecture"], exp["model"]["checkpoint"], device)
    rows = []
    for k, p in enumerate(pairs, 1):
        image = np.array(Image.open(p["image_path"]).convert("RGB"))
        mask = np.array(Image.open(p["mask_path"]).convert("L")) > 0
        if mask.shape != image.shape[:2]:
            mask = resize_mask(mask, image.shape)
        o = model_outputs(model, image, mask, config["image"]["size"], device)
        region = o["masks"]["region"]
        _, dice = iou_dice(region, mask)
        rows.append({"name": p["name"], "iou": o["iou"], "dice_full_res": dice, "pred_share": float(region.mean()), "true_share": float(mask.mean())})
        print(f"[nwrd] {k}/{len(pairs)} {p['name']}", flush=True)
    (exp_dir / "records_nwrd.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def ci(v: list[float]) -> dict:
        m_, lo, hi = bootstrap_ci(v, n_bootstrap=exp["n_bootstrap"], seed=config["seed"])
        return {"mean": m_, "ci_low": lo, "ci_high": hi}

    summary = {"n": len(rows), "iou": ci([r["iou"] for r in rows]), "dice": ci([r["dice_full_res"] for r in rows]),
               "pred_share": float(np.mean([r["pred_share"] for r in rows])), "true_share": float(np.mean([r["true_share"] for r in rows]))}
    (exp_dir / "metrics_nwrd.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    table = (exp_dir if debug else TABLE_DIR) / "phase7_nwrd.md"
    table.write_text(format_nwrd(summary, get_git_commit_hash()), encoding="utf-8")
    print(f"Wrote {table}; {exp_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase7_external.yaml")
    parser.add_argument("--part", choices=["mendeley", "nwrd"], required=True)
    parser.add_argument("--resume", default=None)
    parser.add_argument("--debug", action="store_true", help="one photo per class (Mendeley) or 3 pairs (NWRD); outputs only in the experiment folder")
    args = parser.parse_args()
    config = load_config(args.config)
    exp = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    name = f"phase7_{args.part}" + ("_debug" if args.debug else "")
    exp_dir = Path(args.resume) if args.resume else create_experiment_dir(name, args.config)
    shutil.copy(args.experiment, exp_dir / Path(args.experiment).name)
    (run_mendeley if args.part == "mendeley" else run_nwrd)(config, exp, exp_dir, args.debug)


if __name__ == "__main__":
    main()
