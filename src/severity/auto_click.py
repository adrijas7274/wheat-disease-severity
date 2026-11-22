"""Automatic leaf click for images that have no stored click (Phase 4).

Rule fixed on 2026-11-11 (`docs/phase3_plan.md` section 7, the project plan Phase 4):
the click is the point deepest inside the largest infected component that
SegFormer-B0 predicts on the **clean** image, or the image centre if nothing
is predicted. The same click is then reused for every corrupted version.

Details: "largest" is by pixel count with 8-connectivity at the model's output
resolution; "deepest" is the highest Euclidean distance-transform value; ties
go to the first pixel in row-major order (and to the lowest component label,
which is the component met first in row-major order); the click is mapped back
to original-image pixels at the centre of the chosen output pixel.
"""

import cv2
import numpy as np


def click_from_region(region: np.ndarray, image_shape: tuple[int, ...]) -> tuple[int, int]:
    """(x, y) click in original-image pixels.

    region: bool (h, w) predicted infected region at the model's output resolution, padding removed.
    image_shape: shape of the original image, (H, W, ...).
    """
    height, width = image_shape[:2]
    if not region.any():
        return width // 2, height // 2
    n, labels, stats, _ = cv2.connectedComponentsWithStats(region.astype(np.uint8), connectivity=8)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))  # label 0 is the background
    component = (labels == largest).astype(np.uint8)
    # pad by one pixel so tissue at the image border is not treated as deep inside
    dist = cv2.distanceTransform(np.pad(component, 1), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
    y, x = np.unravel_index(int(np.argmax(dist)), dist.shape)
    h, w = region.shape
    return min(width - 1, int((x + 0.5) * width / w)), min(height - 1, int((y + 0.5) * height / h))
