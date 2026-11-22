"""Experiment output folders and JSON metric logging.

Every training/eval run gets its own timestamped folder under experiments/,
holding a copy of the config it used, the git commit it ran at, and its
metrics — so any reported number can be traced back to exactly how it was produced.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.git import get_git_commit_hash

DEFAULT_EXPERIMENTS_ROOT = Path("experiments")


def create_experiment_dir(
    name: str,
    config_path: str | Path | None = None,
    root: str | Path = DEFAULT_EXPERIMENTS_ROOT,
) -> Path:
    """Create a timestamped experiment directory, e.g. experiments/20260101_120000_name/.

    Copies the config file (if given) into the directory and writes meta.json
    with the git commit hash, so the run is reproducible from its folder alone.
    """
    root = Path(root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir = root / f"{timestamp}_{name}"
    exp_dir.mkdir(parents=True, exist_ok=False)

    meta: dict[str, Any] = {
        "name": name,
        "timestamp": timestamp,
        "git_commit": get_git_commit_hash(),
    }
    if config_path is not None:
        config_path = Path(config_path)
        shutil.copy(config_path, exp_dir / config_path.name)
        meta["config_file"] = config_path.name

    (exp_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return exp_dir


class MetricLogger:
    """Accumulates metrics in memory and writes them to metrics.json on save()."""

    def __init__(self, exp_dir: str | Path) -> None:
        self.exp_dir = Path(exp_dir)
        self.metrics: dict[str, Any] = {}

    def log(self, key: str, value: Any) -> None:
        self.metrics[key] = value

    def update(self, values: dict[str, Any]) -> None:
        self.metrics.update(values)

    def save(self) -> Path:
        out_path = self.exp_dir / "metrics.json"
        out_path.write_text(json.dumps(self.metrics, indent=2), encoding="utf-8")
        return out_path
