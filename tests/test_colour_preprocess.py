import numpy as np
import pytest

from src.corruptions.corruptions import corrupt
from src.severity import colour_preprocess as cp


@pytest.fixture
def photo() -> np.ndarray:
    rng = np.random.default_rng(0)
    base = np.zeros((60, 80, 3), np.float32)
    base[..., 0], base[..., 1], base[..., 2] = 110, 130, 100
    base[20:40, 30:50] = (170, 130, 90)
    return np.clip(base + rng.normal(0, 4, base.shape), 0, 255).astype(np.uint8)


def _lin_means(img: np.ndarray) -> np.ndarray:
    return ((img.astype(np.float32) / 255) ** cp.GAMMA).reshape(-1, 3).mean(axis=0)


def test_gray_world_equalises_channel_means(photo):
    m = _lin_means(cp.gray_world(photo))
    assert m.max() / m.min() < 1.05


def test_white_balance_reduces_a_colour_cast(photo):
    cast = corrupt(photo, "colour_cast", 4, seed=42, image_id="a.jpg")
    for fn in (cp.gray_world, cp.shades_of_gray):
        before = np.abs(cast.astype(float) - photo).mean()
        after = np.abs(fn(cast).astype(float) - fn(photo)).mean()
        assert after < 0.5 * before


def test_exposure_normalisation_undoes_a_gain(photo):
    dark = corrupt(photo, "under_exposure", 3, seed=42, image_id="a.jpg")
    assert np.abs(cp.exposure(dark).astype(float) - cp.exposure(photo)).mean() < 0.3 * np.abs(dark.astype(float) - photo).mean()
    lin = (cp.exposure(photo).astype(np.float32) / 255) ** cp.GAMMA
    assert float((lin @ cp.LUMA).mean()) == pytest.approx(cp.EXPOSURE_TARGET, abs=0.02)


def test_denoise_reduces_sensor_noise(photo):
    noisy = corrupt(photo, "sensor_noise", 4, seed=42, image_id="a.jpg")
    flat = (slice(0, 15), slice(0, 20))
    assert cp.denoise(noisy)[flat].std() < noisy[flat].std()


def test_apply_order_identity_and_unknown_step(photo):
    assert cp.apply(photo, []) is photo
    assert np.array_equal(cp.apply(photo, ["denoise", "gray_world"]), cp.gray_world(cp.denoise(photo)))
    out = cp.apply(photo, ["gray_world", "exposure"])
    assert out.dtype == np.uint8 and out.shape == photo.shape
    with pytest.raises(ValueError):
        cp.apply(photo, ["sharpen"])
