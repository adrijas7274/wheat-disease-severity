"""Phase 6: uncertainty scores for one severity estimate, and risk-coverage tools.

Scores (higher = less reliable), all cheap enough for a phone:

    entropy      mean softmax entropy of the region model inside its predicted region
    tta          spread (std) of the severity when the region model sees the photo mirrored
                 left-right and up-down (test-time augmentation of the region stage)
    photometric  spread (std) of the severity when the photo is made slightly brighter, darker,
                 warmer and cooler before the colour rule (test-time augmentation of the colour
                 stage; no network call). Added because Phase 4 showed the colour stage is where
                 the estimate is fragile.
    margin       minus the distance (points) from the severity to the nearest level threshold:
                 an estimate next to a threshold flips its decision easily (PLACEHOLDER thresholds)

Risk-coverage: order the estimates from most to least reliable, answer only the most reliable
fraction (coverage), and measure the error (risk) on the answered ones.
"""

import numpy as np

GAMMA = 2.2
PHOTOMETRIC_VIEWS = (("gain", 1.15), ("gain", 0.87), ("warm", 0.06), ("cool", 0.06))  # untuned placeholders
_CAST = {"warm": np.array([1.0, 0.0, -1.0], np.float32), "cool": np.array([-1.0, 0.0, 1.0], np.float32)}


def photometric_views(image: np.ndarray) -> list[np.ndarray]:
    """Slightly brighter, darker, warmer and cooler copies of an RGB uint8 image (linear-light gains)."""
    lin = (image.astype(np.float32) / 255.0) ** GAMMA
    views = []
    for kind, amount in PHOTOMETRIC_VIEWS:
        gains = amount if kind == "gain" else (1.0 + amount * _CAST[kind]).reshape(1, 1, 3)
        views.append(np.clip(np.rint(np.clip(lin * gains, 0, 1) ** (1 / GAMMA) * 255.0), 0, 255).astype(np.uint8))
    return views


def spread(values: list[float]) -> float:
    """Standard deviation of the finite values (0 if fewer than two)."""
    v = np.array([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    return float(v.std()) if len(v) >= 2 else 0.0


def threshold_margin(severity_pct: float, thresholds: dict) -> float:
    """Distance in points from a severity to the nearest level boundary (0%, low_max, medium_max)."""
    bounds = [0.0, 100.0 * thresholds["low_max"], 100.0 * thresholds["medium_max"]]
    return float(min(abs(severity_pct - b) for b in bounds))


def risk_coverage(score: np.ndarray, risk: np.ndarray, n_points: int = 101) -> tuple[np.ndarray, np.ndarray]:
    """(coverage grid, mean risk of the answered items). Items are answered in order of increasing
    score; ties are kept in the given order. Coverage 0 is left out."""
    order = np.argsort(score, kind="stable")
    cum = np.cumsum(np.asarray(risk, dtype=float)[order]) / np.arange(1, len(order) + 1)
    coverage = np.linspace(1.0 / n_points, 1.0, n_points)
    idx = np.clip(np.ceil(coverage * len(order) - 1e-9).astype(int) - 1, 0, len(order) - 1)
    return coverage, cum[idx]


def aurc(score: np.ndarray, risk: np.ndarray) -> float:
    """Area under the risk-coverage curve (mean risk over all coverages); lower is better."""
    order = np.argsort(score, kind="stable")
    return float((np.cumsum(np.asarray(risk, dtype=float)[order]) / np.arange(1, len(order) + 1)).mean())


def risk_at_coverage(score: np.ndarray, risk: np.ndarray, coverage: float) -> float:
    """Mean risk when only the `coverage` share with the lowest scores is answered."""
    order = np.argsort(score, kind="stable")
    k = max(1, int(np.ceil(coverage * len(order) - 1e-9)))
    return float(np.asarray(risk, dtype=float)[order[:k]].mean())


def threshold_for_coverage(score: np.ndarray, coverage: float) -> float:
    """Score value such that answering `score <= value` keeps about `coverage` of the items."""
    return float(np.quantile(np.asarray(score, dtype=float), coverage))
