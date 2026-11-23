"""Phase 8: the mobile pipeline in Python, the reference the browser (JavaScript) port is checked against.

Same steps and frozen values as final-v1 (`src.demo.pipeline`), with the two phone models:
    region  SegFormer-B0 INT8 (dynamic, MatMul/Gemm) ONNX, one pass (the final policy does not use flip TTA)
    leaf    EfficientSAM-Ti INT8 ONNX + the frozen `min_area` rule (Adrija's choice, experiments/LOG.md 2026-11-23)
Everything else (2048 px cap, gate, colour rule without preprocessing, photometric spread, placeholder levels and
decisions, `explain`) is the final-v1 code itself.

So: final-v1 vs this = the effect of the phone models; this vs the JavaScript port = porting error.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.demo.pipeline import explain
from src.mobile.leaf_finders import EfficientSam
from src.severity import refinement as rf
from src.uncertainty import quality_gate as qg
from src.uncertainty import scores as sc

SEGFORMER_INT8 = Path("app/web/models/segformer_b0_int8.onnx")
MODEL_DIR = Path("app/web/models")


@dataclass
class MobileResult:
    action: str
    severity: float | None
    level: str | None
    decision: str | None
    uncertainty: float
    failed_checks: list[str]
    features: dict
    leaf: np.ndarray
    region: np.ndarray
    lesion: np.ndarray


def segformer_region(session, image: np.ndarray, image_size: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """(region at the photo's size, region at the model's resolution without padding) from one ONNX pass,
    with exactly the final-v1 preprocessing (`build_transform(train=False)`)."""
    from src.data.severity_transforms import build_transform
    from src.models.inference import resize_mask

    out = build_transform(image_size, train=False)(image=image, masks=[np.ones(image.shape[:2], np.uint8)])
    x = out["image"].numpy()[None].astype(np.float32)
    logits = session.run(None, {"image": x})[0][0]
    pred = logits[1] > logits[0]  # argmax over 2 classes (ties -> background, as torch.argmax)
    valid = np.asarray(out["masks"][0]) > 0
    ys, xs = np.nonzero(valid)
    small = pred[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return resize_mask(small, image.shape), small


class MobilePipeline:
    """Loads the two ONNX models once; `analyse` runs one photo (already capped or not)."""

    def __init__(self, config: dict, policy: dict, threads: int = 4, model_dir: Path = MODEL_DIR):
        from src.mobile.leaf_finders import _session

        self.config, self.policy = config, policy
        self.region_session = _session(model_dir / "segformer_b0_int8.onnx", threads)
        self.leaf_model = EfficientSam(int8=True, threads=threads, model_dir=model_dir)

    def analyse(self, image: np.ndarray, disease: str, click: tuple[int, int]) -> MobileResult:
        from src.external.phase7 import cap_long_side
        from src.severity.leaf_mask import select_leaf
        from src.severity.recheck_report import severity_level

        p, cfg = self.policy, self.config
        h0 = image.shape[0]
        image = cap_long_side(image, p["max_long_side"])
        s = image.shape[0] / h0
        click = (round(click[0] * s), round(click[1] * s))
        region, _ = segformer_region(self.region_session, image, cfg["image"]["size"])
        masks, scores = self.leaf_model.candidates(self.leaf_model.embed(image), click)
        leaf = masks[select_leaf(masks, scores, click, cfg["sam2"]["leaf_rule"], cfg["sam2"]["leaf_min_area_share"])]
        group = rf.DISEASE_GROUPS[disease]
        thr = p["colour_thresholds"][group]

        def sev(picture: np.ndarray) -> float:
            return rf.severity_pct(rf.refine_c1(region & leaf, picture, group, thr), leaf)

        severity = sev(image)
        spread = sc.spread([severity] + [sev(v) for v in sc.photometric_views(image)])
        severity = severity if np.isfinite(severity) else None
        level = severity_level(severity, cfg["severity_thresholds"]) if severity is not None else None
        decision = cfg["decision_mapping"][level] if level else None
        feats = qg.features(image) | {"blockiness": qg.blockiness(image)}
        failed = qg.failed_checks(feats, p["gate_ranges"])
        action, _ = explain(failed, spread, float(p["uncertainty_threshold"]), level, decision, severity)
        lesion = rf.refine_c1(region & leaf, image, group, thr) & leaf
        return MobileResult(action, severity, level, decision, spread, failed, feats, leaf, region, lesion)


def load_policy(path: str | Path = "demo/final_policy.json") -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
