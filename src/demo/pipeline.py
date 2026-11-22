"""The frozen final pipeline (tag `final-v1`) for one photo, a chosen disease and a tap on the leaf.

Same steps as the Phase 7 evaluation (`src.external.phase7.score_photo` and `decide`): photo capped at a
2048 px long side, SegFormer-B0 infected region, SAM 2 tiny leaf from the tap (the frozen leaf rule), the
disease group's colour rule with no preprocessing, the Phase 6 v2 quality gate, then the photometric-spread
uncertainty check at the 80% coverage target. The only difference from the evaluation is that the farmer's
tap replaces the automatic click, as in the gold annotation.

The policy values (gate ranges, uncertainty threshold, colour thresholds) are read from
`demo/final_policy.json`, exported once from the frozen runs by `python -m src.demo.export_policy`.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.severity import refinement as rf
from src.uncertainty import quality_gate as qg

POLICY_FILE = Path("demo/final_policy.json")
DISEASES = list(rf.DISEASE_GROUPS)
ACTION_TEXT = {"no_action": "no action", "monitor": "monitor the field", "treat": "treat", "treat_urgently": "treat urgently"}
CHECK_TEXT = {"sharpness": "it looks blurred", "noise": "it looks grainy (noisy)", "luma": "it is too dark or too bright",
              "clip_high": "parts are over-exposed (washed out)", "clip_low": "parts are under-exposed (too dark)",
              "blockiness": "it looks heavily compressed", "min_side": "it is too small"}


@dataclass
class Result:
    """Everything the demo shows for one photo."""
    action: str                      # "retake" | "consult" | "answer"
    reason: str                      # plain-English explanation
    severity: float | None           # % of the leaf, None when the leaf mask is empty
    level: str | None                # placeholder level: none / low / medium / high
    decision: str | None             # placeholder decision for the level
    uncertainty: float               # photometric spread, points
    uncertainty_threshold: float
    failed_checks: list[str] = field(default_factory=list)
    leaf: np.ndarray | None = None
    lesion: np.ndarray | None = None
    image: np.ndarray | None = None  # the (capped) photo the masks refer to


def explain(failed: list[str], score: float, threshold: float, level: str | None, decision: str | None,
            severity: float | None) -> tuple[str, str]:
    """(action, plain-English reason) from the gate result and the uncertainty score (pure)."""
    if failed:
        return "retake", "Please retake the photo: " + "; ".join(CHECK_TEXT.get(c, c) for c in failed) + "."
    if severity is None:
        return "retake", "Please retake the photo: no leaf was found where you tapped. Tap on the middle of the main leaf."
    if score > threshold:
        return "consult", (f"Consult an expert: the estimate is unstable. Small changes in brightness and colour move it by "
                           f"{score:.1f} points (the limit is {threshold:.1f}), so it should not be trusted.")
    return "answer", (f"Estimated severity {severity:.1f}% of the leaf, level '{level}'. Placeholder recommendation: "
                      f"{ACTION_TEXT.get(decision, decision)}. Levels and recommendations are PLACEHOLDERS, not validated advice.")


class Pipeline:
    """Loads the two models once; `analyse` runs one photo."""

    def __init__(self, config_path: str = "configs/config.yaml", policy_path: str | Path = POLICY_FILE, device: str = "cpu"):
        import torch

        from src.models.inference import load_baseline
        from src.severity.sam2_model import load_sam2_predictor
        from src.utils.config import load_config

        self.config = load_config(config_path)
        self.config["sam2"]["device"] = device
        self.policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
        self.device = torch.device(device)
        self.model = load_baseline(self.policy["model"]["architecture"], self.policy["model"]["checkpoint"], self.device)
        self.predictor = load_sam2_predictor(self.config)

    def analyse(self, image: np.ndarray, disease: str, click: tuple[int, int]) -> Result:
        """image: RGB uint8 at its original size; click: (x, y) in those pixels."""
        from src.external.phase7 import cap_long_side, score_photo
        from src.severity.recheck_report import severity_level

        h0 = image.shape[0]
        image = cap_long_side(image, self.policy["max_long_side"])
        scale = image.shape[0] / h0
        click = (round(click[0] * scale), round(click[1] * scale))
        group = rf.DISEASE_GROUPS[disease]
        p = self.policy
        rec = score_photo(image, self.model, self.predictor, self.config, {group: p["colour_steps"][group]},
                          {group: p["colour_thresholds"][group]}, [group], self.device, click=click, return_masks=True)
        g = rec["groups"][group]
        sev = g["severity"] if g["severity"] is not None and np.isfinite(g["severity"]) else None
        level = severity_level(sev, self.config["severity_thresholds"]) if sev is not None else None
        decision = self.config["decision_mapping"][level] if level else None
        failed = qg.failed_checks(rec["features"], p["gate_ranges"])
        score, thr = float(g[p["policy_score"]]), float(p["uncertainty_threshold"])
        action, reason = explain(failed, score, thr, level, decision, sev)
        return Result(action, reason, sev, level, decision, score, thr, failed,
                      rec["masks"]["leaf"], rec["masks"]["lesion"][group], image)
