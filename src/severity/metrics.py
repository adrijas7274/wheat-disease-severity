"""Segmentation metrics for Phase 2 infected-region baselines: binary IoU,
Dice, infected-area ratio error, and bootstrap confidence intervals.

These score agreement with PlantSeg's coarse infected-region masks, not
true lesion boundaries - see experiments/LOG.md (2026-10-03/04) and
the project plan Phase 2.
"""

import numpy as np


def binary_iou(pred: np.ndarray, true: np.ndarray) -> float:
    """IoU for the infected class. 1.0 if both pred and true are empty
    (correctly predicting "no infection" is not a failure).
    """
    pred_bool = pred.astype(bool)
    true_bool = true.astype(bool)
    intersection = int((pred_bool & true_bool).sum())
    union = int((pred_bool | true_bool).sum())
    if union == 0:
        return 1.0
    return intersection / union


def binary_dice(pred: np.ndarray, true: np.ndarray) -> float:
    """Dice (F1) for the infected class. 1.0 if both pred and true are empty."""
    pred_bool = pred.astype(bool)
    true_bool = true.astype(bool)
    intersection = int((pred_bool & true_bool).sum())
    denom = int(pred_bool.sum()) + int(true_bool.sum())
    if denom == 0:
        return 1.0
    return 2 * intersection / denom


def infected_area_ratio_error(pred: np.ndarray, true: np.ndarray) -> float:
    """|predicted infected-pixel fraction - true infected-pixel fraction|."""
    pred_frac = float(pred.astype(bool).mean())
    true_frac = float(true.astype(bool).mean())
    return abs(pred_frac - true_frac)


def bootstrap_ci(
    values: list[float], n_bootstrap: int = 1000, ci: float = 0.95, seed: int = 42,
) -> tuple[float, float, float]:
    """Percentile bootstrap over a list of per-image metric values.

    Returns (mean, ci_low, ci_high). (nan, nan, nan) if values is empty.
    """
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0:
        return (float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_bootstrap)
    n = len(arr)
    for i in range(n_bootstrap):
        sample = rng.choice(arr, size=n, replace=True)
        boot_means[i] = sample.mean()
    alpha = (1 - ci) / 2
    lo = float(np.percentile(boot_means, 100 * alpha))
    hi = float(np.percentile(boot_means, 100 * (1 - alpha)))
    return (float(arr.mean()), lo, hi)
