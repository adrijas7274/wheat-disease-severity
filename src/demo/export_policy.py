"""Export the frozen final-v1 policy values to `demo/final_policy.json` (small, no experiment folders needed).

Reads the Phase 7 JIC config (= the final pipeline), the re-fitted Phase 6 v2 run it points to, and the Phase 5 v2
colour stage. Fails if the policy score is not a raw score (the demo does not ship a classifier).

    python -m src.demo.export_policy
"""

import json
from pathlib import Path

import yaml

from src.demo.pipeline import POLICY_FILE

FINAL_EXPERIMENT = Path("configs/experiments/phase7_jic.yaml")
COVERAGE = "0.8"


def build() -> dict:
    from src.uncertainty import phase6 as p6

    exp = yaml.safe_load(FINAL_EXPERIMENT.read_text(encoding="utf-8"))
    v2_exp = yaml.safe_load(Path(exp["phase6_v2_experiment"]).read_text(encoding="utf-8"))
    base_exp = yaml.safe_load(Path(v2_exp["v1_experiment"]).read_text(encoding="utf-8"))
    metrics = json.loads((Path(exp["phase6_v2_run"]) / "metrics.json").read_text(encoding="utf-8"))
    if metrics["policy_score"] not in p6.RAW_SCORES:
        raise SystemExit(f"Policy score {metrics['policy_score']} needs a classifier; not supported by the demo")
    steps, thresholds = p6.colour_stage(base_exp)
    return {"tag": "final-v1", "source_run": exp["phase6_v2_run"], "model": exp["model"],
            "max_long_side": exp["mendeley"]["max_long_side"], "colour_steps": steps, "colour_thresholds": thresholds,
            "gate_ranges": metrics["gate"]["ranges"], "policy_score": metrics["policy_score"], "coverage_target": float(COVERAGE),
            "uncertainty_threshold": metrics["thresholds"][COVERAGE]}


def main() -> None:
    POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
    POLICY_FILE.write_text(json.dumps(build(), indent=1), encoding="utf-8")
    print(f"Wrote {POLICY_FILE}")


if __name__ == "__main__":
    main()
