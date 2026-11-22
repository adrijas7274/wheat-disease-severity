"""Blind review of leaf-mask combinations on the tuning set (Phase 3 step 1).

Combinations = SAM 2 model x leaf rule (config `sam2.leaf_rule_review`). The
rater sees one leaf outline at a time, shuffled, with no model or rule name,
and marks "whole main leaf: yes / no". The combination with the most "yes"
is then frozen in the config. Tuning images only: no gold image is touched.

Steps:
    python -m src.severity.leaf_rule_review candidates   # run each SAM 2 model, cache its 3 candidates, log VRAM
    python -m src.severity.leaf_rule_review prepare      # apply the rules, write shuffled overlays + hidden key
    python -m src.severity.leaf_rule_review serve        # the review screen
    python -m src.severity.leaf_rule_review sheet        # contact sheet of all outlines with the verdicts (no names)
    python -m src.severity.leaf_rule_review report       # count "yes" per combination

`--debug` (candidates, prepare) uses the first 3 tuning images and a separate folder.
"""

import argparse
import csv
import json
import random
import time
from datetime import date
from pathlib import Path

import numpy as np

from src.severity import annotation_core as core
from src.severity.leaf_mask import candidate_masks, select_leaf, tuning_rows
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

LOG_FIELDS = ["item", "verdict", "rater", "saved_at"]
VERDICTS = ("yes", "no")
TABLE = Path("report/tables/leaf_rule_review.md")
SHEET = Path("report/figures/leaf_masks/leaf_rule_review_sheet.png")


# ---------------------------------------------------------------- pure helpers

def combo_label(model: str, rule: str) -> str:
    return f"{model} + {rule}"


def group_identical(masks: dict[str, np.ndarray]) -> list[list[str]]:
    """Group combination labels whose masks are pixel-identical, so the rater
    judges each distinct outline of an image once."""
    groups: list[list[str]] = []
    for label, mask in masks.items():
        for g in groups:
            if np.array_equal(masks[g[0]], mask):
                g.append(label)
                break
        else:
            groups.append([label])
    return groups


def tally(key: dict[str, dict], verdicts: dict[str, str], combos: list[str]) -> dict[str, dict]:
    """Per combination: number of images judged 'yes', 'no' and not yet judged.

    key: item id -> {"name": image, "combos": [labels]}; verdicts: item id -> 'yes' / 'no'.
    """
    out = {c: {"yes": 0, "no": 0, "pending": 0} for c in combos}
    for item, entry in key.items():
        for c in entry["combos"]:
            out[c][verdicts.get(item, "pending")] += 1
    return out


def pick_winner(counts: dict[str, dict], preference: list[str]) -> str:
    """Combination with the most 'yes'. Ties go to the one listed first in
    `preference` (fixed before the review: smaller model first, then the
    simpler rule)."""
    best = max(c["yes"] for c in counts.values())
    return next(c for c in preference if counts[c]["yes"] == best)


def load_verdicts(log_csv: Path) -> dict[str, str]:
    """item id -> latest verdict."""
    if not log_csv.exists():
        return {}
    with open(log_csv, encoding="utf-8") as f:
        return {r["item"]: r["verdict"] for r in csv.DictReader(f)}


# ---------------------------------------------------------------- paths and config

def _paths(config: dict, debug: bool = False) -> dict[str, Path]:
    ann = config["annotation"]
    rev = config["sam2"]["leaf_rule_review"]
    root = Path(ann["out_dir"]) / (rev["dir"] + ("_debug" if debug else ""))
    return {"root": root, "cands": root / "candidates", "items": root / "items",
            "key": root / "key.json", "order": root / "order.json",
            "log": Path(ann["out_dir"]) / rev["log"]}


def _combos(config: dict) -> list[str]:
    """All combination labels, in tie-break preference order (config order)."""
    rev = config["sam2"]["leaf_rule_review"]
    return [combo_label(m, r) for m in rev["models"] for r in rev["rules"]]


def _load_image(config: dict, row: dict) -> np.ndarray:
    from PIL import Image

    from src.data.wheat_metadata import image_path

    return np.array(Image.open(image_path(Path(config["data"]["plantseg_dir"]), row)).convert("RGB"))


def _cand_file(cands: Path, model: str, name: str) -> Path:
    return cands / model / (name + ".npz")


# ---------------------------------------------------------------- step: candidates

def run_candidates(config: dict, config_path: str, debug: bool) -> None:
    """Cache each model's 3 candidate masks per tuning image; log shares, scores, time and peak VRAM."""
    import torch

    from src.severity.sam2_model import load_sam2_predictor

    paths = _paths(config, debug)
    rows = tuning_rows(config)[:3] if debug else tuning_rows(config)
    exp_dir = create_experiment_dir("leaf_rule_candidates" + ("_debug" if debug else ""), config_path)
    metrics: dict = {"n_images": len(rows), "models": {}}
    for model, spec in config["sam2"]["leaf_rule_review"]["models"].items():
        cuda = torch.cuda.is_available()
        if cuda:
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        predictor = load_sam2_predictor({**config, "sam2": {**config["sam2"], **spec}})
        per_image, seconds = [], []
        for row in rows:
            img = _load_image(config, row)
            click = (int(row["click_x"]), int(row["click_y"]))
            t0 = time.perf_counter()
            predictor.set_image(img)
            masks, scores = candidate_masks(predictor, click)
            seconds.append(time.perf_counter() - t0)
            out = _cand_file(paths["cands"], model, row["name"])
            out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(out, masks=masks, scores=scores)
            per_image.append({"name": row["name"], "shares": [float(m.mean()) for m in masks],
                              "scores": [float(s) for s in scores]})
            print(f"{model:10s} shares % {[round(100 * s, 1) for s in per_image[-1]['shares']]} "
                  f"scores {[round(s, 2) for s in per_image[-1]['scores']]}  {row['name']}")
        metrics["models"][model] = {
            "checkpoint": spec["checkpoint"], "device": str(predictor.device),
            "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20, 1) if cuda else None,
            "peak_vram_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20, 1) if cuda else None,
            "median_s_per_image": float(np.median(seconds)), "first_image_s": float(seconds[0]),
            "images": per_image,
        }
        print(f"{model}: peak VRAM {metrics['models'][model]['peak_vram_mib']} MiB allocated, "
              f"median {np.median(seconds):.2f} s per image")
        del predictor
    (exp_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Wrote {exp_dir}")


# ---------------------------------------------------------------- step: prepare

def _overlay(img: np.ndarray, mask: np.ndarray, click: tuple[int, int], long_side: int = 1100) -> np.ndarray:
    """Photo with one leaf outline (magenta) and the click (yellow)."""
    import cv2

    scale = long_side / max(img.shape[:2])
    vis = cv2.resize(img, (round(img.shape[1] * scale), round(img.shape[0] * scale)), interpolation=cv2.INTER_AREA
                     if scale < 1 else cv2.INTER_CUBIC)
    small = cv2.resize(mask.astype(np.uint8), (vis.shape[1], vis.shape[0]), interpolation=cv2.INTER_NEAREST)
    cs, _ = cv2.findContours(small, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(vis, cs, -1, (0, 0, 0), 5)
    cv2.drawContours(vis, cs, -1, (255, 60, 200), 3)
    c = (round(click[0] * scale), round(click[1] * scale))
    cv2.circle(vis, c, 8, (255, 255, 0), -1)
    cv2.circle(vis, c, 8, (0, 0, 0), 2)
    return vis


def run_prepare(config: dict, debug: bool) -> None:
    """Apply every rule to the cached candidates; write shuffled overlays and the hidden key."""
    from PIL import Image

    rev = config["sam2"]["leaf_rule_review"]
    paths = _paths(config, debug)
    if rev["min_area_share"] is None:
        raise ValueError("Set sam2.leaf_rule_review.min_area_share in the config first.")
    if not debug and paths["log"].exists():
        raise FileExistsError(f"{paths['log']} exists: the review has started, so the items are frozen.")
    rows = tuning_rows(config)[:3] if debug else tuning_rows(config)
    rng = random.Random(config["seed"])
    ids = rng.sample(range(1000, 10000), 4 * len(rows))
    paths["items"].mkdir(parents=True, exist_ok=True)
    for old in paths["items"].glob("*.jpg"):
        old.unlink()
    key: dict[str, dict] = {}
    for row in rows:
        click = (int(row["click_x"]), int(row["click_y"]))
        masks = {}
        for model in rev["models"]:
            cand = np.load(_cand_file(paths["cands"], model, row["name"]))
            for rule in rev["rules"]:
                i = select_leaf(cand["masks"], cand["scores"], click, rule, rev["min_area_share"])
                masks[combo_label(model, rule)] = cand["masks"][i]
        img = _load_image(config, row)
        for group in group_identical(masks):
            item = str(ids.pop())
            key[item] = {"name": row["name"], "combos": group, "share": float(masks[group[0]].mean())}
            Image.fromarray(_overlay(img, masks[group[0]], click)).save(paths["items"] / f"{item}.jpg", quality=92)
    order = sorted(key)
    rng.shuffle(order)
    paths["key"].write_text(json.dumps(key, indent=2), encoding="utf-8")
    paths["order"].write_text(json.dumps(order), encoding="utf-8")
    print(f"{len(rows)} images x {len(_combos(config))} combinations -> {len(key)} distinct outlines to review "
          f"in {paths['items']}")


# ---------------------------------------------------------------- step: serve

def build_app(config: dict):
    """Gradio review screen: one outline at a time, Yes / No, Back."""
    import gradio as gr

    paths = _paths(config)
    order: list[str] = json.loads(paths["order"].read_text(encoding="utf-8"))

    def first_open() -> int:
        done = load_verdicts(paths["log"])
        return next((i for i, item in enumerate(order) if item not in done), len(order))

    def show(pos: int):
        done = load_verdicts(paths["log"])
        n_done = sum(item in done for item in order)
        if pos >= len(order):
            return None, f"## Finished: {n_done} / {len(order)} judged. You can close this tab.", pos
        prev = f" (your earlier answer here: **{done[order[pos]]}**)" if order[pos] in done else ""
        return str(paths["items"] / f"{order[pos]}.jpg"), f"### Outline {pos + 1} of {len(order)}{prev}", pos

    def vote(verdict: str, rater: str, pos: int):
        if pos < len(order):
            core.append_log(paths["log"], {"item": order[pos], "verdict": verdict, "rater": rater.strip(),
                                           "saved_at": core.now_iso()}, LOG_FIELDS)
            pos += 1
        return show(pos)

    with gr.Blocks(title="Leaf outline review") as demo:
        gr.Markdown(
            "# Is the outline the whole main leaf?\n"
            "The yellow dot is your click. **Yes** = the pink outline covers the leaf you clicked, all of its "
            "visible part, and little else. **No** = it covers only part of that leaf, several leaves, "
            "background, or a different object. Outlines are shuffled and unlabelled.")
        pos = gr.State(0)
        rater = gr.Textbox(value=config["annotation"]["ui"]["default_rater"], label="Rater", scale=0)
        head = gr.Markdown()
        with gr.Row():
            yes = gr.Button("Yes: whole main leaf", variant="primary")
            no = gr.Button("No", variant="stop")
            back = gr.Button("Back one")
        view = gr.Image(show_label=False, interactive=False, show_download_button=False, height=720)
        outs = [view, head, pos]
        demo.load(lambda: show(first_open()), None, outs)
        yes.click(lambda r, p: vote("yes", r, p), [rater, pos], outs)
        no.click(lambda r, p: vote("no", r, p), [rater, pos], outs)
        back.click(lambda p: show(max(p - 1, 0)), [pos], outs)
    return demo


# ---------------------------------------------------------------- step: sheet

def run_sheet(config: dict, out: Path = SHEET, cols: int = 5, tile: int = 440) -> None:
    """Contact sheet of every outline in review order with its latest verdict.
    Shows no model or rule names, so it can be checked blind."""
    import cv2

    paths = _paths(config)
    order: list[str] = json.loads(paths["order"].read_text(encoding="utf-8"))
    verdicts = load_verdicts(paths["log"])
    colours = {"yes": (0, 140, 0), "no": (0, 0, 210)}
    tiles = []
    for pos, item in enumerate(order, 1):
        img = cv2.imread(str(paths["items"] / f"{item}.jpg"))
        scale = tile / max(img.shape[:2])
        img = cv2.resize(img, (round(img.shape[1] * scale), round(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        canvas = np.full((tile + 44, tile + 10, 3), 255, np.uint8)
        canvas[: img.shape[0], : img.shape[1]] = img
        verdict = verdicts.get(item, "not judged")
        cv2.putText(canvas, f"{pos}. {verdict.upper()}", (4, tile + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    colours.get(verdict, (90, 90, 90)), 2, cv2.LINE_AA)
        tiles.append(canvas)
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))
    print(f"Wrote {out} ({sum(v == 'yes' for v in verdicts.values())} yes, "
          f"{sum(v == 'no' for v in verdicts.values())} no of {len(order)})")


# ---------------------------------------------------------------- step: report

def run_report(config: dict) -> None:
    """Count 'yes' per combination and write the table. Prints the winner only when every item is judged."""
    paths = _paths(config)
    key = json.loads(paths["key"].read_text(encoding="utf-8"))
    verdicts = load_verdicts(paths["log"])
    combos = _combos(config)
    counts = tally(key, verdicts, combos)
    n = len({e["name"] for e in key.values()})
    pending = sum(item not in verdicts for item in key)
    with open(paths["log"], encoding="utf-8") as f:
        raters = ", ".join(sorted({r["rater"] for r in csv.DictReader(f)})) or "nobody yet"
    lines = [f"# Leaf rule review on the tuning set ({date.today().isoformat()})", "",
             f"Commit at run time: `{get_git_commit_hash()}`. Generated by "
             "`python -m src.severity.leaf_rule_review report`.", "",
             f"{n} tuning images, {len(key)} distinct outlines judged \"whole main leaf: yes / no\" with "
             f"model and rule names hidden. Verdicts logged by: {raters}. Who judged and who checked is "
             "recorded in `experiments/LOG.md`. Minimum share for `min_area`: "
             f"{config['sam2']['leaf_rule_review']['min_area_share']}.", "",
             "| combination | yes | no | not judged |", "|---|---:|---:|---:|"]
    lines += [f"| {c} | {counts[c]['yes']} | {counts[c]['no']} | {counts[c]['pending']} |" for c in combos]
    if pending:
        lines += ["", f"**Incomplete:** {pending} outlines not judged yet, so no combination is chosen."]
    else:
        lines += ["", f"**Most \"yes\": {pick_winner(counts, combos)}** (ties go to the combination listed "
                  "first, fixed before the review)."]
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[6:]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=["candidates", "prepare", "serve", "sheet", "report"])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--port", type=int, default=7862)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.step == "candidates":
        run_candidates(config, args.config, args.debug)
    elif args.step == "prepare":
        run_prepare(config, args.debug)
    elif args.step == "serve":
        build_app(config).launch(server_port=args.port)
    elif args.step == "sheet":
        run_sheet(config)
    else:
        run_report(config)


if __name__ == "__main__":
    main()
