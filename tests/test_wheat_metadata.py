from pathlib import Path

import pytest

from src.data.wheat_metadata import (
    detect_columns, filter_by_crop_and_disease, image_path, load_metadata_rows, mask_path,
)

HEADER = ["Name", "Index", "Plant", "Disease", "Resolution", "Label file", "Mask ratio", "URL", "License", "Split"]


def test_detect_columns_matches_expected_header() -> None:
    columns = detect_columns(HEADER)
    assert columns["name"] == "Name"
    assert columns["plant"] == "Plant"
    assert columns["disease"] == "Disease"
    assert columns["label_file"] == "Label file"
    assert columns["mask_ratio"] == "Mask ratio"
    assert columns["split"] == "Split"


def test_detect_columns_is_case_and_spacing_insensitive() -> None:
    header = ["image_name", "plant", "DISEASE", "resolution", "mask_file", "mask-ratio", "url", "licence", "SPLIT"]
    columns = detect_columns(header)
    assert columns["name"] == "image_name"
    assert columns["label_file"] == "mask_file"
    assert columns["license"] == "licence"


def test_detect_columns_raises_on_missing_field() -> None:
    header = ["Name", "Plant", "Disease"]
    with pytest.raises(ValueError, match="split"):
        detect_columns(header)


def test_load_metadata_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "Metadata.csv"
    csv_path.write_text(
        "Name,Index,Plant,Disease,Resolution,Label file,Mask ratio,URL,License,Split\n"
        "wheat_stripe_rust_1.jpg,0,Wheat,wheat stripe rust,640x480,wheat_stripe_rust_1.png,0.1,http://x,CC-BY-NC,Training\n",
        encoding="utf-8",
    )
    rows = load_metadata_rows(csv_path)
    assert len(rows) == 1
    assert rows[0]["plant"] == "Wheat"
    assert rows[0]["disease"] == "wheat stripe rust"
    assert rows[0]["split"] == "Training"


def test_filter_by_crop_and_disease() -> None:
    rows = [
        {"plant": "Wheat", "disease": "wheat stripe rust"},
        {"plant": "Wheat", "disease": "wheat head scab"},  # excluded disease
        {"plant": "wheat", "disease": "wheat leaf rust"},  # lowercase plant still matches
        {"plant": "Tomato", "disease": "tomato early blight"},  # wrong plant
    ]
    filtered = filter_by_crop_and_disease(rows, "wheat", ["wheat stripe rust", "wheat leaf rust"])
    assert filtered == [
        {"plant": "Wheat", "disease": "wheat stripe rust"},
        {"plant": "wheat", "disease": "wheat leaf rust"},
    ]


def test_image_and_mask_path() -> None:
    row = {"name": "wheat_stripe_rust_1.jpg", "label_file": "wheat_stripe_rust_1.png", "split": "Validation"}
    root = Path("data/raw/plantseg_v7/plantseg")
    assert image_path(root, row) == root / "images" / "val" / "wheat_stripe_rust_1.jpg"
    assert mask_path(root, row) == root / "annotations" / "val" / "wheat_stripe_rust_1.png"
