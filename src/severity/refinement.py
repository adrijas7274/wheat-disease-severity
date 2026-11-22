"""Lesion refinement and severity (Phase 3, `docs/phase3_plan.md` sections 2-3).

All methods work on the same leaf mask and give
`severity = lesion pixels on leaf / leaf pixels` (in %).

    A / B   the infected region (PlantSeg mask / model prediction) clipped to the leaf
    C0      the region minus healthy-green pixels (untuned HSV range, no parameters)
    C1      the region restricted to the disease group's lesion colour in Lab space,
            one threshold per disease group, plus chlorotic tissue touching a lesion

Refinement can only shrink a region: lesions the region missed stay missed.

Fixed constants here (the green range, the yellow range, the mildew lightness
floor) are untuned placeholders. Only the C1 thresholds are tuned.
"""

import cv2
import numpy as np

from src.severity.mask_coarseness_check import GREEN_LOWER, GREEN_UPPER

DISEASE_GROUPS = {
    "wheat stripe rust": "rust",
    "wheat leaf rust": "rust",
    "wheat septoria blotch": "necrotic",
    "wheat bacterial leaf streak (black chaff)": "necrotic",
    "wheat powdery mildew": "mildew",
}
GROUPS = ("rust", "necrotic", "mildew")
# Chlorotic (yellow) tissue: the hue band just below the healthy-green range. Untuned placeholder.
YELLOW_LOWER = np.array([15, 40, 40])
YELLOW_UPPER = np.array([24, 255, 255])
MILDEW_MIN_LIGHTNESS = 35.0  # L* (0-100): darker low-chroma pixels are shadow, not mildew. Untuned.


def healthy_green(image: np.ndarray) -> np.ndarray:
    """Bool mask of healthy-green pixels of an RGB uint8 image (the untuned range of the mask coarseness check)."""
    return cv2.inRange(cv2.cvtColor(image, cv2.COLOR_RGB2HSV), GREEN_LOWER, GREEN_UPPER) > 0


def chlorotic(image: np.ndarray) -> np.ndarray:
    """Bool mask of yellow (chlorotic) pixels."""
    return cv2.inRange(cv2.cvtColor(image, cv2.COLOR_RGB2HSV), YELLOW_LOWER, YELLOW_UPPER) > 0


def lab(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """CIE L* (0-100), a*, b* (signed) of an RGB uint8 image, as float32 arrays."""
    L, a, b = cv2.split(cv2.cvtColor(image.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB))
    return L, a, b


def lesion_colour(image: np.ndarray, group: str, threshold: float) -> np.ndarray:
    """Bool mask of pixels with the disease group's lesion colour.

    rust      orange to orange-brown: a* (green-to-red axis) at or above the threshold
    necrotic  brown dead tissue:      a* at or above the threshold (browns are less red than pustules)
    mildew    white or grey:          chroma sqrt(a*^2 + b*^2) at or below the threshold, and not dark
    """
    L, a, b = lab(image)
    if group in ("rust", "necrotic"):
        return a >= threshold
    if group == "mildew":
        return (np.hypot(a, b) <= threshold) & (L >= MILDEW_MIN_LIGHTNESS)
    raise ValueError(f"Unknown disease group '{group}'. Expected one of {GROUPS}.")


def touching(candidates: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """The 8-connected components of `candidates` that touch `seeds` (share a pixel or are 8-adjacent)."""
    if not candidates.any() or not seeds.any():
        return np.zeros_like(candidates, dtype=bool)
    _, labels = cv2.connectedComponents(candidates.astype(np.uint8), connectivity=8)
    near = cv2.dilate(seeds.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    hit = np.unique(labels[near & candidates])
    return np.isin(labels, hit[hit > 0])


def refine_c0(region: np.ndarray, image: np.ndarray) -> np.ndarray:
    """C0: the region with healthy-green pixels removed. No tuned parameters."""
    return region & ~healthy_green(image)


def refine_c1(region: np.ndarray, image: np.ndarray, group: str, threshold: float, halo: bool = True) -> np.ndarray:
    """C1: region pixels with the group's lesion colour, plus (if `halo`) chlorotic tissue in the
    region that touches such a pixel (the guidelines' placeholder halo rule)."""
    lesion = region & lesion_colour(image, group, threshold)
    if not halo:
        return lesion
    return lesion | touching(region & chlorotic(image) & ~lesion, lesion)


def severity_pct(lesion: np.ndarray, leaf: np.ndarray) -> float:
    """100 * lesion pixels on the leaf / leaf pixels (nan if the leaf is empty)."""
    n_leaf = int(leaf.sum())
    return 100.0 * int((lesion & leaf).sum()) / n_leaf if n_leaf else float("nan")
