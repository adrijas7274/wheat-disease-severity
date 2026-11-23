"""Write app/web/policy.json: every frozen value the browser pipeline needs, read from the same Python sources as
final-v1, so the JavaScript port has no hand-copied constants.

Usage:
    python -m src.mobile.export_web_policy
"""

import json
from pathlib import Path

OUT = Path("app/web/policy.json")
MODELS = {"region": "segformer_b0_int8.onnx", "leaf_encoder": "efficient_sam_vitt_encoder_int8.onnx",
          "leaf_decoder": "efficient_sam_vitt_decoder_int8.onnx"}


def build(config_path: str = "configs/config.yaml", policy_path: str = "demo/final_policy.json") -> dict:
    from src.data.severity_transforms import IMAGENET_MEAN, IMAGENET_STD
    from src.mobile.export_leaf_models import sha256
    from src.mobile.leaf_finders import SAM_SIZE
    from src.severity import refinement as rf
    from src.severity.mask_coarseness_check import GREEN_LOWER, GREEN_UPPER
    from src.uncertainty import quality_gate as qg
    from src.uncertainty import scores as sc
    from src.utils.config import load_config

    config = load_config(config_path)
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    model_dir = OUT.parent / "models"
    return {
        "tag": "final-v1-mobile",
        "based_on": policy["tag"],
        "note": "final-v1 with SegFormer-B0 INT8 (dynamic) and EfficientSAM-Ti INT8 for the leaf. Levels and decisions are PLACEHOLDERS.",
        "models": {k: {"file": f"models/{v}", "sha256": sha256(model_dir / v)} for k, v in MODELS.items()},
        "max_long_side": policy["max_long_side"],
        "image_size": config["image"]["size"],
        "imagenet_mean": list(IMAGENET_MEAN), "imagenet_std": list(IMAGENET_STD),
        "leaf_max_side": SAM_SIZE,
        "leaf_rule": config["sam2"]["leaf_rule"], "leaf_min_area_share": config["sam2"]["leaf_min_area_share"],
        "disease_groups": rf.DISEASE_GROUPS,
        "colour_thresholds": policy["colour_thresholds"],
        "green_hsv": [GREEN_LOWER.tolist(), GREEN_UPPER.tolist()],
        "yellow_hsv": [rf.YELLOW_LOWER.tolist(), rf.YELLOW_UPPER.tolist()],
        "mildew_min_lightness": rf.MILDEW_MIN_LIGHTNESS,
        "gate_ranges": policy["gate_ranges"],
        "gate_long_side": qg.LONG_SIDE, "gate_gamma": qg.GAMMA, "jpeg_block": qg.BLOCK,
        "photometric_views": [list(v) for v in sc.PHOTOMETRIC_VIEWS], "photometric_gamma": sc.GAMMA,
        "uncertainty_threshold": policy["uncertainty_threshold"],
        "severity_thresholds": config["severity_thresholds"],
        "decision_mapping": config["decision_mapping"],
    }


def main() -> None:
    OUT.write_text(json.dumps(build(), indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
