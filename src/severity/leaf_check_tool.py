"""Wrong-leaf check on the gold set (Phase 3, work order step 2).

For every evaluated gold image (finished gold ratings minus
`annotation.gold_exclude`) SAM 2 finds the leaf from the stored gold click
with the frozen rule (`sam2.leaf_rule`). The rater sees only the photo, the
click and the leaf outline, and marks it **correct leaf**, **wrong leaf** or
**not a leaf** (`docs/annotation_guidelines.md`, *Wrong-leaf check*).

Nothing here computes or shows a severity, a lesion mask, a PlantSeg mask or
a model prediction. The leaf masks are saved so the evaluation later uses
exactly the outlines that were checked.

Steps:
    python -m src.severity.leaf_check_tool prepare   # SAM 2 leaves + shuffled overlays (refuses once the check has started)
    python -m src.severity.leaf_check_tool serve     # the check screen
    python -m src.severity.leaf_check_tool summary   # verdict counts (no severities)
    python -m src.severity.leaf_check_tool sheet     # contact sheet of all outlines with their verdicts

`prepare --debug` uses the first 3 images and a separate folder.
"""

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

import numpy as np

from src.severity import annotation_core as core
from src.severity.leaf_mask import leaf_from_click
from src.severity.leaf_rule_review import _load_image, _overlay
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir

LOG_FIELDS = ["name", "verdict", "rater", "saved_at"]
SHEET = Path("report/figures/leaf_masks/leaf_check_sheet.png")
NOTES = Path("report/tables/leaf_check_notes.csv")  # sheet_number, name, one-line note on borderline calls
VERDICTS = {"correct": "Correct leaf", "wrong": "Wrong leaf", "not_a_leaf": "Not a leaf"}
# what happened to each checked image: a verdict, or the reason it was put in `annotation.gold_exclude` after the check
CATEGORIES = {"correct": "kept", "wrong": "wrong leaf", "not_a_leaf": "not a leaf",
              "duplicate": "duplicate", "collage": "collage", "pending": "pending"}


def gold_rows(config: dict) -> list[dict]:
    """Finished gold ratings minus `annotation.gold_exclude`, in log order."""
    ann = config["annotation"]
    status = core.load_status(Path(ann["out_dir"]) / ann["rating_log"], "gold")
    exclude = set(ann.get("gold_exclude", []))
    return [r for n, r in status.items() if r["status"] == "done" and n not in exclude]


def checked_rows(config: dict) -> list[dict]:
    """Gold rating rows of the images that went through the check (`order.json`), in log order.
    Includes images added to `annotation.gold_exclude` after the check."""
    ann = config["annotation"]
    checked = set(json.loads(_paths(config)["order"].read_text(encoding="utf-8")))
    status = core.load_status(Path(ann["out_dir"]) / ann["rating_log"], "gold")
    return [r for n, r in status.items() if n in checked]


def evaluated_gold_rows(config: dict) -> list[dict]:
    """The gold evaluation set: `gold_rows` whose leaf was marked correct. Requires the locked check."""
    ann = config["annotation"]
    if not ann.get("leaf_check_locked"):
        raise RuntimeError("The wrong-leaf check is not locked, so the evaluation set is not final.")
    verdicts = load_verdicts(_paths(config)["log"])
    return [r for r in gold_rows(config) if verdicts.get(r["name"]) == "correct"]


def verdict_digest(log_csv: Path) -> str:
    """SHA-256 of the latest verdict per image, sorted by name. Parsed first, so line endings don't matter."""
    return hashlib.sha256(json.dumps(sorted(load_verdicts(log_csv).items())).encode("utf-8")).hexdigest()


def categories(rows: list[dict], verdicts: dict[str, str], exclude_reasons: dict[str, str]) -> dict[str, str]:
    """image name -> key of CATEGORIES. A post-check exclusion reason (duplicate, collage) replaces
    a 'correct' verdict; wrong-leaf and not-a-leaf verdicts are kept as they are."""
    out = {}
    for r in rows:
        verdict = verdicts.get(r["name"], "pending")
        out[r["name"]] = exclude_reasons.get(r["name"], verdict) if verdict == "correct" else verdict
    return out


def count_categories(rows: list[dict], cats: dict[str, str]) -> dict[str, dict[str, int]]:
    """disease -> {category key: count}, plus a 'total' entry."""
    out: dict[str, dict[str, int]] = {"total": dict.fromkeys(CATEGORIES, 0)}
    for r in rows:
        out.setdefault(r["disease"], dict.fromkeys(CATEGORIES, 0))[cats[r["name"]]] += 1
        out["total"][cats[r["name"]]] += 1
    return out


def load_verdicts(log_csv: Path) -> dict[str, str]:
    """image name -> latest verdict."""
    if not log_csv.exists():
        return {}
    with open(log_csv, encoding="utf-8") as f:
        return {r["name"]: r["verdict"] for r in csv.DictReader(f)}


def first_open(order: list[str], verdicts: dict[str, str]) -> int:
    """Position of the first image without a verdict (len(order) if all are done)."""
    return next((i for i, name in enumerate(order) if name not in verdicts), len(order))


def _paths(config: dict, debug: bool = False) -> dict[str, Path]:
    ann = config["annotation"]
    root = Path(ann["out_dir"]) / ("leaf_check_debug" if debug else "leaf_check")
    return {"root": root, "items": root / "items", "order": root / "order.json",
            "masks": Path(config["data"]["leaf_masks_dir"]) / ("gold_debug" if debug else "gold"),
            "log": Path(ann["out_dir"]) / "leaf_check_log.csv"}


def _item_file(items: Path, pos: int) -> Path:
    return items / f"{pos:03d}.jpg"


# ---------------------------------------------------------------- step: prepare

def run_prepare(config: dict, config_path: str, debug: bool) -> None:
    """Find each gold leaf with the frozen rule; save the mask and an overlay; fix the shuffled order."""
    from PIL import Image

    from src.severity.sam2_model import load_sam2_predictor

    paths = _paths(config, debug)
    if not debug and paths["log"].exists():
        raise FileExistsError(f"{paths['log']} exists: the check has started, so the outlines are frozen.")
    rows = gold_rows(config)[:3] if debug else gold_rows(config)
    order = [r["name"] for r in rows]
    random.Random(config["seed"]).shuffle(order)
    by_name = {r["name"]: r for r in rows}
    for d in (paths["items"], paths["masks"]):
        d.mkdir(parents=True, exist_ok=True)
    for old in paths["items"].glob("*.jpg"):
        old.unlink()
    predictor = load_sam2_predictor(config)
    for pos, name in enumerate(order):
        row = by_name[name]
        img = _load_image(config, row)
        click = (int(row["click_x"]), int(row["click_y"]))
        predictor.set_image(img)
        leaf = leaf_from_click(predictor, click, config)
        Image.fromarray(leaf.astype(np.uint8) * 255).save(paths["masks"] / (Path(name).stem + ".png"))
        Image.fromarray(_overlay(img, leaf, click)).save(_item_file(paths["items"], pos), quality=92)
    paths["order"].write_text(json.dumps(order, indent=1), encoding="utf-8")
    exp_dir = create_experiment_dir("leaf_check_prepare" + ("_debug" if debug else ""), config_path)
    (exp_dir / "metrics.json").write_text(json.dumps({
        "n_images": len(order), "leaf_rule": config["sam2"]["leaf_rule"],
        "leaf_min_area_share": config["sam2"].get("leaf_min_area_share"),
        "checkpoint": config["sam2"]["checkpoint"], "masks_dir": str(paths["masks"]),
    }, indent=2), encoding="utf-8")
    print(f"{len(order)} gold leaves -> masks in {paths['masks']}, overlays in {paths['items']}; {exp_dir}")


# ---------------------------------------------------------------- step: serve

def build_app(config: dict):
    """Gradio check screen: one outline at a time, three verdicts, Back one. Saves after every answer."""
    import gradio as gr

    paths = _paths(config)
    order: list[str] = json.loads(paths["order"].read_text(encoding="utf-8"))

    def show(pos: int):
        done = load_verdicts(paths["log"])
        n_done = sum(name in done for name in order)
        if pos >= len(order):
            return None, f"## Finished: {n_done} / {len(order)} checked. You can close this tab.", pos
        prev = f" (your earlier answer here: **{VERDICTS[done[order[pos]]]}**)" if order[pos] in done else ""
        return (str(_item_file(paths["items"], pos)),
                f"### Image {pos + 1} of {len(order)}, {n_done} checked so far{prev}", pos)

    def vote(verdict: str, rater: str, pos: int):
        if config["annotation"].get("leaf_check_locked"):
            return None, "## The wrong-leaf check is locked. Verdicts can no longer be changed.", pos
        if pos < len(order):
            core.append_log(paths["log"], {"name": order[pos], "verdict": verdict, "rater": rater.strip(),
                                           "saved_at": core.now_iso()}, LOG_FIELDS)
            pos += 1
        return show(pos)

    with gr.Blocks(title="Wrong-leaf check") as demo:
        gr.Markdown(
            "# Wrong-leaf check\n"
            "The yellow dot is your gold click; the pink outline is the leaf SAM 2 found from it.\n"
            "- **Correct leaf**: the outline is the leaf you clicked.\n"
            "- **Wrong leaf**: the outline is mostly on a different object than the leaf you clicked, "
            "or covers several leaves or background.\n"
            "- **Not a leaf**: what you clicked is a spike, stem or anything else that isn't a leaf, "
            "however good the outline is.\n\n"
            "Wrong-leaf and not-a-leaf images are excluded from evaluation. Ratings can't be changed here.")
        pos = gr.State(0)
        rater = gr.Textbox(value=config["annotation"]["ui"]["default_rater"], label="Rater", scale=0)
        head = gr.Markdown()
        with gr.Row():
            buttons = {v: gr.Button(label, variant="primary" if v == "correct" else "stop")
                       for v, label in VERDICTS.items()}
            back = gr.Button("Back one")
        view = gr.Image(show_label=False, interactive=False, show_download_button=False, height=720)
        outs = [view, head, pos]
        demo.load(lambda: show(first_open(order, load_verdicts(paths["log"]))), None, outs)
        for v, btn in buttons.items():
            btn.click(lambda r, p, v=v: vote(v, r, p), [rater, pos], outs)
        back.click(lambda p: show(max(p - 1, 0)), [pos], outs)
    return demo


# ---------------------------------------------------------------- step: summary

def run_summary(config: dict) -> None:
    """Print, per disease, how many checked images are kept and how many are excluded for each reason.
    No severities are read or shown."""
    rows = checked_rows(config)
    cats = categories(rows, load_verdicts(_paths(config)["log"]), config["annotation"].get("gold_exclude_reasons", {}))
    counts = count_categories(rows, cats)
    keys = [k for k in CATEGORIES if k != "pending" or counts["total"]["pending"]]
    print("| disease | " + " | ".join(CATEGORIES[k] for k in keys) + " |")
    print("|---|" + "---:|" * len(keys))
    for disease, c in sorted(counts.items(), key=lambda kv: kv[0] == "total"):
        print(f"| {disease.replace('wheat ', '')} | " + " | ".join(str(c[k]) for k in keys) + " |")


# ---------------------------------------------------------------- step: sheet

def run_sheet(config: dict, out: Path = SHEET, cols: int = 6, tile: int = 400) -> None:
    """Contact sheet of every checked overlay in check order, numbered, with its latest verdict.
    Images excluded after the check show that reason (duplicate, collage) instead of "kept".
    A '?' marks images whose note in `NOTES` starts with BORDERLINE. No severities are read or shown."""
    import cv2

    paths = _paths(config)
    order: list[str] = json.loads(paths["order"].read_text(encoding="utf-8"))
    verdicts = load_verdicts(paths["log"])
    borderline: set[str] = set()
    if NOTES.exists():
        with open(NOTES, encoding="utf-8") as f:
            borderline = {r["name"] for r in csv.DictReader(f) if r["note"].startswith("BORDERLINE")}
    colours = {"correct": (0, 140, 0), "wrong": (0, 0, 210), "not_a_leaf": (200, 0, 160),
               "duplicate": (200, 110, 0), "collage": (200, 110, 0)}
    cats = categories(checked_rows(config), verdicts, config["annotation"].get("gold_exclude_reasons", {}))
    tiles = []
    for pos, name in enumerate(order):
        img = cv2.imread(str(_item_file(paths["items"], pos)))
        scale = tile / max(img.shape[:2])
        img = cv2.resize(img, (round(img.shape[1] * scale), round(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        canvas = np.full((tile + 44, tile + 10, 3), 255, np.uint8)
        canvas[: img.shape[0], : img.shape[1]] = img
        verdict = cats.get(name, "pending")
        label = f"{pos + 1}. {CATEGORIES[verdict].upper()}" + (" ?" if name in borderline else "")
        cv2.putText(canvas, label, (4, tile + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    colours.get(verdict, (90, 90, 90)), 2, cv2.LINE_AA)
        tiles.append(canvas)
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))
    print(f"Wrote {out} ({len(order)} images, {len(borderline)} marked borderline)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=["prepare", "serve", "summary", "sheet"])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--port", type=int, default=7863)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.step == "prepare":
        run_prepare(config, args.config, args.debug)
    elif args.step == "serve":
        build_app(config).launch(server_port=args.port)
    elif args.step == "sheet":
        run_sheet(config)
    else:
        run_summary(config)


if __name__ == "__main__":
    main()
