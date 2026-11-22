"""Rater training on synthetic leaves with known severity (Phase 3).

Each session is 15 synthetic wheat leaves drawn like the standard area
diagrams (src/severity/area_diagrams.py), with hidden severities between
0.5% and 60%, 5 each in rust, blotch and mildew style, in shuffled order.
The rater rates each leaf, then sees the true value and their error. At the
end: mean absolute error and mean signed error (positive = overestimates).

Hidden severities are drawn **log-uniformly** (rounded to 0.5%): equal
numbers of leaves per factor of 2 in severity, so low severities (where
raters are known to overestimate, and where the 5% / 20% placeholder
thresholds sit) get as much practice as high ones. A linear-uniform draw
over 0.5-60% would put ~90% of the leaves above 5%.

Results go only to report/tables/rater_training.md (one appended section per
session). Nothing here reads or writes the gold, tuning, pilot or recheck logs.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.severity import area_diagrams as sad

N_LEAVES = 15
MIN_PCT, MAX_PCT = 0.5, 60.0
DEFAULT_REPORT = Path("report/tables/rater_training.md")


@dataclass
class TrainingLeaf:
    style: str
    target_pct: float  # % used to generate the lesion
    true_pct: float  # measured % of leaf pixels that are lesion (= target to within one pixel)
    seed: int
    rating: float | None = None

    @property
    def error(self) -> float | None:
        """Signed error, rating - true (positive = overestimate)."""
        return None if self.rating is None else self.rating - self.true_pct


@dataclass
class TrainingSession:
    seed: int
    leaves: list[TrainingLeaf] = field(default_factory=list)
    started_at: str = ""


def make_session(seed: int, n: int = N_LEAVES) -> TrainingSession:
    """15 leaves: styles balanced (5 each) and shuffled, severities
    log-uniform in [0.5, 60] rounded to 0.5. True % is measured from the
    generated mask, so it's exact even after pixel rounding."""
    rng = np.random.default_rng(seed)
    styles = [sad.STYLES[i % len(sad.STYLES)] for i in range(n)]
    rng.shuffle(styles)
    targets = np.exp(rng.uniform(np.log(MIN_PCT), np.log(MAX_PCT), n))
    targets = np.clip(np.round(targets * 2) / 2, MIN_PCT, MAX_PCT)
    leaf = sad.leaf_mask()
    leaves = []
    for i, (style, pct) in enumerate(zip(styles, targets)):
        leaf_seed = int(rng.integers(0, 2**31 - 1))
        lesion = sad.lesion_mask(leaf, float(pct), style, leaf_seed)
        leaves.append(TrainingLeaf(style, float(pct), round(100 * lesion.sum() / leaf.sum(), 2), leaf_seed))
    return TrainingSession(seed, leaves, datetime.now(timezone.utc).isoformat(timespec="seconds"))


def render(leaf: TrainingLeaf, flip: bool = False, upscale: float = 1.5) -> np.ndarray:
    """RGB image of one training leaf (same drawing as the area diagrams).
    The lesion mask is regenerated from the stored seed and target %."""
    import cv2

    mask = sad.leaf_mask()
    lesion = sad.lesion_mask(mask, leaf.target_pct, leaf.style, leaf.seed)
    img = sad.render_leaf(mask, lesion, leaf.style, leaf.seed)
    if flip:
        img = img[:, ::-1]
    size = (round(img.shape[1] * upscale), round(img.shape[0] * upscale))
    return cv2.resize(np.ascontiguousarray(img), size, interpolation=cv2.INTER_NEAREST)


def summary(session: TrainingSession) -> dict:
    """MAE and mean signed error over the rated leaves, overall and per style."""
    rated = [lf for lf in session.leaves if lf.rating is not None]
    if not rated:
        raise ValueError("No leaf has been rated yet.")
    errs = np.array([lf.error for lf in rated])
    out = {"n": len(rated), "mae": float(np.abs(errs).mean()), "bias": float(errs.mean()), "by_style": {}}
    for style in sad.STYLES:
        e = np.array([lf.error for lf in rated if lf.style == style])
        if len(e):
            out["by_style"][style] = {"n": len(e), "mae": float(np.abs(e).mean()), "bias": float(e.mean())}
    return out


def bias_sentence(bias: float, tol: float = 0.5) -> str:
    """Plain-language direction of the mean signed error (|bias| <= tol pts counts as no clear bias)."""
    if bias > tol:
        return f"You **overestimate** on average, by {bias:.1f} percentage points."
    if bias < -tol:
        return f"You **underestimate** on average, by {-bias:.1f} percentage points."
    return f"No clear over- or underestimation (mean signed error {bias:+.1f} points)."


def append_report(path: Path, session: TrainingSession, rater: str) -> None:
    """Append one session (table + summary) to the markdown report."""
    s = summary(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    lines = []
    if new:
        lines += ["# Rater training on synthetic leaves", "",
                  "Synthetic wheat leaves drawn like the standard area diagrams "
                  "(`src/severity/area_diagrams.py`), with hidden exact severities "
                  "(log-uniform, 0.5-60%). Error = rating - true (positive = overestimate). "
                  "Generated by the rating tool's training mode (`src/severity/rater_training.py`). "
                  "Practice only: not part of any evaluation.", ""]
    lines += [f"## Session {session.started_at} (rater: {rater or 'unknown'}, seed {session.seed})", "",
              "| # | style | true % | rating % | error |", "|---|---|---|---|---|"]
    for i, lf in enumerate(session.leaves, 1):
        if lf.rating is not None:
            lines.append(f"| {i} | {lf.style} | {lf.true_pct:.2f} | {lf.rating:.1f} | {lf.error:+.2f} |")
    lines += ["", f"- Rated: {s['n']} of {len(session.leaves)}",
              f"- **Mean absolute error: {s['mae']:.2f}** percentage points",
              f"- Mean signed error: {s['bias']:+.2f} ({bias_sentence(s['bias']).replace('**', '')})"]
    for style, v in s["by_style"].items():
        lines.append(f"- {style}: MAE {v['mae']:.2f}, signed {v['bias']:+.2f} (n={v['n']})")
    lines.append("")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
