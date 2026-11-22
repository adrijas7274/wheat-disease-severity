"""Phase 8 (part): export the final SegFormer-B0 region model for phones and measure what quantisation costs.

Steps (outputs in a new experiments/<timestamp>_export/ folder and report/tables/export.md):
1. ONNX FP32 (opset 17, fixed 1x3x512x512 input, logits upsampled to 512x512 inside the graph).
2. ONNX INT8: dynamic (weights only) and static QDQ (weights + activations, calibrated on TRAINING images).
3. TFLite: NOT done yet (needs a separate TensorFlow environment and onnx2tf). The script merges a
   `tflite_results.json` from the run folder if one is ever added; the calibration images are saved (NHWC .npy).
4. Size on disk, CPU latency per image (model only, 1 image, median of N runs) and infected-region IoU on the
   clean TEST split (121 close-up images, pooled over pixels in the 512 px padded space, padding excluded) for
   every format, plus pixel agreement with PyTorch FP32. Test is only measured: nothing is chosen on it.

    python -m src.export [--debug] [--resume experiments/<dir>]
"""

import argparse
import json
import shutil
import time
from datetime import date
from pathlib import Path

import numpy as np

from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir
from src.utils.git import get_git_commit_hash

CHECKPOINT = "experiments/20261114_100055_segformer/best_model.pt"
TABLE = Path("report/tables/export.md")
SIZE = 512


def prepare(image: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(1x3xHxW float32 input, true mask, valid mask) with the evaluation transform."""
    from src.data.severity_transforms import build_transform

    out = build_transform(SIZE, train=False)(image=image, masks=[mask.astype(np.uint8), np.ones(image.shape[:2], np.uint8)])
    return out["image"].unsqueeze(0).numpy().astype(np.float32), np.asarray(out["masks"][0]) > 0, np.asarray(out["masks"][1]) > 0


def load_items(config: dict, split: str, limit: int | None) -> list[dict]:
    from PIL import Image

    from src.corruptions.cache import split_entries
    from src.models.inference import resize_mask

    items = []
    for e in split_entries(config, split)[:limit]:
        image = np.array(Image.open(e["image_path"]).convert("RGB"))
        mask = np.array(Image.open(e["mask_path"]).convert("L")) > 0
        if mask.shape != image.shape[:2]:
            mask = resize_mask(mask, image.shape)
        x, true, valid = prepare(image, mask)
        items.append({"name": e["name"], "x": x, "true": true, "valid": valid})
    return items


def export_onnx(model, path: Path) -> None:
    import torch

    torch.onnx.export(model, torch.zeros(1, 3, SIZE, SIZE), str(path), opset_version=17, input_names=["image"],
                      output_names=["logits"], do_constant_folding=True)


class _Calibration:
    """onnxruntime CalibrationDataReader over training images."""

    def __init__(self, xs: list[np.ndarray]):
        self.it = iter([{"image": x} for x in xs])

    def get_next(self):
        return next(self.it, None)


def quantise(fp32: Path, out_dir: Path, calib: list[np.ndarray]) -> dict[str, Path]:
    from onnxruntime.quantization import QuantFormat, QuantType, quantize_dynamic, quantize_static
    from onnxruntime.quantization.shape_inference import quant_pre_process

    pre = out_dir / "segformer_b0_pre.onnx"
    quant_pre_process(str(fp32), str(pre))
    dyn, sta = out_dir / "segformer_b0_int8_dynamic.onnx", out_dir / "segformer_b0_int8_static.onnx"
    # MatMul/Gemm only: a dynamically quantised Conv becomes ConvInteger, which the onnxruntime CPU provider does not
    # implement. The convolutions are covered by the static QDQ model.
    quantize_dynamic(str(pre), str(dyn), weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul", "Gemm"])
    quantize_static(str(pre), str(sta), _Calibration(calib), quant_format=QuantFormat.QDQ, per_channel=True,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8)
    pre.unlink()
    return {"ONNX INT8 dynamic": dyn, "ONNX INT8 static": sta}


def runner(path: Path, threads: int):
    """Callable x -> logits (1x2x512x512) for an .onnx or .tflite file."""
    if path.suffix == ".onnx":
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        sess = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        return lambda x: sess.run(None, {"image": x})[0]
    raise ValueError(path)


def evaluate(predict, items: list[dict], reference: list[np.ndarray] | None) -> tuple[dict, list[np.ndarray]]:
    """Pooled infected-class IoU against the masks, and pixel agreement (IoU) with the reference predictions."""
    inter = union = a_inter = a_union = 0
    preds = []
    for k, it in enumerate(items):
        pred = predict(it["x"])[0].argmax(axis=0).astype(bool) & it["valid"]
        preds.append(pred)
        true = it["true"] & it["valid"]
        inter += int((pred & true).sum())
        union += int((pred | true).sum())
        if reference is not None:
            a_inter += int((pred & reference[k]).sum())
            a_union += int((pred | reference[k]).sum())
    out = {"iou": inter / union if union else float("nan")}
    if reference is not None:
        out["agreement_iou"] = a_inter / a_union if a_union else 1.0
    return out, preds


def latency(predict, x: np.ndarray, runs: int) -> float:
    predict(x)
    predict(x)
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        predict(x)
        times.append(time.perf_counter() - t)
    return float(np.median(times) * 1000)


def format_report(rows: dict, info: dict) -> str:
    lines = [f"# Export of the region model for phones ({date.today().isoformat()})", "",
             f"Commit at run time: `{info['commit']}`. Generated by `python -m src.export`.", "",
             "Model: final SegFormer-B0 infected-region model (tag `final-v1`), fixed 1x3x512x512 input. IoU: infected class, clean "
             f"TEST split ({info['n_test']} close-up images), pooled over pixels in the 512 px padded space. Agreement: IoU between the "
             "format's predicted region and PyTorch FP32's. Latency: model only (no resize, no SAM 2, no colour rule), one image, median "
             f"of {info['runs']} runs on {info['cpu']} with {info['threads']} threads. INT8 static calibrated on {info['n_calib']} TRAINING images.", "",
             "| format | size, MB | CPU latency, ms | test IoU | IoU change vs PyTorch FP32 | agreement with FP32 |",
             "|---|---:|---:|---:|---:|---:|"]
    base = rows["PyTorch FP32"]["iou"]
    for name, r in rows.items():
        size = f"{r['size_mb']:.1f}" if r.get("size_mb") is not None else "-"
        lat = f"{r['latency_ms']:.0f}" if r.get("latency_ms") is not None else "-"
        agree = f"{r['agreement_iou']:.3f}" if "agreement_iou" in r else "-"
        lines.append(f"| {name} | {size} | {lat} | {r['iou']:.3f} | {r['iou'] - base:+.3f} | {agree} |")
    lines += ["", "PyTorch latency is the CPU PyTorch eager model (`torch.set_num_threads` as above). The phone also needs the "
              "leaf model: SAM 2.1 hiera-tiny (156 MB checkpoint; the whole demo pipeline takes about 2 s per photo on a laptop CPU) is too large "
              "for a 2-3 GB phone and would need a phone-sized promptable segmenter (e.g. a MobileSAM / EfficientSAM-class model), "
              "not evaluated here."]
    return "\n".join(lines) + "\n"


def main() -> None:
    import platform

    import torch

    from src.models.inference import load_baseline

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--debug", action="store_true", help="5 test and 5 calibration images, 3 runs; outputs only in the experiment folder")
    args = parser.parse_args()
    config = load_config(args.config)
    exp_dir = Path(args.resume) if args.resume else create_experiment_dir("export" + ("_debug" if args.debug else ""), args.config)
    torch.set_num_threads(args.threads)
    runs = 3 if args.debug else args.runs
    model = load_baseline("segformer", CHECKPOINT, "cpu")

    fp32 = exp_dir / "segformer_b0_fp32.onnx"
    if not fp32.exists():
        export_onnx(model, fp32)
    test = load_items(config, "test", 5 if args.debug else None)
    calib = [it["x"] for it in load_items(config, "train", 5 if args.debug else 100)]
    paths = {"ONNX FP32": fp32}
    if not (exp_dir / "segformer_b0_int8_static.onnx").exists():
        paths |= quantise(fp32, exp_dir, calib)
    else:
        paths |= {"ONNX INT8 dynamic": exp_dir / "segformer_b0_int8_dynamic.onnx", "ONNX INT8 static": exp_dir / "segformer_b0_int8_static.onnx"}
    np.save(exp_dir / "calibration_train.npy", np.concatenate(calib).transpose(0, 2, 3, 1))  # NHWC for onnx2tf

    with torch.no_grad():
        torch_predict = lambda x: model(torch.from_numpy(x)).numpy()  # noqa: E731
        rows = {"PyTorch FP32": {}}
        rows["PyTorch FP32"], ref = evaluate(torch_predict, test, None)
        rows["PyTorch FP32"] |= {"size_mb": Path(CHECKPOINT).stat().st_size / 1e6, "latency_ms": latency(torch_predict, test[0]["x"], runs)}
    for name, path in paths.items():
        predict = runner(path, args.threads)
        rows[name], _ = evaluate(predict, test, ref)
        rows[name] |= {"size_mb": path.stat().st_size / 1e6, "latency_ms": latency(predict, test[0]["x"], runs)}
        print(name, rows[name], flush=True)
    tfl = exp_dir / "tflite_results.json"
    if tfl.exists():  # written by src/export_tflite.py (TensorFlow environment)
        rows |= json.loads(tfl.read_text(encoding="utf-8"))
    info = {"commit": get_git_commit_hash(), "n_test": len(test), "n_calib": len(calib), "runs": runs, "threads": args.threads,
            "cpu": platform.processor() or platform.machine()}
    (exp_dir / "metrics.json").write_text(json.dumps({"rows": rows, "info": info}, indent=1), encoding="utf-8")
    np.save(exp_dir / "reference_test_preds.npy", np.stack(ref))
    out = exp_dir / TABLE.name if args.debug else TABLE
    out.write_text(format_report(rows, info), encoding="utf-8")
    shutil.copy(CHECKPOINT, exp_dir / "segformer_b0.pt") if not (exp_dir / "segformer_b0.pt").exists() else None
    print(f"Wrote {out}; {exp_dir}")


if __name__ == "__main__":
    main()
