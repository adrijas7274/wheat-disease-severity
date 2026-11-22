"""Phase 6: photo-quality gate. Cheap image-only checks that run before any model.

Features (all on a copy resized to a 512 px long side, so they don't depend on the photo's size):

    sharpness   variance of the Laplacian of the grey image (low = blurred)
    noise       Immerkaer's (1996) fast noise estimate: std of the image filtered with a
                Laplacian-difference mask, which removes edges and keeps pixel noise (high = noisy)
    luma        mean brightness, 0 to 1 (too low = under-exposed, too high = over-exposed)
    clip_high   share of pixels at 250 or above in the brightest channel
    clip_low    share of pixels at 5 or below in the brightest channel
    cast        largest absolute log-ratio between a channel mean and the mean of the three
                (in linear light). Leaf photos are green-dominant, so this is only a weak cue.
    min_side    shorter side of the original photo in pixels

**Rule gate.** A photo fails ("please retake the photo") if a feature lies outside its allowed
range. The ranges are percentiles of the clean close-up **validation** images (never test), so the
false-retake rate on clean photos is set by construction. `min_side` uses a fixed bound.

The checks see only the photo. They cannot tell a wide shot from a close-up; a separate framing
check on the leaf's share of the image is in `src/uncertainty/phase6.py`.
"""

import cv2
import numpy as np

FEATURES = ("sharpness", "noise", "luma", "clip_high", "clip_low", "cast", "min_side")
LONG_SIDE = 512
MIN_SIDE_PX = 224  # fixed: below this the model's 512 px input is mostly upsampling
# which side of a feature's validation distribution means "bad"
CHECKS = {"sharpness": "low", "noise": "high", "luma": "both", "clip_high": "high", "clip_low": "high"}
REASONS = {"sharpness": "blurred", "noise": "noisy", "luma": "exposure", "clip_high": "over-exposed", "clip_low": "under-exposed",
           "min_side": "too small"}
_NOISE_MASK = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
GAMMA = 2.2


def features(image: np.ndarray) -> dict[str, float]:
    """Gate features of one RGB uint8 image."""
    h, w = image.shape[:2]
    scale = LONG_SIDE / max(h, w)
    small = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA) if scale < 1 else image
    grey = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32)
    lap = cv2.Laplacian(grey, cv2.CV_32F)
    hh, ww = grey.shape
    noise = float(np.sqrt(np.pi / 2) * np.abs(cv2.filter2D(grey, -1, _NOISE_MASK)[1:-1, 1:-1]).sum() / (6.0 * max((ww - 2) * (hh - 2), 1)))
    brightest = small.max(axis=2)
    means = ((small.astype(np.float32) / 255.0) ** GAMMA).reshape(-1, 3).mean(axis=0) + 1e-6
    return {"sharpness": float(lap.var()), "noise": noise, "luma": float(grey.mean() / 255.0),
            "clip_high": float((brightest >= 250).mean()), "clip_low": float((brightest <= 5).mean()),
            "cast": float(np.abs(np.log(means / means.mean())).max()), "min_side": float(min(h, w))}


def fit_ranges(clean_features: list[dict[str, float]], tail_pct: float, checks: dict[str, str] | None = None,
               fixed_min_side: bool = True) -> dict[str, list[float | None]]:
    """Allowed [low, high] per checked feature from clean reference images: the `tail_pct`
    percentile on each bad side (None = no bound on that side). v1: `CHECKS` plus the fixed
    224 px minimum side."""
    ranges: dict[str, list[float | None]] = {}
    for name, side in (CHECKS if checks is None else checks).items():
        values = np.array([f[name] for f in clean_features], dtype=float)
        lo = float(np.percentile(values, tail_pct)) if side in ("low", "both") else None
        hi = float(np.percentile(values, 100 - tail_pct)) if side in ("high", "both") else None
        ranges[name] = [lo, hi]
    if fixed_min_side:
        ranges["min_side"] = [float(MIN_SIDE_PX), None]
    return ranges


# ----------------------------------------------------------------------------- v2 (post hoc, 2026-11-17)

# v2 gate: the v1 checks plus JPEG blockiness, and the minimum side fitted like every other check
# instead of the fixed 224 px.
CHECKS_V2 = dict(CHECKS, blockiness="high", min_side="low")
REASONS["blockiness"] = "compressed"
BLOCK = 8  # JPEG block size


def blockiness(image: np.ndarray) -> float:
    """JPEG blockiness of an RGB uint8 image at its full resolution (resizing would hide the grid):
    mean absolute grey-level step across 8 px block boundaries divided by the mean step elsewhere,
    averaged over the horizontal and vertical directions. About 1 without block artefacts."""
    grey = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float32)
    ratios = []
    for steps in (np.abs(np.diff(grey, axis=1)), np.abs(np.diff(grey, axis=0)).T):
        boundary = (np.arange(steps.shape[1]) + 1) % BLOCK == 0  # step between pixel k and k+1, k+1 a multiple of 8
        if boundary.all() or not boundary.any():
            ratios.append(1.0)
            continue
        ratios.append(float((steps[:, boundary].mean() + 1e-3) / (steps[:, ~boundary].mean() + 1e-3)))
    return float(np.mean(ratios))


def fit_ranges_total(clean_features: list[dict[str, float]], target: float, checks: dict[str, str] | None = None,
                     step_pct: float = 0.05) -> tuple[dict[str, list[float | None]], float, float]:
    """v2: one overall false-retake target. The same tail percentile is used on every check side
    (the budget is split evenly), and the largest tail whose share of clean photos failing ANY check
    is at most `target` is chosen. Returns (ranges, tail_pct, clean failure rate)."""
    checks = CHECKS_V2 if checks is None else checks
    best = (fit_ranges(clean_features, 0.0, checks, fixed_min_side=False), 0.0, 0.0)
    for tail in np.arange(step_pct, 100.0 * target + 1e-9, step_pct):
        ranges = fit_ranges(clean_features, float(tail), checks, fixed_min_side=False)
        rate = float(np.mean([bool(failed_checks(f, ranges)) for f in clean_features]))
        if rate <= target:
            best = (ranges, float(round(tail, 4)), rate)
    return best


def failed_checks(feats: dict[str, float], ranges: dict[str, list[float | None]]) -> list[str]:
    """Names of the features outside their allowed range (empty list = the photo passes)."""
    out = []
    for name, (lo, hi) in ranges.items():
        if (lo is not None and feats[name] < lo) or (hi is not None and feats[name] > hi):
            out.append(name)
    return out


def feature_vector(feats: dict[str, float]) -> list[float]:
    """Features for the tiny classifier: log-scaled where the range spans orders of magnitude.
    Blockiness (v2) is appended when present."""
    out = [float(np.log1p(feats["sharpness"])), float(np.log1p(feats["noise"])), feats["luma"],
           feats["clip_high"], feats["clip_low"], feats["cast"], float(np.log(max(feats["min_side"], 1.0)))]
    return out + ([float(np.log(max(feats["blockiness"], 1e-3)))] if "blockiness" in feats else [])
