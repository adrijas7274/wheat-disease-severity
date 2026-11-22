from pathlib import Path

import numpy as np
from PIL import Image

from src.severity.mask_coarseness_check import compute_table, format_table, healthy_fraction_in_mask


def _save_bgr(path: Path, rgb: tuple[int, int, int], size: tuple[int, int] = (40, 40)) -> None:
    import cv2

    arr = np.full((size[1], size[0], 3), rgb[::-1], dtype=np.uint8)  # RGB -> BGR for cv2
    cv2.imwrite(str(path), arr)


def test_healthy_fraction_all_green_in_mask(tmp_path: Path) -> None:
    img_path = tmp_path / "img.jpg"
    _save_bgr(img_path, (60, 180, 60))  # solid healthy green
    mask_path = tmp_path / "mask.png"
    Image.fromarray(np.ones((40, 40), dtype=np.uint8)).save(mask_path)  # whole image masked

    frac = healthy_fraction_in_mask(img_path, mask_path)

    assert frac == 1.0


def test_healthy_fraction_all_red_in_mask(tmp_path: Path) -> None:
    img_path = tmp_path / "img.jpg"
    _save_bgr(img_path, (180, 40, 40))  # reddish-brown lesion colour, not green
    mask_path = tmp_path / "mask.png"
    Image.fromarray(np.ones((40, 40), dtype=np.uint8)).save(mask_path)

    frac = healthy_fraction_in_mask(img_path, mask_path)

    assert frac == 0.0


def test_healthy_fraction_half_and_half(tmp_path: Path) -> None:
    img_path = tmp_path / "img.jpg"
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[:, :20] = (60, 180, 60)[::-1]  # green half (BGR)
    arr[:, 20:] = (180, 40, 40)[::-1]  # red half (BGR)
    import cv2
    cv2.imwrite(str(img_path), arr)
    mask_path = tmp_path / "mask.png"
    Image.fromarray(np.ones((40, 40), dtype=np.uint8)).save(mask_path)  # whole image masked

    frac = healthy_fraction_in_mask(img_path, mask_path)

    assert abs(frac - 0.5) < 0.05


def test_healthy_fraction_empty_mask_returns_none(tmp_path: Path) -> None:
    img_path = tmp_path / "img.jpg"
    _save_bgr(img_path, (60, 180, 60))
    mask_path = tmp_path / "mask.png"
    Image.fromarray(np.zeros((40, 40), dtype=np.uint8)).save(mask_path)

    assert healthy_fraction_in_mask(img_path, mask_path) is None


def test_compute_table_and_format(tiny_config: dict) -> None:
    results = compute_table(tiny_config)
    diseases = {r["disease"] for r in results}
    assert diseases == set(tiny_config["disease_classes"])

    table_md = format_table(results)
    assert "mean healthy frac in mask" in table_md
    for disease in tiny_config["disease_classes"]:
        assert disease in table_md
