"""Phase 8 parity test: the browser (JavaScript) pipeline vs Python, on the clean test split (121 close-up images).

Three pipelines on the same capped photo and the same tap (the final-v1 automatic click: deepest point of the
largest region predicted by the PyTorch SegFormer-B0, as in Phases 4-7):
    final-v1     Python, PyTorch SegFormer-B0 + SAM 2 tiny (src.demo.pipeline)        -> "mobile version vs final-v1"
    mobile_py    Python, SegFormer INT8 ONNX + EfficientSAM-Ti INT8 (pipeline_ref)   -> "porting error" reference
    js           the JavaScript port in Node (onnxruntime-web, WebAssembly, 1 thread)
The test split was not used to choose or tune anything in the mobile version.

Usage:
    python -m src.mobile.parity prepare [--debug]     # exports photos + Python results to data/mobile_parity/
    node app/parity/run_parity.mjs data/mobile_parity  # JavaScript results
    python -m src.mobile.parity compare               # table report/tables/mobile_parity.md
"""

import argparse
import json
from pathlib import Path

import numpy as np

DIR = Path("data/mobile_parity")
TABLE = Path("report/tables/mobile_parity.md")
ACTIONS = ("answer", "consult", "retake")


def prepare(debug: bool) -> None:
    import torch
    from PIL import Image

    from src.corruptions.benchmark import test_entries
    from src.corruptions.cache import model_outputs
    from src.demo.pipeline import Pipeline
    from src.external.phase7 import cap_long_side
    from src.mobile.pipeline_ref import MobilePipeline, load_policy
    from src.severity.auto_click import click_from_region
    from src.utils.config import load_config

    torch.manual_seed(0)
    config = load_config("configs/config.yaml")
    policy = load_policy()
    final = Pipeline(device="cpu")
    mobile = MobilePipeline(config, policy)
    entries = test_entries(config)[:4] if debug else test_entries(config)
    (DIR / "inputs").mkdir(parents=True, exist_ok=True)
    (DIR / "py_masks").mkdir(exist_ok=True)
    index, results = [], []
    for i, e in enumerate(entries):
        image = cap_long_side(np.array(Image.open(e["image_path"]).convert("RGB")), policy["max_long_side"])
        out = model_outputs(final.model, image, np.zeros(image.shape[:2], bool), config["image"]["size"], final.device)
        click = click_from_region(out["region_small"], image.shape)
        f = final.analyse(image, e["disease"], click)
        m = mobile.analyse(image, e["disease"], click)
        (DIR / "inputs" / f"{i}.rgb").write_bytes(np.ascontiguousarray(image).tobytes())
        np.save(DIR / "py_masks" / f"{i}_mobile_region.npy", np.packbits(m.region))
        np.save(DIR / "py_masks" / f"{i}_mobile_leaf.npy", np.packbits(m.leaf))
        np.save(DIR / "py_masks" / f"{i}_final_leaf.npy", np.packbits(f.leaf))
        index.append({"i": i, "name": e["name"], "disease": e["disease"], "w": image.shape[1], "h": image.shape[0],
                      "click": [int(click[0]), int(click[1])]})
        results.append({"i": i, "name": e["name"], "disease": e["disease"],
                        "final": {"action": f.action, "severity": f.severity, "level": f.level, "decision": f.decision,
                                  "uncertainty": f.uncertainty, "failed": f.failed_checks},
                        "mobile_py": {"action": m.action, "severity": m.severity, "level": m.level, "decision": m.decision,
                                      "uncertainty": m.uncertainty, "failed": m.failed_checks, "features": m.features}})
        print(f"{i + 1}/{len(entries)} {e['name'][:40]} final={f.action}/{f.severity} mobile={m.action}/{m.severity}", flush=True)
    (DIR / "inputs" / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in index), encoding="utf-8")
    (DIR / "py_results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in results), encoding="utf-8")


def _num(x) -> float:
    return float("nan") if x is None else float(x)


def agreement(a: list[dict], b: list[dict]) -> dict:
    """Agreement of pipeline b with pipeline a over the same images (dicts with action, severity, level, ...)."""
    both = [(x, y) for x, y in zip(a, b) if x["severity"] is not None and y["severity"] is not None]
    d = np.array([abs(x["severity"] - y["severity"]) for x, y in both])
    u = np.array([abs(_num(x["uncertainty"]) - _num(y["uncertainty"])) for x, y in zip(a, b)])
    return {
        "n": len(a), "n_both_severity": len(both),
        "sev_diff_mean": float(d.mean()) if len(d) else float("nan"),
        "sev_diff_median": float(np.median(d)) if len(d) else float("nan"),
        "sev_diff_p95": float(np.percentile(d, 95)) if len(d) else float("nan"),
        "sev_diff_max": float(d.max()) if len(d) else float("nan"),
        "within_1pt": float((d <= 1).mean()) if len(d) else float("nan"),
        "same_level": float(np.mean([x["level"] == y["level"] for x, y in zip(a, b)])),
        "same_decision": float(np.mean([x["decision"] == y["decision"] for x, y in zip(a, b)])),
        "same_gate": float(np.mean([bool(x["failed"]) == bool(y["failed"]) for x, y in zip(a, b)])),
        "same_failed_checks": float(np.mean([sorted(x["failed"]) == sorted(y["failed"]) for x, y in zip(a, b)])),
        "same_action": float(np.mean([x["action"] == y["action"] for x, y in zip(a, b)])),
        "uncertainty_diff_mean": float(np.nanmean(u)),
    }


def mask_ious(idx: list[dict]) -> dict:
    """IoU of the JavaScript region and leaf with the Python mobile reference, and of the mobile leaf with SAM 2."""
    out = {"region_js_vs_py": [], "leaf_js_vs_py": [], "leaf_mobile_vs_final": []}
    for r in idx:
        n = r["w"] * r["h"]
        py = {k: np.unpackbits(np.load(DIR / "py_masks" / f"{r['i']}_{k}.npy"))[:n].astype(bool)
              for k in ("mobile_region", "mobile_leaf", "final_leaf")}
        js = {k: np.fromfile(DIR / "js_masks" / f"{r['i']}_{k}.bin", np.uint8).astype(bool) for k in ("region", "leaf")}
        for key, a, b in (("region_js_vs_py", js["region"], py["mobile_region"]), ("leaf_js_vs_py", js["leaf"], py["mobile_leaf"]),
                          ("leaf_mobile_vs_final", py["mobile_leaf"], py["final_leaf"])):
            u = (a | b).sum()
            out[key].append(float((a & b).sum() / u) if u else 1.0)
    return {k: {"median": float(np.median(v)), "min": float(np.min(v)), "below_0.9": int(np.sum(np.array(v) < 0.9))} for k, v in out.items()}


def rates(rows: list[dict]) -> dict:
    return {a: float(np.mean([r["action"] == a for r in rows])) for a in ACTIONS}


def compare() -> None:
    from src.utils.git import get_git_commit_hash

    idx = [json.loads(l) for l in (DIR / "inputs" / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    py = {r["i"]: r for r in map(json.loads, (DIR / "py_results.jsonl").read_text(encoding="utf-8").splitlines())}
    js = {r["i"]: r for r in map(json.loads, (DIR / "js_results.jsonl").read_text(encoding="utf-8").splitlines())}
    ids = [r["i"] for r in idx if r["i"] in js]
    final = [py[i]["final"] for i in ids]
    mpy = [py[i]["mobile_py"] for i in ids]
    mjs = [js[i] for i in ids]
    feat_diff = {k: float(np.max([abs(py[i]["mobile_py"]["features"][k] - js[i]["features"][k]) / max(abs(py[i]["mobile_py"]["features"][k]), 1e-9)
                                  for i in ids])) for k in ("sharpness", "noise", "luma", "clip_high", "clip_low", "blockiness", "min_side")}
    ms = {k: float(np.median([js[i]["ms"][k] for i in ids])) for k in ("gate", "region", "encoder", "decoder", "colour", "total")}
    summary = {"mobile_js_vs_final": agreement(final, mjs), "mobile_py_vs_final": agreement(final, mpy),
               "js_vs_mobile_py": agreement(mpy, mjs), "masks": mask_ious(idx), "rates": {"final": rates(final),
               "mobile_py": rates(mpy), "mobile_js": rates(mjs)}, "feature_max_rel_diff": feat_diff, "node_ms_median": ms}
    (DIR / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    def row(name: str, s: dict) -> str:
        return (f"| {name} | {s['n_both_severity']} | {s['sev_diff_mean']:.2f} / {s['sev_diff_median']:.2f} / {s['sev_diff_p95']:.1f} / "
                f"{s['sev_diff_max']:.1f} | {s['within_1pt']:.0%} | {s['same_level']:.0%} | {s['same_decision']:.0%} | "
                f"{s['same_gate']:.0%} | {s['same_action']:.0%} |")

    a = summary
    lines = [
        "# Mobile version (final-v1-mobile): parity with the Python pipelines", "",
        f"Clean test split, {len(ids)} close-up images, the final-v1 automatic click as the tap. Commit `{get_git_commit_hash()}`. "
        "Nothing in the mobile version was chosen or tuned on these images. Levels and decisions are PLACEHOLDERS.", "",
        "- **final-v1**: Python, PyTorch SegFormer-B0 + SAM 2.1 tiny (the frozen pipeline).",
        "- **mobile (Python)**: same code, SegFormer-B0 INT8 + EfficientSAM-Ti INT8 (ONNX).",
        "- **mobile (browser)**: the JavaScript port (`app/web/js/pipeline.js`) with onnxruntime-web 1.20.1 (WebAssembly, 1 thread), run in Node.", "",
        "## Agreement", "",
        "| comparison | images with a severity in both | severity difference, points: mean / median / 95th pct / max | within 1 point | same level | same decision | same gate result | same action (answer / consult / retake) |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
        row("**mobile (browser) vs final-v1**: the mobile version's numbers", a["mobile_js_vs_final"]),
        row("mobile (Python) vs final-v1: effect of the phone models", a["mobile_py_vs_final"]),
        row("mobile (browser) vs mobile (Python): porting error", a["js_vs_mobile_py"]), "",
        "## What each pipeline answers", "",
        "| pipeline | answer | consult an expert | retake |", "|---|---:|---:|---:|",
        *[f"| {n} | {r['answer']:.0%} | {r['consult']:.0%} | {r['retake']:.0%} |" for n, r in
          (("final-v1", a["rates"]["final"]), ("mobile (Python)", a["rates"]["mobile_py"]), ("mobile (browser)", a["rates"]["mobile_js"]))], "",
        "## Masks", "",
        "| masks | median IoU | lowest IoU | images below 0.9 |", "|---|---:|---:|---:|",
        *[f"| {k.replace('_', ' ')} | {v['median']:.3f} | {v['min']:.3f} | {v['below_0.9']} |" for k, v in a["masks"].items()], "",
        "Gate features, largest relative difference browser vs Python: " +
        ", ".join(f"{k} {v:.1e}" for k, v in feat_diff.items()) + ".", "",
        "## Speed of the browser pipeline (Node, WebAssembly, 1 thread, laptop CPU; median ms per photo)", "",
        "| gate | region | leaf encoder | leaf decoder | colour rule + uncertainty | total |", "|---:|---:|---:|---:|---:|---:|",
        f"| {ms['gate']:.0f} | {ms['region']:.0f} | {ms['encoder']:.0f} | {ms['decoder']:.0f} | {ms['colour']:.0f} | {ms['total']:.0f} |", "",
        "Phone speed is measured separately (fallback rule: more than 10 s per photo -> MobileSAM INT8).", "",
    ]
    TABLE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["prepare", "compare"])
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    prepare(args.debug) if args.step == "prepare" else compare()


if __name__ == "__main__":
    main()
