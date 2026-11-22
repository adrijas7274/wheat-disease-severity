"""Phone-realistic image corruptions for the Phase 4 benchmark.

Ten corruption types, five levels each (1 = mild, 5 = severe), applied on the
fly to an RGB uint8 image. Level 0 returns the image unchanged.

    gaussian_blur    out-of-focus / soft lens
    motion_blur      hand shake (random direction)
    defocus_blur     disk-shaped blur of a missed focus
    sensor_noise     signal-dependent shot noise + read noise of a small sensor
    jpeg             heavy JPEG compression
    low_resolution   downscale then upscale back (cheap sensor, digital zoom, messaging apps)
    over_exposure    too much light: highlights clip
    under_exposure   too little light: dark and coarsely quantised
    colour_cast      wrong white balance (warm, cool or green, chosen at random)
    combined         low_resolution -> sensor_noise -> jpeg at the same level

**Deterministic:** all randomness comes from a generator seeded by
(seed, corruption name, level, image id) through SHA-256, so the same image
gets the same corruption in every run and on every machine, and the order in
which images are processed doesn't matter. The motion-blur direction and the
colour of the cast depend on (seed, name, image id) only, so they stay the same
across the five levels of one image and only the strength changes.

**Scale:** blur sizes are given for an image whose long side is 1024 px and are
scaled to the actual image, so a small and a large copy of the same photo are
blurred by the same share of their width.

**The level parameters are PLACEHOLDERS.** They were set by hand to span "barely
visible" to "clearly bad" and are not calibrated against photos from real
low-end phones. See `LEVELS`.
"""

import hashlib
from typing import Callable

import cv2
import numpy as np

N_LEVELS = 5
REFERENCE_LONG_SIDE = 1024

# PLACEHOLDER level parameters (level 1..5), not calibrated against real phones.
LEVELS: dict[str, tuple] = {
    "gaussian_blur": (1.0, 2.0, 3.0, 4.5, 6.0),         # sigma in px at the reference size
    "motion_blur": (5, 9, 13, 19, 27),                   # line length in px at the reference size
    "defocus_blur": (2.0, 3.0, 5.0, 7.0, 10.0),          # disk radius in px at the reference size
    "sensor_noise": ((0.004, 0.01), (0.008, 0.02), (0.015, 0.03), (0.025, 0.045), (0.04, 0.07)),  # (shot gain, read std), image in [0, 1]
    "jpeg": (50, 35, 25, 15, 8),                         # JPEG quality
    "low_resolution": (0.6, 0.45, 0.33, 0.25, 0.17),     # downscale factor
    "over_exposure": (1.3, 1.6, 2.0, 2.6, 3.4),          # gain in linear light
    "under_exposure": (0.6, 0.4, 0.27, 0.18, 0.1),       # gain in linear light
    "colour_cast": (0.08, 0.15, 0.22, 0.30, 0.40),       # white-balance error
}
CAST_DIRECTIONS = {"warm": (1.0, 0.0, -1.0), "cool": (-1.0, 0.0, 1.0), "green": (-0.5, 1.0, -0.5)}  # R, G, B
COMBINED_CHAIN = ("low_resolution", "sensor_noise", "jpeg")
GAMMA = 2.2


def _scale(img: np.ndarray) -> float:
    return max(img.shape[:2]) / REFERENCE_LONG_SIDE


def _to_uint8(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(x * 255.0), 0, 255).astype(np.uint8)


def gaussian_blur(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    sigma = LEVELS["gaussian_blur"][level - 1] * _scale(img)
    return cv2.GaussianBlur(img, (0, 0), sigmaX=max(sigma, 0.1))


def motion_blur(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    length = max(3, int(round(LEVELS["motion_blur"][level - 1] * _scale(img))) | 1)  # odd, at least 3
    angle = float(dir_rng.uniform(0.0, 180.0))  # same direction at every level
    kernel = np.zeros((length, length), np.float32)
    kernel[length // 2, :] = 1.0
    rot = cv2.getRotationMatrix2D(((length - 1) / 2, (length - 1) / 2), angle, 1.0)
    kernel = cv2.warpAffine(kernel, rot, (length, length), flags=cv2.INTER_LINEAR)
    return cv2.filter2D(img, -1, kernel / kernel.sum(), borderType=cv2.BORDER_REFLECT)


def defocus_blur(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    radius = max(1.0, LEVELS["defocus_blur"][level - 1] * _scale(img))
    r = int(np.ceil(radius))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    kernel = (xx ** 2 + yy ** 2 <= radius ** 2).astype(np.float32)
    return cv2.filter2D(img, -1, kernel / kernel.sum(), borderType=cv2.BORDER_REFLECT)


def sensor_noise(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    shot, read = LEVELS["sensor_noise"][level - 1]
    x = img.astype(np.float32) / 255.0
    std = np.sqrt(shot * x + read ** 2)  # brighter pixels carry more shot noise
    return _to_uint8(x + rng.standard_normal(x.shape).astype(np.float32) * std)


def jpeg(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR),
                           [int(cv2.IMWRITE_JPEG_QUALITY), int(LEVELS["jpeg"][level - 1])])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return cv2.cvtColor(cv2.imdecode(buf, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def low_resolution(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    factor = LEVELS["low_resolution"][level - 1]
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(1, round(w * factor)), max(1, round(h * factor))), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _gain_in_linear_light(img: np.ndarray, gain: float | np.ndarray) -> np.ndarray:
    linear = (img.astype(np.float32) / 255.0) ** GAMMA
    return _to_uint8(np.clip(linear * gain, 0.0, 1.0) ** (1.0 / GAMMA))


def over_exposure(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    return _gain_in_linear_light(img, LEVELS["over_exposure"][level - 1])


def under_exposure(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    return _gain_in_linear_light(img, LEVELS["under_exposure"][level - 1])


def colour_cast(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    direction = np.array(CAST_DIRECTIONS[sorted(CAST_DIRECTIONS)[int(dir_rng.integers(len(CAST_DIRECTIONS)))]], np.float32)
    gains = 1.0 + LEVELS["colour_cast"][level - 1] * direction
    return _gain_in_linear_light(img, gains.reshape(1, 1, 3))


def combined(img: np.ndarray, level: int, rng: np.random.Generator, dir_rng: np.random.Generator) -> np.ndarray:
    for name in COMBINED_CHAIN:
        img = CORRUPTIONS[name](img, level, rng, dir_rng)
    return img


CORRUPTIONS: dict[str, Callable[[np.ndarray, int, np.random.Generator, np.random.Generator], np.ndarray]] = {
    "gaussian_blur": gaussian_blur, "motion_blur": motion_blur, "defocus_blur": defocus_blur,
    "sensor_noise": sensor_noise, "jpeg": jpeg, "low_resolution": low_resolution,
    "over_exposure": over_exposure, "under_exposure": under_exposure, "colour_cast": colour_cast,
    "combined": combined,
}


# Chains used only for the combined-chain ablation (Phase 4 follow-up, 2026-11-14); not part of the benchmark's ten.
ABLATION_CHAINS: dict[str, tuple[str, ...]] = {
    "noise_jpeg": ("sensor_noise", "jpeg"),
    "lowres_noise": ("low_resolution", "sensor_noise"),
}


def make_rng(seed: int, name: str, level: int | str, image_id: str) -> np.random.Generator:
    """Generator that depends only on (seed, corruption, level, image id)."""
    digest = hashlib.sha256(f"{seed}|{name}|{level}|{image_id}".encode("utf-8")).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


def corrupt(img: np.ndarray, name: str, level: int, seed: int, image_id: str) -> np.ndarray:
    """Apply corruption `name` at `level` (0 = unchanged, 1..5) to an RGB uint8 image.

    Returns a new uint8 array of the same shape. Deterministic in (seed, name, level, image_id).
    """
    if name not in CORRUPTIONS and name not in ABLATION_CHAINS:
        raise ValueError(f"Unknown corruption '{name}'. Expected one of {sorted(CORRUPTIONS) + sorted(ABLATION_CHAINS)}.")
    if not isinstance(level, (int, np.integer)) or not 0 <= level <= N_LEVELS:
        raise ValueError(f"level must be an integer from 0 to {N_LEVELS}, got {level!r}")
    if img.dtype != np.uint8 or img.ndim != 3 or img.shape[2] != 3:
        raise ValueError("img must be an RGB uint8 array of shape (H, W, 3)")
    if level == 0:
        return img.copy()
    rng = make_rng(seed, name, int(level), image_id)       # noise: new at every level
    dir_rng = make_rng(seed, name, "direction", image_id)  # blur direction / cast colour: the same at every level
    if name in ABLATION_CHAINS:
        for step in ABLATION_CHAINS[name]:
            img = CORRUPTIONS[step](img, int(level), rng, dir_rng)
        return np.ascontiguousarray(img)
    return np.ascontiguousarray(CORRUPTIONS[name](img, int(level), rng, dir_rng))
