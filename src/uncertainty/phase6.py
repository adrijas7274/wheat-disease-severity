"""Phase 6: quality gate, uncertainty and abstention, evaluated with risk-coverage curves.

For every image, corruption and level in the condition cache (`src/corruptions/cache.py`) it
computes the severity of the Phase 5 method, the gate features of the (corrupted) photo and four
uncertainty scores. Everything that is fitted (gate ranges, the tiny classifiers, the abstention
thresholds, the choice of the policy's score) is fitted on the **validation** split; the **test**
split is only evaluated. Gold is not used.

Error of an estimate = its distance from the same method's estimate on the clean photo (severity
shift in points; decision flip with the PLACEHOLDER mapping). Test images have no ratings, so the
risk on clean photos is zero by definition; for clean photos only the abstention rate is reported.

Policy: gate fails -> "please retake the photo"; else uncertainty above the threshold ->
"consult an expert"; else answer.

Gate test set (the project plan Phase 6): non-disputed `wide` images of every split plus all `skip`
images, which the segmentation model never trains on. The gate's photo checks cannot see framing,
so a framing check (leaf share of the image, from the automatic click and SAM 2) is reported too.

Usage:
    python -m src.uncertainty.phase6 --config configs/config.yaml \
        --experiment configs/experiments/phase6_abstention.yaml [--resume experiments/<dir>] [--debug]
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
from src.corruptions.corruptions import CORRUPTIONS, N_LEVELS
from src.severity import colour_preprocess as cp
from src.severity import refinement as rf
from src.uncertainty import quality_gate as qg
from src.uncertainty import scores as sc
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

TABLE = Path("report/tables/abstention.md")
FIG_DIR = Path("report/figures/phase6")
BENCH = list(CORRUPTIONS)
LEVELS = list(range(1, N_LEVELS + 1))
RAW_SCORES = ("entropy", "tta", "photometric", "margin")
SCORE_LABELS = {"entropy": "softmax entropy (region)", "tta": "mirror TTA spread", "photometric": "photometric TTA spread",
                "margin": "threshold margin", "gate_classifier": "tiny classifier: gate features",
                "full_classifier": "tiny classifier: gate features + scores"}


# ----------------------------------------------------------------------------- colour stage

def colour_stage(experiment: dict) -> tuple[dict[str, list[str]], dict[str, float]]:
    """(preprocessing steps per group, threshold per group). `colour_stage` is either one variant for every
    group ({variant, thresholds}) or, from Phase 5 v2 (post hoc), {per_group: {group: {variant, threshold}}}."""
    from src.severity.refinement import GROUPS

    cs = experiment["colour_stage"]
    if "per_group" in cs:
        return ({g: experiment["variants"][cs["per_group"][g]["variant"]] for g in GROUPS},
                {g: cs["per_group"][g]["threshold"] for g in GROUPS})
    return {g: experiment["variants"][cs["variant"]] for g in GROUPS}, dict(cs["thresholds"])


def describe_colour_stage(experiment: dict) -> str:
    cs = experiment["colour_stage"]
    if "per_group" in cs:
        return "per group (Phase 5 v2, post hoc): " + "; ".join(
            f"{g} `{v['variant']}` (threshold {v['threshold']:g})" for g, v in cs["per_group"].items())
    return f"`{cs['variant']}` (thresholds {cs['thresholds']})"


# ----------------------------------------------------------------------------- per-image scoring (worker)

def score_image(job: dict) -> list[dict]:
    """One record per condition of one image: severity, gate features and raw uncertainty scores."""
    from PIL import Image

    cache = ConditionCache(job["cache_dir"], job["split"])
    entry = job["entry"]
    image = np.array(Image.open(entry["image_path"]).convert("RGB"))
    group = rf.DISEASE_GROUPS[entry["disease"]]
    threshold, steps = job["thresholds"][group], job["steps"][group]
    leaf_blob, model_blob = cache.load(entry["name"], "leaf"), cache.load(entry["name"], job["model"])
    records = []
    for i, cond in enumerate(leaf_blob["meta"]["conditions"]):
        img = condition_image(image, (cond[0], cond[1]), job["seed"], entry["name"])
        leaf = cache.mask(leaf_blob, f"leaf_{i}")
        pre = cp.apply(img, steps)

        def severity(region_key: str, picture: np.ndarray) -> float:
            return rf.severity_pct(rf.refine_c1(cache.mask(model_blob, f"{region_key}_{i}") & leaf, picture, group, threshold), leaf)

        sev = severity("region", pre)
        stats = model_blob["meta"]["stats"][i]
        entropy = stats["entropy_region"]
        records.append({
            "name": entry["name"], "disease": entry["disease"], "corruption": cond[0], "level": cond[1],
            "severity": sev, "leaf_share": float(leaf.mean()), "features": qg.features(img),
            "entropy": 0.0 if entropy is None or not np.isfinite(entropy) else entropy,
            "tta": sc.spread([sev, severity("tta_lr", pre), severity("tta_ud", pre)]),
            "photometric": sc.spread([sev] + [severity("region", cp.apply(v, steps)) for v in sc.photometric_views(img)]),
        })
    return records


def score_split(split: str, entries: list[dict], out: Path, job_base: dict, workers: int) -> list[dict]:
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()] if out.exists() else []
    done = {r["name"] for r in records}
    jobs = [dict(job_base, split=split, entry=e) for e in entries if e["name"] not in done]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for k, new in enumerate(pool.map(score_image, jobs), 1):
            with out.open("a", encoding="utf-8") as f:
                f.writelines(json.dumps(r) + "\n" for r in new)
            records += new
            print(f"[{split}] {k}/{len(jobs)} {new[0]['name']}", flush=True)
    return records


# ----------------------------------------------------------------------------- analysis (pure)

def add_errors(records: list[dict], config: dict, unreliable_shift: float) -> list[dict]:
    """Add shift, flip, unreliable (shift above the limit) and the margin score to every record whose
    image has a clean estimate. A missing corrupted estimate counts as a flip and as unreliable."""
    clean = {r["name"]: r["severity"] for r in records if r["corruption"] == "clean"}
    out = []
    for r in records:
        ref = clean.get(r["name"])
        if ref is None or not np.isfinite(ref):
            continue
        sev = r["severity"]
        ok = sev is not None and np.isfinite(sev)
        shift = abs(sev - ref) if ok else float("nan")
        out.append(dict(r, shift=shift, flip=float(bm.decision(sev if ok else float("nan"), config) != bm.decision(ref, config)),
                        unreliable=float((not ok) or shift > unreliable_shift),
                        margin=-sc.threshold_margin(sev, config["severity_thresholds"]) if ok else 0.0))
    return out


def corrupted(records: list[dict]) -> list[dict]:
    """The benchmark pool: the ten corruptions x five levels (no clean photos, no ablation chains)."""
    return [r for r in records if r["corruption"] in CORRUPTIONS]


def _x(records: list[dict], with_scores: bool) -> np.ndarray:
    rows = [qg.feature_vector(r["features"]) + ([r[s] for s in RAW_SCORES] + [r["severity"] if np.isfinite(r["severity"]) else 0.0]
                                                if with_scores else []) for r in records]
    return np.asarray(rows, dtype=float)


def fit_classifier(val_records: list[dict], with_scores: bool, seed: int):
    """Tiny classifier (standardised logistic regression) predicting "this estimate is unreliable"."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=seed))
    model.fit(_x(val_records, with_scores), np.array([r["unreliable"] for r in val_records]))
    return lambda recs: model.predict_proba(_x(recs, with_scores))[:, 1]


def all_scores(records: list[dict], classifiers: dict) -> dict[str, np.ndarray]:
    out = {s: np.array([r[s] for r in records], dtype=float) for s in RAW_SCORES}
    for name, fn in classifiers.items():
        out[name] = fn(records)
    return out


def _risks(records: list[dict]) -> dict[str, np.ndarray]:
    shift = np.array([r["shift"] for r in records], dtype=float)
    return {"shift": np.where(np.isfinite(shift), shift, np.nanmax(shift) if np.isfinite(shift).any() else 0.0),
            "flip": np.array([r["flip"] for r in records], dtype=float)}


def _auroc(score: np.ndarray, label: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(label, score)) if 0 < label.sum() < len(label) else float("nan")


def score_table(records: list[dict], scores: dict[str, np.ndarray], coverages: list[float], n_boot: int, seed: int) -> dict:
    """Per score and risk: AURC and risk at each coverage with a cluster bootstrap CI (images resampled)."""
    if not records:  # nothing to evaluate (e.g. every photo sent back in a --debug run)
        nan = float("nan")
        empty = {"aurc": nan, **{f"at_{c}": {"risk": nan, "ci_low": nan, "ci_high": nan} for c in coverages}}
        return {"n": 0, "n_images": 0, "base": {"shift": nan, "flip": nan},
                "scores": {k: {"auroc_unreliable": nan, "shift": dict(empty), "flip": dict(empty)} for k in list(scores) + ["oracle_shift", "oracle_flip"]}}
    risks = _risks(records)
    names = np.array([r["name"] for r in records])
    groups = [np.nonzero(names == n)[0] for n in sorted(set(names))]
    rng = np.random.default_rng(seed)
    boots = [np.concatenate([groups[g] for g in rng.integers(len(groups), size=len(groups))]) for _ in range(n_boot)]
    unreliable = np.array([r["unreliable"] for r in records])
    table = {"n": len(records), "n_images": len(groups), "base": {k: float(v.mean()) for k, v in risks.items()}, "scores": {}}
    candidates = dict(scores, oracle_shift=risks["shift"], oracle_flip=risks["flip"])
    for name, score in candidates.items():
        row = {"auroc_unreliable": _auroc(score, unreliable)}
        for rk, risk in risks.items():
            row[rk] = {"aurc": sc.aurc(score, risk)}
            for c in coverages:
                vals = [sc.risk_at_coverage(score[b], risk[b], c) for b in boots]
                row[rk][f"at_{c}"] = {"risk": sc.risk_at_coverage(score, risk, c), "ci_low": float(np.percentile(vals, 2.5)),
                                      "ci_high": float(np.percentile(vals, 97.5))}
        table["scores"][name] = row
    return table


def gate_flags(records: list[dict], ranges: dict) -> np.ndarray:
    return np.array([bool(qg.failed_checks(r["features"], ranges)) for r in records])


def policy_thresholds(val_pool: list[dict], val_score: np.ndarray, val_gate: np.ndarray, coverages: list[float]) -> dict[str, float]:
    """Score thresholds set on validation so that gate-passed and score <= threshold keeps the target share."""
    passed = ~val_gate
    out = {}
    for c in coverages:
        q = min(1.0, c / max(float(passed.mean()), 1e-9))
        out[str(c)] = float(np.quantile(val_score[passed], q)) if passed.any() else float("inf")
    return out


def policy_outcome(records: list[dict], score: np.ndarray, gate: np.ndarray, threshold: float) -> dict:
    """Shares of retake / consult / answered, and the risks of the answered estimates and of all estimates."""
    risks = _risks(records) if records and "shift" in records[0] else {}
    retake = gate
    consult = ~gate & (score > threshold)
    answered = ~gate & ~consult
    out = {"n": len(records), "retake": float(retake.mean()), "consult": float(consult.mean()), "answered": float(answered.mean())}
    for rk, risk in risks.items():
        out[f"{rk}_all"] = float(risk.mean())
        out[f"{rk}_answered"] = float(risk[answered].mean()) if answered.any() else float("nan")
        out[f"{rk}_refused"] = float(risk[~answered].mean()) if (~answered).any() else float("nan")
    return out


def gate_matrix(records: list[dict], ranges: dict) -> dict:
    """Retake rate per corruption and level, and the share of each failed check over the corrupted pool."""
    out: dict = {"rate": {}, "reasons": {}}
    for c in BENCH:
        out["rate"][c] = {}
        for lv in LEVELS:
            recs = [r for r in records if r["corruption"] == c and r["level"] == lv]
            out["rate"][c][str(lv)] = float(gate_flags(recs, ranges).mean()) if recs else float("nan")
        recs = [r for r in records if r["corruption"] == c]
        fails = [qg.failed_checks(r["features"], ranges) for r in recs]
        out["reasons"][c] = {k: float(np.mean([k in f for f in fails])) for k in ranges}
    return out


def gate_coverage(records: list[dict], ranges: dict, refused: np.ndarray | None = None) -> dict:
    """Does the gate catch the estimates that moved? Per corruption (all levels) and per level:
    share of unreliable estimates, the gate's catch rate among them (recall), its retake rate among
    the reliable ones, and the mean shift of the photos that pass / fail. `refused` (optional) =
    refused by the full policy (retake or consult), for the catch rate of the whole policy."""
    gate = gate_flags(records, ranges)
    bad = np.array([r["unreliable"] for r in records], dtype=bool)
    shift = _risks(records)["shift"] if records else np.zeros(0)
    corr = np.array([r["corruption"] for r in records])
    level = np.array([r["level"] for r in records])

    def cell(sel: np.ndarray) -> dict:
        def mean(values: np.ndarray, mask: np.ndarray) -> float:
            return float(values[mask].mean()) if mask.any() else float("nan")

        out = {"n": int(sel.sum()), "unreliable": mean(bad.astype(float), sel), "retake": mean(gate.astype(float), sel),
               "caught": mean(gate.astype(float), sel & bad), "false_retake": mean(gate.astype(float), sel & ~bad),
               "shift_passed": mean(shift, sel & ~gate), "shift_failed": mean(shift, sel & gate)}
        if refused is not None:
            out["policy_caught"] = mean(refused.astype(float), sel & bad)
            out["policy_refused"] = mean(refused.astype(float), sel)
            out["shift_answered"] = mean(shift, sel & ~refused)
        return out

    return {c: {"all": cell(corr == c), **{str(lv): cell((corr == c) & (level == lv)) for lv in LEVELS}} for c in BENCH}


# ----------------------------------------------------------------------------- gate set (wide / skip images)

def gate_set_rows(config: dict) -> dict[str, list[dict]]:
    """Metadata rows of the gate test set: non-disputed wide, skip, and (separately) disputed wide."""
    from src.data.wheat_metadata import filter_by_crop_and_disease, load_metadata_rows
    from src.data.wheat_tags import load_disputed, load_tags

    plantseg_dir = Path(config["data"]["plantseg_dir"])
    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
    tags, disputed = load_tags(tags_csv), load_disputed(tags_csv)
    rows = filter_by_crop_and_disease(load_metadata_rows(plantseg_dir / "Metadata.csv"), config["crop"], config["disease_classes"])
    out: dict[str, list[dict]] = {"wide (non-disputed)": [], "skip": [], "wide (disputed)": []}
    for r in sorted(rows, key=lambda r: r["name"]):
        tag, d = tags.get(r["name"]), bool(disputed.get(r["name"], False))
        if tag == "wide":
            out["wide (disputed)" if d else "wide (non-disputed)"].append(r)
        elif tag == "skip":
            out["skip"].append(r)
    return out


def gate_set_features(config: dict, experiment: dict) -> dict[str, list[dict]]:
    """Gate features and leaf share (automatic click + SAM 2) of every gate-set image. Needs the GPU."""
    import torch
    from PIL import Image

    from src.data.wheat_metadata import image_path
    from src.models.inference import load_baseline, predict_region
    from src.severity.auto_click import click_from_region
    from src.severity.leaf_mask import leaf_from_click
    from src.severity.sam2_model import load_sam2_predictor

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    spec = experiment["models"][experiment["model"]]
    model, predictor = load_baseline(spec["architecture"], spec["checkpoint"], device), load_sam2_predictor(config)
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    out = {}
    for group, rows in gate_set_rows(config).items():
        out[group] = []
        for r in rows:
            image = np.array(Image.open(image_path(plantseg_dir, r)).convert("RGB"))
            predictor.set_image(image)
            click = click_from_region(predict_region(model, image, config["image"]["size"], device), image.shape)
            out[group].append({"name": r["name"], "features": qg.features(image),
                               "leaf_share": float(leaf_from_click(predictor, click, config).mean())})
    return out


# ----------------------------------------------------------------------------- report

def _pct(x: float) -> str:
    return "-" if x is None or not np.isfinite(x) else f"{100 * x:.0f}%"


def format_report(res: dict, experiment: dict, config: dict, commit: str) -> str:
    cov = experiment["coverages"]
    t = res["test_table"]
    lines = [
        f"# Phase 6: quality gate, uncertainty and abstention ({date.today().isoformat()})", "",
        f"Commit at run time: `{commit}`. Generated by `python -m src.uncertainty.phase6`.", "",
        f"Method: SegFormer-B0 region, SAM 2 leaf, colour stage {describe_colour_stage(experiment)}. "
        f"Everything fitted here was fitted on the validation split "
        f"({res['n_val_images']} images); the numbers below are on the test split ({t['n_images']} images, "
        f"{t['n']} corrupted estimates: ten corruptions x five levels). Gold was not used.", "",
        "**Error = distance from the same method's estimate on the clean photo** (severity shift in points; decision flip with "
        "the PLACEHOLDER levels and mapping). It measures stability, not correctness: the method itself is about 14 points from "
        "the gold ratings. Corruption levels are placeholders.", "",
        "## Risk-coverage on corrupted test photos", "",
        f"Without abstention (coverage 100%): severity shift {t['base']['shift']:.2f} points, flip rate {t['base']['flip']:.2f}. "
        "Lower is better everywhere. AURC = mean risk over all coverages. The oracle rows order the estimates by their true error "
        "and are the best any score could do.", "",
        "| score | AUROC for \"shift > 3.64\" | shift AURC | " + " | ".join(f"shift at {int(100 * c)}% coverage (95% CI)" for c in cov)
        + " | flip AURC | " + " | ".join(f"flip rate at {int(100 * c)}% coverage (95% CI)" for c in cov) + " |",
        "|---|---:|---:|" + "---|" * len(cov) + "---:|" + "---|" * len(cov)]

    def cells(row: dict, rk: str, fmt: str) -> str:
        return " | ".join(f"{fmt.format(row[rk][f'at_{c}']['risk'])} ({fmt.format(row[rk][f'at_{c}']['ci_low'])}-"
                          f"{fmt.format(row[rk][f'at_{c}']['ci_high'])})" for c in cov)

    for name, row in t["scores"].items():
        label = SCORE_LABELS.get(name, name.replace("_", " "))
        mark = " **(policy score)**" if name == res["policy_score"] else ""
        lines.append(f"| {label}{mark} | {row['auroc_unreliable']:.2f} | {row['shift']['aurc']:.2f} | {cells(row, 'shift', '{:.2f}')} | "
                     f"{row['flip']['aurc']:.3f} | {cells(row, 'flip', '{:.2f}')} |")
    lines += ["", f"The policy score (`{res['policy_score']}`) was chosen on validation (lowest shift AURC there).", "",
              "## Error reduction at fixed coverage (policy score, test)", "",
              "| coverage | severity shift, points | reduction | flip rate | reduction |", "|---:|---|---:|---|---:|"]
    row = t["scores"][res["policy_score"]]
    for c in cov:
        s, f = row["shift"][f"at_{c}"], row["flip"][f"at_{c}"]
        lines.append(f"| {int(100 * c)}% | {s['risk']:.2f} ({s['ci_low']:.2f}-{s['ci_high']:.2f}) | {_pct(1 - s['risk'] / t['base']['shift'])} | "
                     f"{f['risk']:.2f} ({f['ci_low']:.2f}-{f['ci_high']:.2f}) | {_pct(1 - f['risk'] / t['base']['flip'])} |")
    lines.append(f"| 100% | {t['base']['shift']:.2f} | - | {t['base']['flip']:.2f} | - |")

    lines += ["", "## Full policy: gate, then uncertainty (thresholds from validation)", "",
              "\"Retake\" = the gate failed; \"consult\" = the gate passed and the policy score is above the threshold. "
              "Risks of clean photos are zero by definition, so only the shares are shown for them.", "",
              "| target coverage | photos | retake | consult an expert | answered | shift: answered / refused / all | flip: answered / refused / all |",
              "|---:|---|---:|---:|---:|---|---|"]
    for c in cov:
        for pool in ("corrupted", "clean"):
            o = res["policy"][str(c)][pool]
            risks = (f"{o['shift_answered']:.2f} / {o['shift_refused']:.2f} / {o['shift_all']:.2f} | "
                     f"{o['flip_answered']:.2f} / {o['flip_refused']:.2f} / {o['flip_all']:.2f}") if pool == "corrupted" else "- | -"
            lines.append(f"| {int(100 * c)}% | test, {pool} (n = {o['n']}) | {_pct(o['retake'])} | {_pct(o['consult'])} | {_pct(o['answered'])} | {risks} |")

    g = res["gate"]
    lines += ["", "## Quality gate alone", "",
              f"Allowed ranges = the {experiment['gate_tail_pct']}th percentile on each bad side of the clean validation photos: "
              + "; ".join(f"{k} [{'-' if lo is None else f'{lo:.3g}'}, {'-' if hi is None else f'{hi:.3g}'}]" for k, (lo, hi) in g["ranges"].items()) + ".", "",
              f"Clean photos sent back for a retake: validation {_pct(g['clean_val'])}, test {_pct(g['clean_test'])}. "
              f"Corrupted test photos: {_pct(g['corrupted_test'])}; their mean shift is {g['shift_failed']:.2f} points when the gate "
              f"fails and {g['shift_passed']:.2f} when it passes.", "",
              "Retake rate by corruption and level (test):", "",
              "| corruption | " + " | ".join(f"level {lv}" for lv in LEVELS) + " | most frequent failed check |", "|---|" + "---:|" * len(LEVELS) + "---|"]
    for c in BENCH:
        reasons = g["matrix"]["reasons"][c]
        top = max(reasons, key=reasons.get)
        lines.append(f"| {c} | " + " | ".join(_pct(g["matrix"]["rate"][c][str(lv)]) for lv in LEVELS)
                     + f" | {qg.REASONS.get(top, top)} ({_pct(reasons[top])}) |")

    cv = g["coverage"]
    pc = int(100 * float(cv["policy_coverage"]))
    lines += ["", "## Does the gate catch the estimates that moved?", "",
              f"\"Unreliable\" = the estimate is more than {experiment['unreliable_shift']} points from the clean-photo estimate. "
              "Catch rate = share of the unreliable estimates that the gate sends back for a retake. The last two columns add the "
              f"uncertainty step (full policy at the {pc}% target coverage: retake or consult). All levels pooled, test.", "",
              "| corruption | unreliable | gate catch rate | retake rate among reliable | shift: gate passes / fails | "
              f"policy catch rate ({pc}%) | shift of answered ({pc}%) |", "|---|---:|---:|---:|---|---:|---:|"]

    def num(x: float) -> str:
        return "-" if x is None or not np.isfinite(x) else f"{x:.2f}"

    for c in BENCH:
        o = cv["cells"][c]["all"]
        lines.append(f"| {c} | {_pct(o['unreliable'])} | {_pct(o['caught'])} | {_pct(o['false_retake'])} | "
                     f"{num(o['shift_passed'])} / {num(o['shift_failed'])} | {_pct(o['policy_caught'])} | {num(o['shift_answered'])} |")
    lines += ["", "Gate catch rate among the unreliable estimates, by level (share of estimates that are unreliable in brackets):", "",
              "| corruption | " + " | ".join(f"level {lv}" for lv in LEVELS) + " |", "|---|" + "---|" * len(LEVELS)]
    for c in BENCH:
        lines.append(f"| {c} | " + " | ".join(f"{_pct(cv['cells'][c][str(lv)]['caught'])} ({_pct(cv['cells'][c][str(lv)]['unreliable'])})"
                                               for lv in LEVELS) + " |")

    gs = res["gate_set"]
    lines += ["", "## Gate test set: `wide` and `skip` images", "",
              "These images are never used to train the segmentation model. All `wide` images of the five diseases are disputed "
              "(the blind inter-rater check disagreed with the tag), so the planned \"non-disputed wide\" set is empty; the disputed "
              "ones are shown in their own row and are not part of the planned set.", "",
              f"Framing check: leaf share of the image below {100 * gs['leaf_share_bound']:.1f}% (the {experiment['gate_tail_pct']}th "
              "percentile of the clean validation close-ups; leaf from the automatic click and SAM 2).", "",
              "| set | n | fails a photo check | fails the framing check | fails either |", "|---|---:|---:|---:|---:|"]
    for name, o in gs["sets"].items():
        lines.append(f"| {name} | {o['n']} | {_pct(o['photo'])} | {_pct(o['framing'])} | {_pct(o['either'])} |")
    lines += ["", f"For comparison, clean test close-ups: photo checks {_pct(g['clean_test'])}, framing check {_pct(gs['clean_test_framing'])}.", ""]
    return "\n".join(lines)


def plot(res: dict, curves: dict, fig_dir: Path, pool_label: str = "corrupted test photos") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir.mkdir(parents=True, exist_ok=True)
    palette = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
    if not curves:  # nothing answered: only the gate figure
        _plot_gate(res, fig_dir, plt)
        return
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, rk, label in zip(axes, ("shift", "flip"), ("severity shift of answered estimates, points", "decision flip rate of answered estimates")):
        names = [n for n in curves if not n.startswith("oracle")]
        for name, colour in zip(names, palette):
            cov, risk = curves[name][rk]
            ax.plot(100 * np.asarray(cov), risk, color=colour, lw=2.4 if name == res["policy_score"] else 1.3, label=SCORE_LABELS.get(name, name))
        cov, risk = curves[f"oracle_{rk}"][rk]
        ax.plot(100 * np.asarray(cov), risk, "k--", lw=1, label="oracle (true error)")
        ax.axhline(res["test_table"]["base"][rk], color="grey", lw=1, ls=":", label="no abstention / random")
        ax.set_xlabel("coverage: share of estimates answered, %")
        ax.set_ylabel(label)
        ax.set_xlim(20, 100)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Risk-coverage on {pool_label} (error = distance from the clean-photo estimate; placeholder levels)", fontsize=10)
    fig.tight_layout()
    fig.savefig(fig_dir / "risk_coverage.png", dpi=130)
    plt.close(fig)

    _plot_gate(res, fig_dir, plt)


def _plot_gate(res: dict, fig_dir: Path, plt) -> None:
    grid = np.array([[res["gate"]["matrix"]["rate"][c][str(lv)] for lv in LEVELS] for c in BENCH])
    fig, ax = plt.subplots(figsize=(6.5, 5))
    im = ax.imshow(grid, cmap="viridis", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(LEVELS)), [str(lv) for lv in LEVELS])
    ax.set_yticks(range(len(BENCH)), [c.replace("_", " ") for c in BENCH])
    ax.set_xlabel("corruption level")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center", fontsize=8, color="white" if grid[i, j] < 0.6 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046, label="share sent back for a retake")
    ax.set_title(f"Quality gate: retake rate on corrupted test photos{res.get('gate_title_suffix', '')}", fontsize=10)
    fig.tight_layout()
    fig.savefig(fig_dir / "gate_retake_rate.png", dpi=130)
    plt.close(fig)


# ----------------------------------------------------------------------------- main

def analyse(val: list[dict], test: list[dict], gate_set: dict, experiment: dict, config: dict) -> tuple[dict, dict]:
    """Fit on validation, evaluate on test. Returns (results, risk-coverage curves)."""
    limit, cov, seed = experiment["unreliable_shift"], experiment["coverages"], config["seed"]
    val, test = add_errors(val, config, limit), add_errors(test, config, limit)
    val_pool, test_pool = corrupted(val), corrupted(test)
    val_clean = [r for r in val if r["corruption"] == "clean"]
    test_clean = [r for r in test if r["corruption"] == "clean"]
    ranges = qg.fit_ranges([r["features"] for r in val_clean], experiment["gate_tail_pct"])
    fit_on = val_pool + val_clean
    classifiers = {"gate_classifier": fit_classifier(fit_on, False, seed), "full_classifier": fit_classifier(fit_on, True, seed)}

    val_scores, test_scores = all_scores(val_pool, classifiers), all_scores(test_pool, classifiers)
    val_risk = _risks(val_pool)["shift"]
    policy_score = min(val_scores, key=lambda s: sc.aurc(val_scores[s], val_risk))
    table = score_table(test_pool, test_scores, cov, experiment["n_bootstrap"], seed)
    risks = _risks(test_pool)
    curves = {name: {rk: [list(map(float, a)) for a in sc.risk_coverage(score, risks[rk])] for rk in risks}
              for name, score in dict(test_scores, oracle_shift=risks["shift"], oracle_flip=risks["flip"]).items()}

    val_gate, test_gate = gate_flags(val_pool, ranges), gate_flags(test_pool, ranges)
    thresholds = policy_thresholds(val_pool, val_scores[policy_score], val_gate, cov)
    clean_scores = all_scores(test_clean, classifiers)[policy_score]
    clean_gate = gate_flags(test_clean, ranges)
    policy = {c: {"threshold": thr, "corrupted": policy_outcome(test_pool, test_scores[policy_score], test_gate, thr),
                  "clean": policy_outcome([{k: v for k, v in r.items() if k != "shift"} for r in test_clean], clean_scores, clean_gate, thr)}
              for c, thr in thresholds.items()}

    low_cov = str(min(cov))
    refused = test_gate | (test_scores[policy_score] > thresholds[low_cov])
    coverage_by_corruption = {"policy_coverage": low_cov, "cells": gate_coverage(test_pool, ranges, refused)}
    shift = risks["shift"]
    bound =float(np.percentile([r["leaf_share"] for r in val_clean], experiment["gate_tail_pct"]))
    sets = {}
    for name, rows in gate_set.items():
        photo = np.array([bool(qg.failed_checks(r["features"], ranges)) for r in rows], dtype=bool)
        framing = np.array([r["leaf_share"] < bound for r in rows], dtype=bool)
        sets[name] = {"n": len(rows), "photo": float(photo.mean()) if len(rows) else float("nan"),
                      "framing": float(framing.mean()) if len(rows) else float("nan"),
                      "either": float((photo | framing).mean()) if len(rows) else float("nan")}
    res = {
        "n_val_images": len(val_clean), "policy_score": policy_score, "test_table": table, "policy": policy,
        "val_aurc_shift": {s: sc.aurc(v, val_risk) for s, v in val_scores.items()},
        "gate": {"ranges": ranges, "clean_val": float(gate_flags(val_clean, ranges).mean()), "clean_test": float(clean_gate.mean()),
                 "corrupted_test": float(test_gate.mean()),
                 "shift_failed": float(shift[test_gate].mean()) if test_gate.any() else float("nan"),
                 "shift_passed": float(shift[~test_gate].mean()) if (~test_gate).any() else float("nan"),
                 "matrix": gate_matrix(test_pool, ranges), "coverage": coverage_by_corruption},
        "gate_set": {"leaf_share_bound": bound, "sets": sets,
                     "clean_test_framing": float(np.mean([r["leaf_share"] < bound for r in test_clean]))},
    }
    return res, curves


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase6_abstention.yaml")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--debug", action="store_true", help="the debug cache (2 images per split), outputs only in the experiment folder")
    parser.add_argument("--gate-set-from", default=None, help="earlier run whose gate_set.json is reused (photo features only)")
    parser.add_argument("--table", default=None, help="report path (default report/tables/abstention.md)")
    parser.add_argument("--fig-dir", default=None, help="figure folder (default report/figures/phase6)")
    args = parser.parse_args()
    config = load_config(args.config)
    experiment = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    cache_dir = experiment["cache_dir"] + ("_debug" if args.debug else "")
    exp_dir = Path(args.resume) if args.resume else create_experiment_dir("phase6_abstention" + ("_debug" if args.debug else ""), args.config)
    shutil.copy(args.experiment, exp_dir / Path(args.experiment).name)

    gate_file = exp_dir / "gate_set.json"
    if not gate_file.exists() and args.gate_set_from:
        shutil.copy(Path(args.gate_set_from) / "gate_set.json", gate_file)
    if gate_file.exists():
        gate_set = json.loads(gate_file.read_text(encoding="utf-8"))
    else:
        gate_set = gate_set_features(config, experiment)
        gate_file.write_text(json.dumps(gate_set), encoding="utf-8")

    job_base = {"cache_dir": cache_dir, "seed": config["seed"], "model": experiment["model"],
                "steps": colour_stage(experiment)[0], "thresholds": colour_stage(experiment)[1]}
    records = {}
    for split in ("val", "test"):
        cache = ConditionCache(cache_dir, split)
        entries = [e for e in split_entries(config, split) if cache.has(e["name"], "leaf") and cache.has(e["name"], experiment["model"])]
        records[split] = score_split(split, entries, exp_dir / f"records_{split}.jsonl", job_base, args.workers)
    res, curves = analyse(records["val"], records["test"], gate_set, experiment, config)
    (exp_dir / "metrics.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (exp_dir / "curves.json").write_text(json.dumps(curves), encoding="utf-8")
    report = format_report(res, experiment, config, get_git_commit_hash())
    table, fig_dir = Path(args.table) if args.table else TABLE, Path(args.fig_dir) if args.fig_dir else FIG_DIR
    out = exp_dir / table.name if args.debug else table
    out.write_text(report, encoding="utf-8")
    plot(res, curves, exp_dir / "figures" if args.debug else fig_dir)
    print(f"Policy score: {res['policy_score']}. Wrote {out}; {exp_dir}")


if __name__ == "__main__":
    main()
