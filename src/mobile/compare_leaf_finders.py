"""Phase 8 step 1: phone-sized leaf finders vs the frozen SAM 2 tiny leaf rule, on TUNING images only.

Sets (no gold image is opened; the script refuses any name in queues/gold.csv):
    rated   the 12 rated tuning images (tuning_exclude removed), with Adrija's stored clicks and ratings
    queue   the other tuning-queue images (Validation split), with the automatic click from SegFormer-B0

For each image and finder: leaf IoU with the SAM 2 leaf, severity with that leaf (same region, same colour rule,
no preprocessing, as in final-v1), its difference from the SAM 2 severity, the placeholder level, and on the rated
set the error against the rating. SAM 2 is the reference, not the truth.
Speed: encoder and decoder time with onnxruntime on this laptop's CPU (1 and 4 threads), at a 1024 px photo.

Usage:
    python -m src.mobile.compare_leaf_finders [--debug]
"""

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np

from src.mobile import leaf_finders as lf

FINDERS = ["sam2_tiny", "mobile_sam", "mobile_sam_int8", "efficient_sam", "efficient_sam_int8", "grabcut"]
COLOURS = {"sam2_tiny": (255, 220, 0), "mobile_sam_int8": (0, 220, 255), "efficient_sam_int8": (255, 60, 220),
           "grabcut": (255, 140, 0)}
SHEET_DIR = Path("report/figures/leaf_finders")
TABLE = Path("report/tables/leaf_finders.md")


def load_rows(config: dict, debug: bool) -> list[dict]:
    """Rated tuning rows (with click and rating) then the rest of the tuning queue; never gold."""
    from src.severity.leaf_mask import tuning_rows

    ann = Path(config["annotation"]["out_dir"])
    gold = {r["name"] for r in csv.DictReader(open(ann / "queues/gold.csv", encoding="utf-8"))}
    exclude = set(config["annotation"].get("tuning_exclude", []))
    rated = [r | {"set": "rated"} for r in tuning_rows(config)]
    rated_names = {r["name"] for r in rated}
    queue = [r | {"set": "queue"} for r in csv.DictReader(open(ann / "queues/tuning.csv", encoding="utf-8"))
             if r["name"] not in rated_names and r["name"] not in exclude]
    rows = rated + queue
    leaked = [r["name"] for r in rows if r["name"] in gold]
    if leaked:
        raise RuntimeError(f"gold images in the tuning rows: {leaked}")
    return rows[:4] + queue[:2] if debug else rows


def outline(img: np.ndarray, mask: np.ndarray, colour: tuple[int, int, int], width: int) -> None:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(img, contours, -1, colour, width)


def tile_row(image: np.ndarray, leaves: dict, click: tuple[int, int], rec: dict, height: int = 260) -> np.ndarray:
    """One sheet row: one panel per shown finder, each with its leaf outline, the tap and IoU / severity."""
    s = height / image.shape[0]
    small = cv2.resize(image, (max(1, round(image.shape[1] * s)), height), interpolation=cv2.INTER_AREA)
    small = cv2.resize(small, (min(small.shape[1], 360), height), interpolation=cv2.INTER_AREA) if small.shape[1] > 360 else small
    sx, sy = small.shape[1] / image.shape[1], small.shape[0] / image.shape[0]
    panels = []
    for name, colour in COLOURS.items():
        p = small.copy()
        m = cv2.resize(leaves[name].astype(np.uint8), small.shape[1::-1], interpolation=cv2.INTER_NEAREST)
        outline(p, m, colour, 2)
        cv2.circle(p, (round(click[0] * sx), round(click[1] * sy)), 5, (255, 0, 0), -1)
        r = rec["finders"][name]
        text = f"{name.replace('_int8', ' int8')}" if name == "sam2_tiny" else f"IoU {r['iou']:.2f}"
        text2 = f"sev {r['severity']:.1f}%" if r["severity"] is not None else "sev -"
        canvas = np.full((height + 34, 360, 3), 255, np.uint8)
        canvas[:height, :p.shape[1]] = p
        cv2.putText(canvas, text, (4, height + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(canvas, text2, (4, height + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        panels.append(canvas)
    row = np.hstack(panels)
    label = np.full((row.shape[0], 150, 3), 255, np.uint8)
    for i, line in enumerate([f"#{rec['index']} {rec['set']}", rec["disease"].replace("wheat ", "")[:20],
                              f"rating {rec['rating']}" if rec["rating"] is not None else ""]):
        cv2.putText(label, line, (4, 20 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    return np.hstack([label, row])


def save_sheet(rows: list[np.ndarray], out: Path) -> None:
    from PIL import Image

    header = np.full((40, rows[0].shape[1], 3), 255, np.uint8)
    for i, (name, colour) in enumerate(COLOURS.items()):
        x = 150 + 360 * i + 4
        cv2.rectangle(header, (x, 12), (x + 20, 28), colour, -1)
        cv2.putText(header, name, (x + 26, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.vstack([header, *rows])).quantize(colors=256).save(out, optimize=True)


def timing(images: list[np.ndarray], runs: int = 3) -> list[dict]:
    """Median ms per photo (long side 1024) for each finder; ONNX at 1 and 4 threads."""
    from src.severity.sam2_model import load_sam2_predictor
    from src.utils.config import load_config

    imgs = [cv2.resize(i, (round(i.shape[1] * 1024 / max(i.shape[:2])), round(i.shape[0] * 1024 / max(i.shape[:2]))))
            for i in images]
    out = []

    def med(f):
        f(imgs[0])  # warm-up
        ts = []
        for img in imgs:
            for _ in range(runs):
                t = time.perf_counter()
                f(img)
                ts.append(1000 * (time.perf_counter() - t))
        return float(np.median(ts))

    for threads in (1, 4):
        for name, cls, int8 in (("mobile_sam", lf.MobileSam, False), ("mobile_sam_int8", lf.MobileSam, True),
                                ("efficient_sam", lf.EfficientSam, False), ("efficient_sam_int8", lf.EfficientSam, True)):
            m = cls(int8=int8, threads=threads)
            st = m.embed(imgs[0])
            click = (imgs[0].shape[1] // 2, imgs[0].shape[0] // 2)
            out.append({"finder": name, "threads": threads, "encoder_ms": med(m.embed),
                        "decoder_ms": med(lambda im: m.candidates(st, click))})
    import torch

    cfg = load_config("configs/config.yaml")
    cfg["sam2"]["device"] = "cpu"
    for threads in (1, 4):
        torch.set_num_threads(threads)
        pred = load_sam2_predictor(cfg)
        pred.set_image(imgs[0])
        click = np.array([[imgs[0].shape[1] // 2, imgs[0].shape[0] // 2]], np.float32)
        with torch.inference_mode():
            enc = med(pred.set_image)
            dec = med(lambda im: pred.predict(point_coords=click, point_labels=np.array([1]), multimask_output=True))
        out.append({"finder": "sam2_tiny", "threads": threads, "encoder_ms": enc, "decoder_ms": dec})
    region = np.zeros(imgs[0].shape[:2], bool)
    region[400:600, 300:500] = True
    out.append({"finder": "grabcut", "threads": 1, "encoder_ms": 0.0,
                "decoder_ms": med(lambda im: lf.grabcut_leaf(im, (400, 500), region[: im.shape[0], : im.shape[1]]))})
    return out


def summarise(records: list[dict], subset: str | None) -> list[dict]:
    rows = []
    recs = [r for r in records if subset is None or r["set"] == subset]
    for name in FINDERS[1:]:
        iou = np.array([r["finders"][name]["iou"] for r in recs], float)
        d = np.array([abs(r["finders"][name]["severity"] - r["finders"]["sam2_tiny"]["severity"])
                      if r["finders"][name]["severity"] is not None and r["finders"]["sam2_tiny"]["severity"] is not None
                      else np.nan for r in recs], float)
        same = np.array([r["finders"][name]["level"] == r["finders"]["sam2_tiny"]["level"] for r in recs], float)
        err = np.array([abs(r["finders"][name]["severity"] - r["rating"]) for r in recs
                        if r["rating"] is not None and r["finders"][name]["severity"] is not None], float)
        rows.append({"finder": name, "n": len(recs), "iou_median": float(np.nanmedian(iou)),
                     "iou_below_0.5": int(np.sum(iou < 0.5)), "sev_diff_mean": float(np.nanmean(d)),
                     "sev_diff_median": float(np.nanmedian(d)), "sev_diff_max": float(np.nanmax(d)),
                     "same_level": float(same.mean()), "mae_vs_rating": float(err.mean()) if len(err) else None})
    return rows


def write_table(records: list[dict], times: list[dict], sizes: dict, run: Path, commit: str) -> None:
    from src.utils.config import load_config  # noqa: F401  (kept for symmetry with other report writers)

    rated = [r for r in records if r["set"] == "rated"]
    sam2_mae = np.mean([abs(r["finders"]["sam2_tiny"]["severity"] - r["rating"]) for r in rated
                        if r["finders"]["sam2_tiny"]["severity"] is not None]) if rated else float("nan")
    lines = [
        "# Phase 8 step 1: phone-sized leaf finders vs the frozen SAM 2 tiny rule (tuning images only)", "",
        f"Run `{run.as_posix()}`, commit `{commit}`. Reference = SAM 2.1 tiny + the frozen `min_area` rule (final-v1), "
        "**not ground truth**. Every SAM-style finder uses the same frozen rule on its 3 candidates. Severity uses the "
        "same SegFormer-B0 region and colour rule (no preprocessing), so only the leaf changes. No gold image was opened.", "",
        "## Agreement with the SAM 2 leaf", "",
    ]
    for subset, title in (("rated", f"Rated tuning images, Adrija's clicks (n = {len(rated)})"),
                          ("queue", f"Other tuning-queue images, automatic click (n = {sum(r['set'] == 'queue' for r in records)})"),
                          (None, f"All (n = {len(records)})")):
        lines += [f"### {title}", "", "| finder | leaf IoU, median | IoU < 0.5 | severity diff, mean / median / max (points) | same level | MAE vs rating |",
                  "|---|---:|---:|---|---:|---:|"]
        for s in summarise(records, subset):
            mae = f"{s['mae_vs_rating']:.1f}" if s["mae_vs_rating"] is not None and subset == "rated" else "–"
            lines.append(f"| {s['finder']} | {s['iou_median']:.2f} | {s['iou_below_0.5']} | {s['sev_diff_mean']:.1f} / "
                         f"{s['sev_diff_median']:.1f} / {s['sev_diff_max']:.1f} | {s['same_level']:.0%} | {mae} |")
        if subset == "rated":
            lines.append(f"| *sam2_tiny (reference)* | 1.00 | 0 | 0 | 100% | {sam2_mae:.1f} |")
        lines.append("")
    lines += ["## Size and speed (laptop CPU, onnxruntime; SAM 2 tiny in PyTorch; photo long side 1024 px)", "",
              "| finder | files | 1 thread: encoder + decoder (ms) | 4 threads: encoder + decoder (ms) |", "|---|---:|---:|---:|"]
    for name in FINDERS:
        t = {x["threads"]: x for x in times if x["finder"] == name}
        cell = lambda k: f"{t[k]['encoder_ms']:.0f} + {t[k]['decoder_ms']:.0f}" if k in t else "–"  # noqa: E731
        lines.append(f"| {name} | {sizes.get(name, '–')} | {cell(1)} | {cell(4)} |")
    lines += ["", "Times are medians on this laptop's CPU, not a phone; in a browser (onnxruntime-web, WebAssembly) "
              "expect them to be several times slower. GrabCut runs at 512 px with OpenCV (1 thread).", "",
              f"Contact sheets: `{(SHEET_DIR / 'rated.png').as_posix()}` (all rated images) and "
              f"`{(SHEET_DIR / 'queue_worst.png').as_posix()}` (the 12 queue images with the lowest MobileSAM INT8 IoU).", ""]
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_text("\n".join(lines), encoding="utf-8")


def file_sizes() -> dict:
    mb = lambda *names: sum((lf.MODEL_DIR / n).stat().st_size for n in names) / 1e6  # noqa: E731
    return {"sam2_tiny": f"{Path('data/checkpoints/sam2/sam2.1_hiera_tiny.pt').stat().st_size / 1e6:.0f} MB (PyTorch)",
            "mobile_sam": f"{mb('mobile_sam_encoder.onnx', 'mobile_sam_decoder.onnx'):.1f} MB",
            "mobile_sam_int8": f"{mb('mobile_sam_encoder_int8.onnx', 'mobile_sam_decoder_int8.onnx'):.1f} MB",
            "efficient_sam": f"{mb('efficient_sam_vitt_encoder.onnx', 'efficient_sam_vitt_decoder.onnx'):.1f} MB",
            "efficient_sam_int8": f"{mb('efficient_sam_vitt_encoder_int8.onnx', 'efficient_sam_vitt_decoder_int8.onnx'):.1f} MB",
            "grabcut": "0 (OpenCV; OpenCV.js ~9 MB in a browser)"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    import torch
    from PIL import Image

    from src.corruptions.cache import model_outputs
    from src.data.wheat_metadata import image_path
    from src.external.phase7 import cap_long_side
    from src.models.inference import load_baseline
    from src.severity import refinement as rf
    from src.severity.auto_click import click_from_region
    from src.severity.leaf_mask import leaf_from_click, mask_iou, select_leaf
    from src.severity.recheck_report import severity_level
    from src.severity.sam2_model import load_sam2_predictor
    from src.utils.config import load_config
    from src.utils.experiment import create_experiment_dir
    from src.utils.git import get_git_commit_hash

    torch.manual_seed(0)
    config = load_config(args.config)
    config["sam2"]["device"] = "cpu"
    policy = json.loads(Path("demo/final_policy.json").read_text(encoding="utf-8"))
    run = create_experiment_dir("leaf_finders_debug" if args.debug else "leaf_finders", args.config)
    device = torch.device("cpu")
    model = load_baseline(policy["model"]["architecture"], policy["model"]["checkpoint"], device)
    predictor = load_sam2_predictor(config)
    finders = {"mobile_sam": lf.MobileSam(False), "mobile_sam_int8": lf.MobileSam(True),
               "efficient_sam": lf.EfficientSam(False), "efficient_sam_int8": lf.EfficientSam(True)}
    rule, share = config["sam2"]["leaf_rule"], config["sam2"]["leaf_min_area_share"]
    plantseg = Path(config["data"]["plantseg_dir"])
    records, sheet_rated, queue_tiles, timing_imgs = [], [], [], []
    rows = load_rows(config, args.debug)
    for i, row in enumerate(rows, 1):
        raw = np.array(Image.open(image_path(plantseg, row)).convert("RGB"))
        image = cap_long_side(raw, policy["max_long_side"])
        out = model_outputs(model, image, np.zeros(image.shape[:2], bool), config["image"]["size"], device)
        region = out["masks"]["region"]
        if row["set"] == "rated":
            s = image.shape[1] / int(row["img_w"])
            click = (int(round(int(row["click_x"]) * s)), int(round(int(row["click_y"]) * s)))
        else:
            click = click_from_region(out["region_small"], image.shape)
        predictor.set_image(image)
        leaves = {"sam2_tiny": leaf_from_click(predictor, click, config)}
        for name, f in finders.items():
            masks, scores = f.candidates(f.embed(image), click)
            leaves[name] = masks[select_leaf(masks, scores, click, rule, share)]
        leaves["grabcut"] = lf.grabcut_leaf(image, click, region)
        group = rf.DISEASE_GROUPS[row["disease"]]
        thr = policy["colour_thresholds"][group]
        rec = {"index": i, "name": row["name"], "set": row["set"], "disease": row["disease"], "click": list(click),
               "rating": float(row["severity_pct"]) if row["set"] == "rated" else None, "finders": {}}
        for name, leaf in leaves.items():
            sev = rf.severity_pct(rf.refine_c1(region & leaf, image, group, thr), leaf) if leaf.any() else None
            sev = sev if sev is not None and np.isfinite(sev) else None
            rec["finders"][name] = {"iou": mask_iou(leaf, leaves["sam2_tiny"]), "leaf_share": float(leaf.mean()),
                                    "severity": sev, "level": severity_level(sev, config["severity_thresholds"]) if sev is not None else None}
        records.append(rec)
        tile = tile_row(image, leaves, click, rec)
        (sheet_rated if row["set"] == "rated" else queue_tiles).append((rec["finders"]["mobile_sam_int8"]["iou"], tile))
        if len(timing_imgs) < 5:
            timing_imgs.append(image)
        print(f"{i}/{len(rows)} {row['name'][:40]:40s} " + " ".join(f"{n}={r['iou']:.2f}" for n, r in rec["finders"].items()), flush=True)

    with open(run / "records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    times = timing(timing_imgs)
    (run / "timing.json").write_text(json.dumps(times, indent=1), encoding="utf-8")
    if not args.debug:
        save_sheet([t for _, t in sheet_rated], SHEET_DIR / "rated.png")
        worst = sorted(queue_tiles, key=lambda x: x[0])[:12]
        if worst:
            save_sheet([t for _, t in worst], SHEET_DIR / "queue_worst.png")
        write_table(records, times, file_sizes(), run, get_git_commit_hash())
    (run / "summary.json").write_text(json.dumps({"rated": summarise(records, "rated"), "queue": summarise(records, "queue"),
                                                  "all": summarise(records, None)}, indent=1), encoding="utf-8")
    print(f"run: {run}")


if __name__ == "__main__":
    main()
