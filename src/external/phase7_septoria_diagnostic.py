"""Phase 7 diagnostic (not tuning): septoria photos with the frozen phase3-method-v1 colour stage.

The final pipeline (Phase 5 colour stage) estimates exactly 0% on 94% of the Mendeley septoria photos.
This re-runs the same photos with the Phase 3 colour stage (no preprocessing, necrotic threshold 15)
to see whether the Phase 5 preprocessing causes the misses. Nothing is chosen or changed from it.

Usage: python -m src.external.phase7_septoria_diagnostic --run experiments/<phase7 run>
"""

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from src.external import phase7 as p7
from src.utils.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase7_external.yaml")
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    import torch
    from PIL import Image

    from src.models.inference import load_baseline
    from src.severity.sam2_model import load_sam2_predictor

    config = load_config(args.config)
    exp = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    entries, _ = p7.list_mendeley(Path(exp["mendeley"]["dir"]), exp["mendeley"]["classes"])
    entries = [e for e in entries if e["label"] == "wheat septoria blotch"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_baseline(exp["model"]["architecture"], exp["model"]["checkpoint"], device)
    predictor = load_sam2_predictor(config)
    out = Path(args.run) / "septoria_phase3_colour_stage.jsonl"
    rows = []
    for k, e in enumerate(entries, 1):
        image = p7.cap_long_side(np.array(Image.open(e["path"]).convert("RGB")), exp["mendeley"]["max_long_side"])
        rec = p7.score_photo(image, model, predictor, config, [], {"necrotic": 15}, ["necrotic"], device)
        rows.append({"name": e["name"], "severity": rec["groups"]["necrotic"]["severity"]})
        print(f"[septoria] {k}/{len(entries)}", flush=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    sev = np.array([r["severity"] for r in rows], dtype=float)
    print(json.dumps({"n": len(sev), "zero": float((sev == 0).mean()), "detected": float((sev > 0).mean()),
                      "median": float(np.median(sev)), "p90": float(np.percentile(sev, 90))}))


if __name__ == "__main__":
    main()
