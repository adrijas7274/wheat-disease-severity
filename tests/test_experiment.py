import json
from pathlib import Path

from src.utils.experiment import MetricLogger, create_experiment_dir


def test_create_experiment_dir_writes_meta(tmp_path: Path) -> None:
    exp_dir = create_experiment_dir("unit_test", root=tmp_path)

    assert exp_dir.exists()
    meta = json.loads((exp_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["name"] == "unit_test"
    assert "git_commit" in meta
    assert "config_file" not in meta


def test_create_experiment_dir_copies_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("crop: tomato\n", encoding="utf-8")

    exp_dir = create_experiment_dir("unit_test", config_path=config_path, root=tmp_path)

    assert (exp_dir / "config.yaml").read_text(encoding="utf-8") == "crop: tomato\n"


def test_metric_logger_save_roundtrip(tmp_path: Path) -> None:
    logger = MetricLogger(tmp_path)
    logger.log("miou", 0.42)
    logger.update({"dice": 0.5})

    out_path = logger.save()

    saved = json.loads(out_path.read_text(encoding="utf-8"))
    assert saved == {"miou": 0.42, "dice": 0.5}
