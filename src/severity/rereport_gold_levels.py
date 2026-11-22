"""Re-report level and decision agreement of the single gold evaluation with the current level mapping.

Gold is **not** re-scored: this reads the per-image severities saved by the one
gold run (`experiments/<...>_gold_evaluation/per_image.json`) and only re-bins
them with the levels and decision mapping now in the config (changed on
2026-11-14, see `configs/config.yaml`). The MAE values cannot change. The
original report, `report/tables/gold_evaluation.md`, is left as it is.

Usage:
    python -m src.severity.rereport_gold_levels --config configs/config.yaml --run experiments/<...>_gold_evaluation
"""

import argparse
import json
from datetime import date
from pathlib import Path

from src.severity import evaluate_gold as eg
from src.utils.config import load_config

TABLE = Path("report/tables/gold_levels_v2.md")


def format_report(per_image: list[dict], config: dict, run: str) -> str:
    t, limit = config["severity_thresholds"], config["severity_method"]["resolution_limit"]
    sens = config["annotation"].get("gold_sensitivity_without") or {}
    lines = [f"# Gold level and decision agreement with the corrected level mapping ({date.today().isoformat()})", "",
             f"Re-binned from the single gold run `{run}`; no image was scored again and the MAE values are unchanged "
             "(`report/tables/gold_evaluation.md`).", "",
             f"**PLACEHOLDER levels and mapping** (not validated against an agronomy source): none = 0%, low below "
             f"{100 * t['low_max']:g}%, medium below {100 * t['medium_max']:g}%, high above; decisions "
             f"{config['decision_mapping']}. A rating within {limit} points of a threshold (the resolution limit) can change "
             "level from rating noise alone.", ""]
    sets = [(f"All {len(per_image)} images", per_image)]
    left_out = [n for n in sens.get("names", []) if any(r["name"] == n for r in per_image)]
    if left_out:
        kept = [r for r in per_image if r["name"] not in left_out]
        sets.append((f"Without {', '.join(f'`{n}`' for n in left_out)} ({len(kept)} images)", kept))
    for title, rows in sets:
        summary = eg.summarise(rows, config)
        lines += [f"## {title}", ""] + eg._agreement_lines(summary) + ["", "Level confusion (rating level -> method level: count):", ""]
        lines += [f"- {m}: " + "; ".join(f"{a} -> {b}: {c}" for a, row in sorted(s["level_confusion_rating_then_method"].items())
                                         for b, c in sorted(row.items())) for m, s in summary.items()]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    per_image = json.loads((Path(args.run) / "per_image.json").read_text(encoding="utf-8"))
    report = format_report(per_image, config, Path(args.run).as_posix())
    TABLE.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
