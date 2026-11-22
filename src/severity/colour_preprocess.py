"""Phase 5: cheap image normalisation applied before the colour rule only.

The Phase 4 benchmark showed that the severity estimate is most fragile under
colour casts, exposure changes and sensor noise, because the lesion rule is a
colour threshold. These steps try to undo those changes before the threshold is
applied. They are all a few array operations, cheap enough for a phone.

    gray_world       colour constancy: scale each channel so the three channel means are equal
    shades_of_gray   the same with a Minkowski p-norm (p = 6) instead of the mean (Finlayson & Trezzi, 2004)
    exposure         one gain so that the mean luminance is mid grey (0.18 in linear light)
    denoise          light Gaussian blur (sigma 1.5 px at a 1024 px long side)

Gains are applied in linear light (gamma 2.2), like the corruptions. The region
model and SAM 2 never see the normalised image.
"""

import cv2
import numpy as np

GAMMA = 2.2
SHADES_P = 6
EXPOSURE_TARGET = 0.18
DENOISE_SIGMA = 1.5  # px at the reference long side
REFERENCE_LONG_SIDE = 1024
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)  # Rec. 709, linear light


def _linear(image: np.ndarray) -> np.ndarray:
    return (image.astype(np.float32) / 255.0) ** GAMMA


def _encode(linear: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(np.clip(linear, 0.0, 1.0) ** (1.0 / GAMMA) * 255.0), 0, 255).astype(np.uint8)


def _white_balance(image: np.ndarray, p: float) -> np.ndarray:
    lin = _linear(image)
    illum = np.power(np.mean(np.power(lin.reshape(-1, 3), p), axis=0), 1.0 / p)
    gains = illum.mean() / np.maximum(illum, 1e-6)  # keeps the overall brightness
    return _encode(lin * gains.reshape(1, 1, 3))


def gray_world(image: np.ndarray) -> np.ndarray:
    return _white_balance(image, 1.0)


def shades_of_gray(image: np.ndarray) -> np.ndarray:
    return _white_balance(image, SHADES_P)


def exposure(image: np.ndarray) -> np.ndarray:
    lin = _linear(image)
    mean_luma = float((lin @ LUMA).mean())
    return _encode(lin * (EXPOSURE_TARGET / max(mean_luma, 1e-6)))


def denoise(image: np.ndarray) -> np.ndarray:
    sigma = max(0.5, DENOISE_SIGMA * max(image.shape[:2]) / REFERENCE_LONG_SIDE)
    return cv2.GaussianBlur(image, (0, 0), sigmaX=sigma)


STEPS = {"gray_world": gray_world, "shades_of_gray": shades_of_gray, "exposure": exposure, "denoise": denoise}


def apply(image: np.ndarray, steps: list[str] | tuple[str, ...]) -> np.ndarray:
    """Apply the named steps in order to an RGB uint8 image. An empty list returns the image itself."""
    for step in steps:
        if step not in STEPS:
            raise ValueError(f"Unknown preprocessing step '{step}'. Expected one of {sorted(STEPS)}.")
        image = STEPS[step](image)
    return image
