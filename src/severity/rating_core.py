"""UI-independent logic for the Phase 3 visual severity rating tool
(src/severity/rating_tool.py): log schema, skip reasons, input checks,
click mapping, the click marker and which pilot images are excluded.

Rules: docs/annotation_guidelines.md. Queues, the append-only log helpers
and the non_photo re-tag sync are shared with the retired mask tool
(src/severity/annotation_core.py).
"""

import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from src.severity import annotation_core as core

RATING_FIELDNAMES = [
    "name", "split", "disease", "set", "rater", "status", "skip_reason",
    "click_x", "click_y", "img_w", "img_h", "severity_pct", "rating_s",
    "notes", "saved_at",
]
COLLAGE = "collage / multi-panel image"
SKIP_REASONS = [
    core.NO_MAIN_LEAF,
    "main leaf too blurred",
    "not wheat leaf disease",
    core.NOT_A_PHOTO,
    COLLAGE,
]
RETAG_REASONS = (core.NOT_A_PHOTO, COLLAGE)  # these skips re-tag the image to non_photo


def gold_digest(log_csv: Path) -> str:
    """SHA-256 of every gold row in the rating log, in log order. Rows are
    parsed first, so git's line-ending conversion doesn't change the digest.
    Recheck rows are their own set and don't affect it."""
    with open(log_csv, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["set"] == "gold"]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def validate_rating(click: tuple[int, int] | None, severity_pct: float | None) -> None:
    """Raise ValueError (with a message for the rater) if the rating can't be saved."""
    if click is None:
        raise ValueError("Click once on the main leaf first.")
    if severity_pct is None:
        raise ValueError("Enter a severity % (0-100).")
    if not 0 <= severity_pct <= 100:
        raise ValueError(f"Severity must be between 0 and 100, got {severity_pct}.")


HIGH_CONFIRM_ABOVE = 75.0  # no reference diagram goes above 75%, so higher ratings need a second Save


def needs_high_confirm(severity_pct: float, confirmed_pct: float | None) -> bool:
    """True if this rating is above 75% and the rater hasn't yet confirmed this exact value."""
    return severity_pct > HIGH_CONFIRM_ABOVE and confirmed_pct != severity_pct


def rating_display_scale(shape: tuple[int, ...], target_long: int = 1600, max_long: int = 2048) -> float:
    """Scale for the display copy: big images are shrunk to `max_long`, small
    ones are enlarged to `target_long` so they fill the photo area (the
    browser never enlarges them, it only shrinks). Display only: clicks are
    divided by this scale (display_to_image), so logged coordinates stay in
    original pixels."""
    long_side = max(shape[:2])
    if long_side > max_long:
        return max_long / long_side
    if long_side < target_long:
        return target_long / long_side
    return 1.0


def display_to_image(xy: tuple[float, float], scale: float, shape: tuple[int, ...]) -> tuple[int, int]:
    """Map a click on the downscaled display copy to original-resolution pixel coordinates."""
    h, w = shape[:2]
    x = min(w - 1, max(0, int(xy[0] / scale)))
    y = min(h - 1, max(0, int(xy[1] / scale)))
    return x, y


def draw_marker(display: np.ndarray, xy_image: tuple[int, int] | None, scale: float) -> np.ndarray:
    """Copy of the display image with a ring + centre dot at the stored click.
    The marker is the only thing ever drawn on the photo."""
    out = display.copy()
    if xy_image is None:
        return out
    cx, cy = round(xy_image[0] * scale), round(xy_image[1] * scale)
    r = max(6, round(max(out.shape[:2]) / 90))
    t = max(2, r // 4)
    cv2.circle(out, (cx, cy), r + t, (0, 0, 0), t + 2, lineType=cv2.LINE_AA)
    cv2.circle(out, (cx, cy), r, (0, 255, 255), t, lineType=cv2.LINE_AA)
    cv2.circle(out, (cx, cy), max(2, t), (255, 0, 255), -1, lineType=cv2.LINE_AA)
    return out


def seen_in_mask_pilots(mask_log_csv: Path) -> set[str]:
    """Pilot images already shown to the rater by the retired mask tool. The
    rating pilot skips them so its timings aren't sped up by familiarity."""
    if not mask_log_csv.exists():
        return set()
    with open(mask_log_csv, encoding="utf-8") as f:
        return {r["name"] for r in csv.DictReader(f) if r["set"] == "pilot"}


def status_with_exclusions(log_csv: Path, set_name: str, exclude: set[str]) -> dict[str, dict]:
    """core.load_status plus excluded names marked status 'excluded', so
    next_row passes over them and progress counts them as neither done nor skipped."""
    status = {n: {"status": "excluded"} for n in exclude}
    status.update(core.load_status(log_csv, set_name))
    return status


def mean_abs_diff(first: dict[str, float], second: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Self-consistency: mean |first - second| over images rated twice, plus per-image differences."""
    common = sorted(set(first) & set(second))
    if not common:
        raise ValueError("No image has both a gold rating and a recheck rating.")
    diffs = {n: abs(first[n] - second[n]) for n in common}
    return float(np.mean(list(diffs.values()))), diffs
