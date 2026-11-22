"""YAML config loading."""

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file into a plain dict.

    Raises FileNotFoundError if the path doesn't exist and ValueError if the
    file is empty, so a missing/blank config fails loudly instead of letting
    code silently fall back to defaults.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if config is None:
        raise ValueError(f"Config file is empty: {path}")
    return config
