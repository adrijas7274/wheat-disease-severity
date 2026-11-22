from pathlib import Path

from src.data.build_tag_review_sheets import build_sheet


def test_build_sheet_creates_file(tiny_config: dict, tmp_path: Path) -> None:
    rows = [
        {"name": "stripe_1.jpg", "plant": "Wheat", "disease": "wheat stripe rust",
         "split": "Training", "label_file": "stripe_1.png", "tag": "close_up"},
    ]
    out_path = tmp_path / "sheet.png"

    build_sheet(tiny_config, rows, "test sheet", out_path)

    assert out_path.exists()


def test_build_sheet_empty_rows(tiny_config: dict, tmp_path: Path) -> None:
    out_path = tmp_path / "sheet.png"
    build_sheet(tiny_config, [], "empty", out_path)
    assert out_path.exists()
