import numpy as np
import pytest

from src.corruptions import corruptions as cr


@pytest.fixture(scope="module")
def photo() -> np.ndarray:
    """Synthetic 'leaf' photo: smooth mid-grey-green gradient with fine texture and bright spots."""
    rng = np.random.default_rng(0)
    h, w = 240, 320
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.stack([70 + 40 * xx / w, 120 + 50 * yy / h, 60 + 30 * xx / w], axis=-1)
    texture = rng.normal(0, 12, (h, w, 1))
    img = base + texture
    img[60:90, 100:140] = (200, 150, 60)
    img[150:170, 200:260] = (235, 235, 225)
    return np.clip(img, 0, 255).astype(np.uint8)


def _diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


@pytest.mark.parametrize("name", sorted(cr.CORRUPTIONS))
def test_every_corruption_keeps_shape_and_dtype_and_changes_the_image(photo: np.ndarray, name: str):
    before = photo.copy()
    for level in range(1, cr.N_LEVELS + 1):
        out = cr.corrupt(photo, name, level, seed=42, image_id="a.jpg")
        assert out.shape == photo.shape and out.dtype == np.uint8
        assert _diff(out, photo) > 0
    assert np.array_equal(photo, before)  # input is never modified in place


@pytest.mark.parametrize("name", sorted(cr.CORRUPTIONS))
def test_same_inputs_give_the_same_output(photo: np.ndarray, name: str):
    a = cr.corrupt(photo, name, 3, seed=42, image_id="a.jpg")
    b = cr.corrupt(photo, name, 3, seed=42, image_id="a.jpg")
    assert np.array_equal(a, b)


@pytest.mark.parametrize("name", ["sensor_noise", "motion_blur", "combined"])
def test_random_corruptions_depend_on_seed_and_image_id(photo: np.ndarray, name: str):
    a = cr.corrupt(photo, name, 3, seed=42, image_id="a.jpg")
    assert not np.array_equal(a, cr.corrupt(photo, name, 3, seed=43, image_id="a.jpg"))
    assert not np.array_equal(a, cr.corrupt(photo, name, 3, seed=42, image_id="b.jpg"))


@pytest.mark.parametrize("name", sorted(cr.CORRUPTIONS))
def test_higher_level_is_further_from_the_clean_image(photo: np.ndarray, name: str):
    diffs = [_diff(cr.corrupt(photo, name, level, seed=42, image_id="a.jpg"), photo) for level in range(1, 6)]
    assert diffs == sorted(diffs) and diffs[-1] > diffs[0]


def test_level_zero_is_an_unchanged_copy(photo: np.ndarray):
    out = cr.corrupt(photo, "jpeg", 0, seed=42, image_id="a.jpg")
    assert np.array_equal(out, photo) and out is not photo


def test_combined_is_the_documented_chain(photo: np.ndarray):
    rng, dir_rng = cr.make_rng(42, "combined", 2, "a.jpg"), cr.make_rng(42, "combined", "direction", "a.jpg")
    expected = photo
    for name in cr.COMBINED_CHAIN:
        expected = cr.CORRUPTIONS[name](expected, 2, rng, dir_rng)
    assert cr.COMBINED_CHAIN == ("low_resolution", "sensor_noise", "jpeg")
    assert np.array_equal(cr.corrupt(photo, "combined", 2, seed=42, image_id="a.jpg"), expected)


def test_exposure_direction_and_clipping(photo: np.ndarray):
    over = cr.corrupt(photo, "over_exposure", 5, seed=42, image_id="a.jpg")
    under = cr.corrupt(photo, "under_exposure", 5, seed=42, image_id="a.jpg")
    assert over.mean() > photo.mean() > under.mean()
    assert (over == 255).mean() > (photo == 255).mean()


def test_blur_is_scaled_with_image_size(photo: np.ndarray):
    """A copy twice as large gets twice the blur, so both lose the same detail."""
    import cv2

    big = cv2.resize(photo, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
    small_out = cr.corrupt(photo, "gaussian_blur", 4, seed=42, image_id="a.jpg")
    big_out = cv2.resize(cr.corrupt(big, "gaussian_blur", 4, seed=42, image_id="a.jpg"), (photo.shape[1], photo.shape[0]),
                         interpolation=cv2.INTER_AREA)
    assert _diff(small_out, big_out) < 0.25 * _diff(small_out, photo)


def test_there_are_ten_corruptions_with_five_levels():
    assert len(cr.CORRUPTIONS) == 10
    assert all(len(v) == cr.N_LEVELS for v in cr.LEVELS.values())
    assert set(cr.LEVELS) == set(cr.CORRUPTIONS) - {"combined"}


@pytest.mark.parametrize("bad", [dict(name="fog", level=1), dict(name="jpeg", level=6), dict(name="jpeg", level=1.5)])
def test_bad_arguments_are_rejected(photo: np.ndarray, bad: dict):
    with pytest.raises(ValueError):
        cr.corrupt(photo, bad["name"], bad["level"], seed=42, image_id="a.jpg")


def test_non_uint8_image_is_rejected(photo: np.ndarray):
    with pytest.raises(ValueError):
        cr.corrupt(photo.astype(np.float32), "jpeg", 1, seed=42, image_id="a.jpg")


def test_direction_is_the_same_at_every_level(photo: np.ndarray):
    """Only the strength changes with the level: the cast colour is the same at levels 1 and 5."""
    shifts = []
    for level in (1, 5):
        out = cr.corrupt(photo, "colour_cast", level, seed=42, image_id="a.jpg").astype(float)
        shifts.append(np.sign(np.round(out.mean(axis=(0, 1)) - photo.mean(axis=(0, 1)), 1)))
    assert np.array_equal(shifts[0], shifts[1])
