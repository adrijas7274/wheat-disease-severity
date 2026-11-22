"""Phase 6 v2: POST HOC revision of the quality gate and the abstention policy (Adrija, 2026-11-17).

v1 (`src/uncertainty/phase6.py`, tag `phase6-v1`) is the pre-registered result and stays as it is.
This round was decided after the v1 test results were seen, so it is labelled post hoc everywhere.
Its rules (`configs/experiments/phase6_v2.yaml`) and this code are committed and tagged
`phase6-v2-prereg` before the single test evaluation. Everything is fitted on validation.

Changes against v1:
1. Gate: one overall false-retake target (5%) on clean validation photos, split evenly across the
   check sides; the fixed 224 px minimum side becomes a fitted check inside that budget.
2. A JPEG blockiness check.
3. Coverage targets are measured among gate-passed photos, so "consult an expert" can fire.
4. The tiny classifiers are tuned and the policy score is chosen with grouped cross-validation
   inside validation (out-of-fold scores).
5. Reporting: catch rates per corruption and level, clean-photo retake rate, and flip rates at
   single thresholds (0, 3, 5, 10, 20%) for v1 and v2.

The per-image records of the v1 run (severity, features, uncertainty scores) are reused; only the
blockiness of every (deterministic) corrupted image is computed here.

Usage:
    python -m src.uncertainty.phase6_v2 --config configs/config.yaml \
        --experiment configs/experiments/phase6_v2.yaml [--resume experiments/<dir>] [--debug]
"""

import argparse
import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import yaml

from src.corruptions.cache import condition_image
from src.uncertainty import phase6 as p6
from src.uncertainty import quality_gate as qg
from src.uncertainty import scores as sc
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

TABLE = Path("report/tables/abstention_v2.md")
FIG_DIR = Path("report/figures/phase6_v2")


# ----------------------------------------------------------------------------- blockiness of every condition (worker)

def blockiness_image(job: dict) -> list[dict]:
    """Blockiness of every condition of one image, in the order of the v1 records."""
    from PIL import Image

    image = np.array(Image.open(job["image_path"]).convert("RGB"))
    return [{"name": job["name"], "corruption": c, "level": lv,
             "blockiness": qg.blockiness(condition_image(image, (c, lv), job["seed"], job["name"]))}
            for c, lv in job["conditions"]]


def blockiness_split(records: list[dict], paths: dict[str, str], out: Path, seed: int, workers: int) -> dict:
    """{(name, corruption, level): blockiness}; images already in `out` are skipped."""
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()] if out.exists() else []
    done = {r["name"] for r in rows}
    conditions: dict[str, list] = {}
    for r in records:
        conditions.setdefault(r["name"], []).append((r["corruption"], r["level"]))
    jobs = [{"name": n, "image_path": paths[n], "conditions": c, "seed": seed} for n, c in conditions.items() if n not in done]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for k, new in enumerate(pool.map(blockiness_image, jobs), 1):
            with out.open("a", encoding="utf-8") as f:
                f.writelines(json.dumps(r) + "\n" for r in new)
            rows += new
            print(f"[{out.stem}] {k}/{len(jobs)} {new[0]['name']}", flush=True)
    return {(r["name"], r["corruption"], r["level"]): r["blockiness"] for r in rows}


def with_blockiness(records: list[dict], block: dict) -> list[dict]:
    return [dict(r, features=dict(r["features"], blockiness=block[(r["name"], r["corruption"], r["level"])])) for r in records]


# ----------------------------------------------------------------------------- analysis (pure)

def crosses(sev: float, ref: float, boundary: float) -> bool:
    """Does the estimate fall on the other side of one threshold than the clean estimate?
    Boundary 0 = the none/low boundary (exactly 0 against above 0). A missing estimate crosses."""
    if sev is None or not np.isfinite(sev):
        return True
    return (sev > 0) != (ref > 0) if boundary == 0 else (sev >= boundary) != (ref >= boundary)


def flip_breakdown(records: list[dict], score: np.ndarray, coverages: list[float], boundaries: list[float]) -> dict:
    """Per coverage (answering the lowest scores first): flip rate with the full mapping and the share
    of answered estimates crossing each single boundary. Records need `clean_severity` and `flip`."""
    order = np.argsort(score, kind="stable")
    out = {}
    for c in list(coverages) + [1.0]:
        k = max(1, int(np.ceil(c * len(order) - 1e-9)))
        chosen = [records[i] for i in order[:k]]
        row = {"flip": float(np.mean([r["flip"] for r in chosen]))}
        for b in boundaries:
            row[str(b)] = float(np.mean([crosses(r["severity"], r["clean_severity"], b) for r in chosen]))
        out[str(c)] = row
    return out


def attach_clean(records: list[dict]) -> list[dict]:
    clean = {r["name"]: r["severity"] for r in records if r["corruption"] == "clean"}
    return [dict(r, clean_severity=clean[r["name"]]) for r in records]


def clean_distribution(clean_records: list[dict]) -> dict:
    s = np.array([r["severity"] for r in clean_records], dtype=float)
    s = s[np.isfinite(s)]
    return {"n": int(len(s)), "zero": float((s == 0).mean()), "between_0_and_5": float(((s > 0) & (s < 5)).mean()),
            "within_3_of_5": float((np.abs(s - 5) <= 3).mean()), "within_3_of_20": float((np.abs(s - 20) <= 3).mean()),
            "median": float(np.median(s))}


def fit_classifier_cv(records: list[dict], with_scores: bool, seed: int, folds: int, c_grid: list[float]):
    """Tiny classifier with C chosen by grouped (by image) K-fold CV. Returns (predict function on all
    records, info, out-of-fold predictions aligned with `records`)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def make(c: float):
        return make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=2000, random_state=seed))

    x, y = p6._x(records, with_scores), np.array([r["unreliable"] for r in records])
    groups = np.array([r["name"] for r in records])
    splitter = GroupKFold(n_splits=max(2, min(folds, len(set(groups)))))
    best = None
    for c in c_grid:
        oof = np.zeros(len(y))
        for tr, te in splitter.split(x, y, groups):
            if len(set(y[tr])) < 2:
                oof[te] = y[tr].mean()
                continue
            oof[te] = make(c).fit(x[tr], y[tr]).predict_proba(x[te])[:, 1]
        loss = float(log_loss(y, np.clip(oof, 1e-6, 1 - 1e-6), labels=[0, 1]))
        if best is None or loss < best[0]:
            best = (loss, c, oof)
    final = make(best[1]).fit(x, y) if len(set(y)) > 1 else None

    def predict(recs: list[dict]) -> np.ndarray:
        return final.predict_proba(p6._x(recs, with_scores))[:, 1] if final is not None else np.full(len(recs), float(y.mean()))

    return predict, {"C": best[1], "cv_log_loss": best[0]}, best[2]


def thresholds_among_passed(score_passed: np.ndarray, coverages: list[float]) -> dict[str, float]:
    """v2: the coverage quantile of the policy score among gate-passed photos."""
    return {str(c): float(np.quantile(score_passed, c)) if len(score_passed) else float("inf") for c in coverages}


def v1_policy_scores(val: list[dict], test_pool: list[dict], seed: int) -> tuple[str, np.ndarray]:
    """Re-derives the v1 policy score on the test pool exactly as `phase6.analyse` did (deterministic)."""
    val_pool = p6.corrupted(val)
    fit_on = val_pool + [r for r in val if r["corruption"] == "clean"]
    classifiers = {"gate_classifier": p6.fit_classifier(fit_on, False, seed), "full_classifier": p6.fit_classifier(fit_on, True, seed)}
    val_scores = p6.all_scores(val_pool, classifiers)
    risk = p6._risks(val_pool)["shift"]
    name = min(val_scores, key=lambda s: sc.aurc(val_scores[s], risk))
    return name, p6.all_scores(test_pool, classifiers)[name]


def analyse_v2(val_v1: list[dict], test_v1: list[dict], val: list[dict], test: list[dict], gate_set: dict,
               experiment: dict, v1_experiment: dict, config: dict) -> tuple[dict, dict]:
    """Fit on validation, evaluate on test once. `*_v1` = the v1 records without blockiness."""
    limit, cov, seed = v1_experiment["unreliable_shift"], experiment["coverages"], config["seed"]
    bounds = experiment["flip_boundaries"]
    val, test = attach_clean(p6.add_errors(val, config, limit)), attach_clean(p6.add_errors(test, config, limit))
    val_pool, test_pool = p6.corrupted(val), p6.corrupted(test)
    val_clean = [r for r in val if r["corruption"] == "clean"]
    test_clean = [r for r in test if r["corruption"] == "clean"]

    # 1-2. gate
    ranges, tail, val_rate = qg.fit_ranges_total([r["features"] for r in val_clean], experiment["gate_false_retake_target"], experiment["checks"])
    val_gate, test_gate, clean_gate = p6.gate_flags(val_pool, ranges), p6.gate_flags(test_pool, ranges), p6.gate_flags(test_clean, ranges)

    def per_check(recs: list[dict]) -> dict:
        fails = [qg.failed_checks(r["features"], ranges) for r in recs]
        return {k: float(np.mean([k in f for f in fails])) for k in ranges}

    # 4. classifiers with CV; policy score by out-of-fold AURC on gate-passed val photos
    fit_on = val_pool + val_clean
    classifiers, cv_info, oof = {}, {}, {}
    for name, with_scores in (("gate_classifier", False), ("full_classifier", True)):
        fn, info, pred = fit_classifier_cv(fit_on, with_scores, seed, experiment["cv_folds"], experiment["c_grid"])
        classifiers[name], cv_info[name], oof[name] = fn, info, pred[:len(val_pool)]
    val_scores = {s: np.array([r[s] for r in val_pool], dtype=float) for s in p6.RAW_SCORES} | oof
    passed_val = ~val_gate
    val_passed_pool = [r for r, ok in zip(val_pool, passed_val) if ok]
    val_risk = p6._risks(val_passed_pool)["shift"]
    val_aurc = {s: sc.aurc(v[passed_val], val_risk) for s, v in val_scores.items()}
    policy_score = min(val_aurc, key=val_aurc.get)

    # 3. thresholds among gate-passed
    thresholds = thresholds_among_passed(val_scores[policy_score][passed_val], cov)

    # test
    test_scores = p6.all_scores(test_pool, classifiers)
    passed_test = ~test_gate
    test_passed_pool = [r for r, ok in zip(test_pool, passed_test) if ok]
    passed_scores = {s: v[passed_test] for s, v in test_scores.items()}
    table_passed = p6.score_table(test_passed_pool, passed_scores, cov, experiment["n_bootstrap"], seed)
    table_all = p6.score_table(test_pool, test_scores, cov, experiment["n_bootstrap"], seed)
    risks = p6._risks(test_passed_pool)
    curves = {n: {rk: [list(map(float, a)) for a in sc.risk_coverage(s, risks[rk])] for rk in risks}
              for n, s in dict(passed_scores, oracle_shift=risks["shift"], oracle_flip=risks["flip"]).items()} if test_passed_pool else {}
    clean_scores = p6.all_scores(test_clean, classifiers)[policy_score]
    policy = {}
    for c, thr in thresholds.items():
        policy[c] = {"threshold": thr,
                     "corrupted": p6.policy_outcome(test_pool, test_scores[policy_score], test_gate, thr),
                     "clean": p6.policy_outcome([{k: v for k, v in r.items() if k != "shift"} for r in test_clean], clean_scores, clean_gate, thr)}
    low = str(min(cov))
    refused = test_gate | (test_scores[policy_score] > thresholds[low])

    # 5. flips by threshold: v1 policy on all corrupted test photos, v2 policy on gate-passed ones
    v1_name, v1_score = v1_policy_scores(p6.add_errors(val_v1, config, limit), p6.corrupted(p6.add_errors(test_v1, config, limit)), seed)
    flips = {"v1": {"score": v1_name, "pool": "all corrupted test photos",
                    "rows": flip_breakdown(test_pool, v1_score, cov, bounds)},
             "v2": {"score": policy_score, "pool": "gate-passed corrupted test photos",
                    "rows": flip_breakdown(test_passed_pool, test_scores[policy_score][passed_test], cov, bounds) if test_passed_pool else {}},
             "v2_policy": {"rows": {c: {"flip": float(np.mean([r["flip"] for r, a in zip(test_pool, ~(test_gate | (test_scores[policy_score] > t))) if a])),
                                        **{str(b): float(np.mean([crosses(r["severity"], r["clean_severity"], b)
                                                                  for r, a in zip(test_pool, ~(test_gate | (test_scores[policy_score] > t))) if a]))
                                           for b in bounds}} for c, t in thresholds.items()}},
             "clean_test": clean_distribution(test_clean)}

    shift = p6._risks(test_pool)["shift"]
    bound = float(np.percentile([r["leaf_share"] for r in val_clean], v1_experiment["gate_tail_pct"]))
    sets = {}
    for name, rows in gate_set.items():
        photo = np.array([bool(qg.failed_checks(r["features"], ranges)) for r in rows], dtype=bool)
        framing = np.array([r["leaf_share"] < bound for r in rows], dtype=bool)
        sets[name] = {"n": len(rows), "photo": float(photo.mean()) if len(rows) else float("nan"),
                      "framing": float(framing.mean()) if len(rows) else float("nan"),
                      "either": float((photo | framing).mean()) if len(rows) else float("nan")}
    sizes = {split: [float(r["features"]["min_side"]) for r in recs] for split, recs in (("val", val_clean), ("test", test_clean))}
    res = {
        "n_val_images": len(val_clean), "policy_score": policy_score, "cv": cv_info, "val_aurc_passed_oof": val_aurc,
        "thresholds": thresholds, "test_table_passed": table_passed, "test_table_all": table_all, "test_table": table_passed,
        "policy": policy, "flips": flips, "gate_title_suffix": " (v2 gate, post hoc)",
        "gate": {"ranges": ranges, "tail_pct": tail, "clean_val": val_rate, "clean_test": float(clean_gate.mean()),
                 "per_check_clean": {"val": per_check(val_clean), "test": per_check(test_clean)},
                 "corrupted_test": float(test_gate.mean()), "passed_val_share": float(passed_val.mean()),
                 "shift_failed": float(shift[test_gate].mean()) if test_gate.any() else float("nan"),
                 "shift_passed": float(shift[~test_gate].mean()) if (~test_gate).any() else float("nan"),
                 "matrix": p6.gate_matrix(test_pool, ranges),
                 "coverage": {"policy_coverage": low, "cells": p6.gate_coverage(test_pool, ranges, refused)},
                 "min_side": {s: {"pct": dict(zip(("1", "2.5", "5", "10", "50"), np.percentile(v, [1, 2.5, 5, 10, 50]).round(1).tolist())),
                                  "below_224": int(np.sum(np.array(v) < 224)), "n": len(v)} for s, v in sizes.items()}},
        "gate_set": {"leaf_share_bound": bound, "sets": sets},
    }
    return res, curves


# ----------------------------------------------------------------------------- report

def _num(x: float, fmt: str = "{:.2f}") -> str:
    return "-" if x is None or not np.isfinite(x) else fmt.format(x)


def format_report(res: dict, experiment: dict, v1_experiment: dict, commit: str, prereg: str) -> str:
    cov, pct = experiment["coverages"], p6._pct
    g, t, ta = res["gate"], res["test_table_passed"], res["test_table_all"]
    lines = [
        f"# Phase 6 v2 (POST HOC): revised gate and abstention policy ({date.today().isoformat()})", "",
        f"Commit at run time: `{commit}`; rules and code tagged `{prereg}` before this single test evaluation. "
        "Generated by `python -m src.uncertainty.phase6_v2`.", "",
        "**This is a post-hoc round, decided after the v1 test results were seen.** The pre-registered result is v1 "
        "(`report/tables/abstention.md`, tag `phase6-v1`), reported unchanged. Everything here was fitted on the validation split "
        f"({res['n_val_images']} images) and evaluated once on test ({ta['n_images']} images). Gold was not used. Same method and records "
        f"as the base run (colour stage {p6.describe_colour_stage(v1_experiment)}); error = distance from the clean-photo estimate; "
        "flip rates use the PLACEHOLDER levels and mapping; corruption levels are placeholders.", "",
        "Changes: (1) one overall false-retake target of "
        f"{pct(experiment['gate_false_retake_target'])} on clean validation photos, split evenly over the check sides, with the minimum side "
        "fitted inside that budget instead of the fixed 224 px; (2) a JPEG blockiness check; (3) coverage measured among gate-passed "
        "photos; (4) classifiers tuned and the policy score chosen by grouped cross-validation inside validation.", "",
        "## Quality gate", "",
        f"Tail percentile per check side: {g['tail_pct']:g}. Ranges: "
        + "; ".join(f"{k} [{'-' if lo is None else f'{lo:.3g}'}, {'-' if hi is None else f'{hi:.3g}'}]" for k, (lo, hi) in g["ranges"].items()) + ".", "",
        f"**Clean photos sent back for a retake: validation {pct(g['clean_val'])} (fitted), test {pct(g['clean_test'])}** (v1: 15% and 19%). "
        f"Corrupted test photos sent back: {pct(g['corrupted_test'])} (v1: 55%); mean shift {g['shift_failed']:.2f} points when the gate fails, "
        f"{g['shift_passed']:.2f} when it passes. Gate-passed share of corrupted validation photos: {pct(g['passed_val_share'])}.", "",
        "Clean photos failing each check:", "", "| check | validation | test |", "|---|---:|---:|"]
    for k in g["ranges"]:
        lines.append(f"| {qg.REASONS.get(k, k)} (`{k}`) | {pct(g['per_check_clean']['val'][k])} | {pct(g['per_check_clean']['test'][k])} |")
    lines += ["", "Shorter side of the clean photos, px (the v1 gate used a fixed 224 px minimum):", "",
              "| split | 1st pct | 2.5th | 5th | 10th | median | below 224 px |", "|---|---:|---:|---:|---:|---:|---:|"]
    for s, o in g["min_side"].items():
        p = o["pct"]
        lines.append(f"| {s} | {p['1']:g} | {p['2.5']:g} | {p['5']:g} | {p['10']:g} | {p['50']:g} | {o['below_224']} of {o['n']} |")

    lines += ["", "## Policy score, chosen inside validation", "",
              "Out-of-fold shift AURC on gate-passed corrupted validation photos (lower is better); classifiers' C by grouped "
              f"{experiment['cv_folds']}-fold CV: " + ", ".join(f"{k} C = {v['C']:g}" for k, v in res["cv"].items()) + ".", "",
              "| score | validation AURC (out of fold) |", "|---|---:|"]
    for s, v in sorted(res["val_aurc_passed_oof"].items(), key=lambda kv: kv[1]):
        lines.append(f"| {p6.SCORE_LABELS.get(s, s)}{' **(policy score)**' if s == res['policy_score'] else ''} | {v:.2f} |")

    def cells(row: dict, rk: str) -> str:
        return " | ".join(f"{row[rk][f'at_{c}']['risk']:.2f} ({row[rk][f'at_{c}']['ci_low']:.2f}-{row[rk][f'at_{c}']['ci_high']:.2f})" for c in cov)

    lines += ["", "## Risk-coverage on gate-passed corrupted test photos", "",
              f"{t['n']} estimates from {t['n_images']} images pass the gate. Without abstention among them: shift {t['base']['shift']:.2f} points, "
              f"flip rate {t['base']['flip']:.2f}.", "",
              "| score | AUROC for \"shift > " + f"{v1_experiment['unreliable_shift']}" + "\" | shift AURC | " + " | ".join(f"shift at {int(100 * c)}% (95% CI)" for c in cov)
              + " | flip AURC | " + " | ".join(f"flip at {int(100 * c)}% (95% CI)" for c in cov) + " |",
              "|---|---:|---:|" + "---|" * len(cov) + "---:|" + "---|" * len(cov)]
    for name, row in t["scores"].items():
        mark = " **(policy score)**" if name == res["policy_score"] else ""
        lines.append(f"| {p6.SCORE_LABELS.get(name, name.replace('_', ' '))}{mark} | {_num(row['auroc_unreliable'])} | {row['shift']['aurc']:.2f} | "
                     f"{cells(row, 'shift')} | {row['flip']['aurc']:.3f} | {cells(row, 'flip')} |")
    row = t["scores"][res["policy_score"]]
    lines += ["", "## Error reduction at fixed coverage among gate-passed photos (policy score, test)", "",
              "| coverage | severity shift, points | reduction | flip rate | reduction |", "|---:|---|---:|---|---:|"]
    for c in cov:
        s, f = row["shift"][f"at_{c}"], row["flip"][f"at_{c}"]
        lines.append(f"| {int(100 * c)}% | {s['risk']:.2f} ({s['ci_low']:.2f}-{s['ci_high']:.2f}) | {pct(1 - s['risk'] / t['base']['shift'])} | "
                     f"{f['risk']:.2f} ({f['ci_low']:.2f}-{f['ci_high']:.2f}) | {pct(1 - f['risk'] / t['base']['flip'])} |")
    lines.append(f"| 100% | {t['base']['shift']:.2f} | - | {t['base']['flip']:.2f} | - |")

    lines += ["", "## Full policy: gate, then uncertainty (thresholds from validation, among gate-passed photos)", "",
              "| target coverage among passed | photos | retake | consult an expert | answered | shift: answered / refused / all | flip: answered / refused / all |",
              "|---:|---|---:|---:|---:|---|---|"]
    for c in cov:
        for pool in ("corrupted", "clean"):
            o = res["policy"][str(c)][pool]
            risks = (f"{_num(o['shift_answered'])} / {_num(o['shift_refused'])} / {_num(o['shift_all'])} | "
                     f"{_num(o['flip_answered'])} / {_num(o['flip_refused'])} / {_num(o['flip_all'])}") if pool == "corrupted" else "- | -"
            lines.append(f"| {int(100 * c)}% | test, {pool} (n = {o['n']}) | {pct(o['retake'])} | {pct(o['consult'])} | {pct(o['answered'])} | {risks} |")

    cv_ = g["coverage"]
    pc = int(100 * float(cv_["policy_coverage"]))
    lines += ["", "## Does the gate catch the estimates that moved?", "",
              f"Unreliable = shift > {v1_experiment['unreliable_shift']} points. Catch rate = share of unreliable estimates sent back. Policy = gate "
              f"or uncertainty at the {pc}% target. All levels pooled, test.", "",
              "| corruption | unreliable | gate catch rate | retake rate among reliable | shift: gate passes / fails | "
              f"policy catch rate ({pc}%) | shift of answered ({pc}%) |", "|---|---:|---:|---:|---|---:|---:|"]
    for c in p6.BENCH:
        o = cv_["cells"][c]["all"]
        lines.append(f"| {c} | {pct(o['unreliable'])} | {pct(o['caught'])} | {pct(o['false_retake'])} | {_num(o['shift_passed'])} / {_num(o['shift_failed'])} | "
                     f"{pct(o['policy_caught'])} | {_num(o['shift_answered'])} |")
    lines += ["", "Gate catch rate by level (share unreliable in brackets):", "",
              "| corruption | " + " | ".join(f"level {lv}" for lv in p6.LEVELS) + " |", "|---|" + "---|" * len(p6.LEVELS)]
    for c in p6.BENCH:
        lines.append(f"| {c} | " + " | ".join(f"{pct(cv_['cells'][c][str(lv)]['caught'])} ({pct(cv_['cells'][c][str(lv)]['unreliable'])})" for lv in p6.LEVELS) + " |")
    lines += ["", f"Policy catch rate by level ({pc}% target):", "",
              "| corruption | " + " | ".join(f"level {lv}" for lv in p6.LEVELS) + " |", "|---|" + "---:|" * len(p6.LEVELS)]
    for c in p6.BENCH:
        lines.append(f"| {c} | " + " | ".join(pct(cv_["cells"][c][str(lv)]["policy_caught"]) for lv in p6.LEVELS) + " |")
    lines += ["", "Retake rate by corruption and level:", "",
              "| corruption | " + " | ".join(f"level {lv}" for lv in p6.LEVELS) + " | most frequent failed check |", "|---|" + "---:|" * len(p6.LEVELS) + "---|"]
    for c in p6.BENCH:
        reasons = g["matrix"]["reasons"][c]
        top = max(reasons, key=reasons.get)
        lines.append(f"| {c} | " + " | ".join(pct(g["matrix"]["rate"][c][str(lv)]) for lv in p6.LEVELS) + f" | {qg.REASONS.get(top, top)} ({pct(reasons[top])}) |")

    fl, bounds = res["flips"], experiment["flip_boundaries"]
    d = fl["clean_test"]
    head = "| coverage | flip rate (full mapping) | " + " | ".join("crosses 0% (none/low)" if b == 0 else f"crosses {b:g}%" for b in bounds) + " |"
    sep = "|---:|---:|" + "---:|" * len(bounds)
    lines += ["", "## Which thresholds do the flips cross?", "",
              f"Clean test estimates (n = {d['n']}): {pct(d['zero'])} are exactly 0, {pct(d['between_0_and_5'])} are above 0 and below 5%, "
              f"{pct(d['within_3_of_5'])} are within 3 points of 5%, {pct(d['within_3_of_20'])} within 3 points of 20%; median {d['median']:.1f}%. "
              "A single-threshold column is the share of answered estimates on the other side of that threshold than the clean estimate.", ""]
    for key, title in (("v1", "v1 policy score"), ("v2", "v2 policy score")):
        lines += [f"**{title}** (`{fl[key]['score']}`), {fl[key]['pool']}, answering the lowest scores first:", "", head, sep]
        for c, r in fl[key]["rows"].items():
            lines.append(f"| {int(100 * float(c))}% | {r['flip']:.2f} | " + " | ".join(f"{r[str(b)]:.2f}" for b in bounds) + " |")
        lines.append("")
    lines += ["**v2 full policy** (gate, then uncertainty), answered corrupted test photos:", "", head.replace("coverage", "target among passed"), sep]
    for c, r in fl["v2_policy"]["rows"].items():
        lines.append(f"| {int(100 * float(c))}% | {r['flip']:.2f} | " + " | ".join(f"{r[str(b)]:.2f}" for b in bounds) + " |")

    gs = res["gate_set"]
    lines += ["", "## Gate test set: `wide` and `skip` images", "",
              f"Framing check unchanged from v1 (leaf share below {100 * gs['leaf_share_bound']:.1f}%).", "",
              "| set | n | fails a photo check | fails the framing check | fails either |", "|---|---:|---:|---:|---:|"]
    for name, o in gs["sets"].items():
        lines.append(f"| {name} | {o['n']} | {pct(o['photo'])} | {pct(o['framing'])} | {pct(o['either'])} |")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- main

def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase6_v2.yaml")
    parser.add_argument("--v1-run", default=None, help="override the v1 run folder (the debug run with --debug)")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--debug", action="store_true", help="v1 debug run; outputs only in the experiment folder")
    parser.add_argument("--blockiness-from", default=None,
                        help="earlier v2 run whose blockiness and gate-set files are reused (they depend only on the photos)")
    parser.add_argument("--table", default=None, help="report path (default report/tables/abstention_v2.md)")
    parser.add_argument("--fig-dir", default=None, help="figure folder (default report/figures/phase6_v2)")
    args = parser.parse_args()
    config = load_config(args.config)
    experiment = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    v1_experiment = yaml.safe_load(Path(experiment["v1_experiment"]).read_text(encoding="utf-8"))
    v1_run = Path(args.v1_run or experiment["v1_run"])
    exp_dir = Path(args.resume) if args.resume else create_experiment_dir("phase6_v2" + ("_debug" if args.debug else ""), args.config)
    shutil.copy(args.experiment, exp_dir / Path(args.experiment).name)
    if args.blockiness_from:
        for f in ("blockiness_val.jsonl", "blockiness_test.jsonl", "gate_set.json"):
            if not (exp_dir / f).exists():
                shutil.copy(Path(args.blockiness_from) / f, exp_dir / f)

    from src.corruptions.cache import split_entries
    from src.data.wheat_metadata import image_path

    records_v1, records = {}, {}
    for split in ("val", "test"):
        records_v1[split] = _read(v1_run / f"records_{split}.jsonl")
        paths = {e["name"]: str(e["image_path"]) for e in split_entries(config, split)}
        block = blockiness_split(records_v1[split], paths, exp_dir / f"blockiness_{split}.jsonl", config["seed"], args.workers)
        records[split] = with_blockiness(records_v1[split], block)

    gate_file = exp_dir / "gate_set.json"
    if gate_file.exists():
        gate_set = json.loads(gate_file.read_text(encoding="utf-8"))
    else:
        from PIL import Image

        plantseg_dir = Path(config["data"]["plantseg_dir"])
        rows = {r["name"]: r for group in p6.gate_set_rows(config).values() for r in group}
        gate_set = {group: [dict(r, features=dict(r["features"], blockiness=qg.blockiness(
            np.array(Image.open(image_path(plantseg_dir, rows[r["name"]])).convert("RGB"))))) for r in items]
            for group, items in json.loads((v1_run / "gate_set.json").read_text(encoding="utf-8")).items()}
        gate_file.write_text(json.dumps(gate_set), encoding="utf-8")

    res, curves = analyse_v2(records_v1["val"], records_v1["test"], records["val"], records["test"], gate_set, experiment, v1_experiment, config)
    (exp_dir / "metrics.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (exp_dir / "curves.json").write_text(json.dumps(curves), encoding="utf-8")
    prereg = experiment.get("prereg_tag", "phase6-v2-prereg")
    report = format_report(res, experiment, v1_experiment, get_git_commit_hash(), prereg)
    table, fig_dir = Path(args.table) if args.table else TABLE, Path(args.fig_dir) if args.fig_dir else FIG_DIR
    out = exp_dir / table.name if args.debug else table
    out.write_text(report, encoding="utf-8")
    p6.plot(res, curves, exp_dir / "figures" if args.debug else fig_dir, pool_label="gate-passed corrupted test photos (v2, post hoc)")
    print(f"Policy score: {res['policy_score']}. Wrote {out}; {exp_dir}")


if __name__ == "__main__":
    main()
