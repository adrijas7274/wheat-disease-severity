"""UI-independent logic for the Phase 3 annotation tool: magic wand, brush
strokes, overlays, the append-only annotation log, and which image is next.

Independence rule (docs/annotation_guidelines.md): nothing here reads the
refinement pipeline's thresholds. The wand's colour tolerance is whatever the
annotator sets on the slider for that image, and it's logged per image.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

LOG_FIELDNAMES = [
    "name", "split", "disease", "set", "annotator", "status", "skip_reason",
    "incomplete", "leaf_s", "lesion_s", "tools_leaf", "tools_lesion",
    "wand_tolerance", "leaf_px", "lesion_px", "severity", "no_lesion",
    "leaf_largest_part", "notes", "saved_at",
]
NOT_A_PHOTO = "not a real photo (mis-tagged)"
NO_MAIN_LEAF = "no single main leaf"
SKIP_REASONS = [
    NO_MAIN_LEAF,
    "main leaf too blurred",
    "not wheat leaf disease",
    NOT_A_PHOTO,  # also re-tags the image to non_photo in the tags CSV, see sync_not_photo_retags
]
ADD_COLOR = (0, 255, 0)  # brush colour meaning "add to mask"
REMOVE_COLOR = (255, 0, 255)  # brush colour meaning "remove from mask"


# ---------------------------------------------------------------- wand

def to_lab(image: np.ndarray) -> np.ndarray:
    """RGB uint8 -> CIE Lab float32 (L 0-100), so the wand's tolerance is a
    perceptual colour distance (Delta E 1976) rather than raw RGB."""
    return cv2.cvtColor(image.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def wand_select(lab: np.ndarray, seed_xy: tuple[int, int], tolerance: float, contiguous: bool) -> np.ndarray:
    """Pixels whose Lab colour is within `tolerance` of the seed's colour
    (median of a 5x5 patch, to be robust to a single noisy pixel).

    contiguous=True keeps only the connected region containing the seed (one
    blotch); False keeps every matching pixel in the image (many pustules at
    once). Callers clip the result to the leaf for lesion annotation.
    """
    x, y = seed_xy
    h, w = lab.shape[:2]
    patch = lab[max(0, y - 2): min(h, y + 3), max(0, x - 2): min(w, x + 3)].reshape(-1, 3)
    seed = np.median(patch, axis=0)
    sel = np.linalg.norm(lab - seed, axis=2) <= tolerance
    if contiguous:
        _, labels = cv2.connectedComponents(sel.astype(np.uint8), connectivity=8)
        seed_label = labels[y, x]
        sel = (labels == seed_label) if seed_label != 0 else np.zeros_like(sel)
    return sel


# ---------------------------------------------------------------- brush

def apply_brush_layer(mask: np.ndarray, layer: np.ndarray) -> np.ndarray:
    """Apply an RGBA brush layer to a boolean mask: green strokes add,
    magenta strokes remove. The layer is resized (nearest) to the mask size,
    since the editor works on a downscaled display copy of large images."""
    if layer.shape[:2] != mask.shape:
        layer = cv2.resize(layer, (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_NEAREST)
    painted = layer[..., 3] >= 128
    rgb = layer[..., :3].astype(np.int32)
    is_add = painted & (rgb[..., 1] > rgb[..., 0])  # green: G dominates; magenta: R (and B) dominate
    is_remove = painted & ~is_add
    return (mask | is_add) & ~is_remove


# ---------------------------------------------------------------- display

def display_scale(shape: tuple[int, ...], max_side: int) -> float:
    """Factor (<= 1) that brings the longer image side down to `max_side`."""
    return min(1.0, max_side / max(shape[:2]))


def resize_mask(mask: np.ndarray, size_wh: tuple[int, int]) -> np.ndarray:
    return cv2.resize(mask.astype(np.uint8), size_wh, interpolation=cv2.INTER_NEAREST).astype(bool)


def render_overlay(
    image: np.ndarray, leaf: np.ndarray, lesion: np.ndarray, pending: np.ndarray | None,
    scale: float, show_lesion: bool = True,
) -> np.ndarray:
    """Display image: leaf as a yellow outline + faint tint, lesion as red
    fill, pending (not yet committed) selection as cyan fill."""
    h, w = image.shape[:2]
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    out = cv2.resize(image, size, interpolation=cv2.INTER_AREA).astype(np.float32)

    def tint(m: np.ndarray, color: tuple[int, int, int], alpha: float) -> None:
        if m.any():
            out[m] = (1 - alpha) * out[m] + alpha * np.array(color, dtype=np.float32)

    leaf_d = resize_mask(leaf, size)
    tint(leaf_d, (255, 255, 0), 0.12)
    if show_lesion:
        tint(resize_mask(lesion, size), (255, 0, 0), 0.5)
    if pending is not None:
        tint(resize_mask(pending, size), (0, 255, 255), 0.5)
    if leaf_d.any():
        k = max(1, round(max(size) / 400))
        edge = leaf_d & ~cv2.erode(leaf_d.astype(np.uint8), np.ones((2 * k + 1, 2 * k + 1), np.uint8)).astype(bool)
        out[edge] = (255, 255, 0)
    return out.astype(np.uint8)


# ---------------------------------------------------------------- log + masks

def append_log(log_csv: Path, row: dict, fieldnames: list[str] = LOG_FIELDNAMES) -> None:
    """Append one row (append-only; the latest row per (set, name) wins).
    `fieldnames` lets the rating tool reuse this with its own log schema."""
    log_csv.parent.mkdir(parents=True, exist_ok=True)
    new = not log_csv.exists()
    with open(log_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_status(log_csv: Path, set_name: str) -> dict[str, dict]:
    """name -> latest log row for `set_name` (status 'done' or 'skipped')."""
    if not log_csv.exists():
        return {}
    with open(log_csv, encoding="utf-8") as f:
        return {r["name"]: r for r in csv.DictReader(f) if r["set"] == set_name}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mask_paths(out_dir: Path, set_name: str, name: str) -> tuple[Path, Path]:
    stem = Path(name).stem
    d = out_dir / set_name
    return d / f"{stem}_leaf.png", d / f"{stem}_lesion.png"


def save_masks(out_dir: Path, set_name: str, name: str, leaf: np.ndarray, lesion: np.ndarray) -> None:
    """Save full-resolution 0/255 PNG masks."""
    leaf_p, lesion_p = mask_paths(out_dir, set_name, name)
    leaf_p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(leaf.astype(np.uint8) * 255).save(leaf_p)
    Image.fromarray(lesion.astype(np.uint8) * 255).save(lesion_p)


# A leaf mask whose biggest connected piece holds less than this share of its
# pixels gets a warning + a "no single main leaf" skip suggestion. Warning only:
# a stem crossing the leaf can legitimately split it into two large parts.
FRAGMENT_WARN_BELOW = 0.8


def largest_part_fraction(mask: np.ndarray) -> float:
    """Share of the mask's pixels in its largest 8-connected component (1.0 = one piece)."""
    n_total = int(mask.sum())
    if n_total == 0:
        return 0.0
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return float(stats[1:, cv2.CC_STAT_AREA].max() / n_total)


def severity(leaf: np.ndarray, lesion: np.ndarray) -> float:
    """Lesion pixels on the leaf / leaf pixels."""
    n_leaf = int(leaf.sum())
    if n_leaf == 0:
        raise ValueError("Leaf mask is empty.")
    return float((lesion & leaf).sum() / n_leaf)


def sync_not_photo_retags(log_csv: Path, tags_csv: Path, reasons: tuple[str, ...] = (NOT_A_PHOTO,)) -> list[str]:
    """For every image skipped in the log for one of `reasons` whose current
    tag isn't already non_photo, append a human_annotation re-tag row to the
    tags CSV. Idempotent, so it's safe to run on every skip and at startup
    (which also catches skips made before this existed).
    Returns the names re-tagged on this call.
    """
    from src.data.wheat_tags import _latest_row_per_name, append_annotation_retag

    if not log_csv.exists():
        return []
    with open(log_csv, encoding="utf-8") as f:
        skipped = [r for r in csv.DictReader(f) if r["status"] == "skipped" and r["skip_reason"] in reasons]
    latest = _latest_row_per_name(tags_csv)
    done = []
    for r in skipped:
        existing = latest.get(r["name"])
        if existing and existing["tag"] != "non_photo" and r["name"] not in done:
            append_annotation_retag(
                tags_csv, r["name"], existing["plant"], r["disease"], r["split"], "non_photo",
                f"Phase 3 annotation ({r['set']} set): {r['skip_reason']}", now_iso(),
            )
            done.append(r["name"])
    return done


# ---------------------------------------------------------------- queue

def next_row(queues: dict[str, list[dict]], quotas: dict[str, int], status: dict[str, dict]) -> dict | None:
    """First disease (config order) still short of its quota, and its first
    queued image not yet done or skipped. None when every disease is either
    at quota or out of eligible images."""
    for disease, queue in queues.items():
        done = sum(1 for r in queue if status.get(r["name"], {}).get("status") == "done")
        if done >= quotas[disease]:
            continue
        for r in queue:
            if r["name"] not in status:
                return r
    return None


def progress(queues: dict[str, list[dict]], quotas: dict[str, int], status: dict[str, dict]) -> list[dict]:
    """Per-disease counts for the progress table."""
    out = []
    for disease, queue in queues.items():
        st = [status.get(r["name"], {}) for r in queue]
        out.append({
            "disease": disease,
            "done": sum(1 for s in st if s.get("status") == "done"),
            "quota": quotas[disease],
            "skipped": sum(1 for s in st if s.get("status") == "skipped"),
            "incomplete": sum(1 for s in st if s.get("status") == "done" and s.get("incomplete") == "true"),
            "left_in_queue": sum(1 for r in queue if r["name"] not in status),
        })
    return out


def set_finished(rows: list[dict]) -> bool:
    """True when every disease is at quota or has run out of eligible images."""
    return all(r["done"] >= r["quota"] or r["left_in_queue"] == 0 for r in rows)
