from pathlib import Path

import pytest
import yaml

from src.utils.config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_config_reads_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({"crop": "tomato", "seed": 42}), encoding="utf-8")

    config = load_config(config_path)

    assert config["crop"] == "tomato"
    assert config["seed"] == 42


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")


def test_load_config_empty_file_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "empty.yaml"
    config_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(config_path)


def test_real_config_has_required_keys() -> None:
    config = load_config(REPO_ROOT / "configs" / "config.yaml")

    assert "crop" in config
    assert "seed" in config
    assert "severity_thresholds" in config
    assert "decision_mapping" in config
