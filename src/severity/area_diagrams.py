"""Synthetic standard area diagrams (SADs) for the Phase 3 rating tool.

A wheat-leaf-shaped outline with lesions covering an exact share of its
area (1, 2, 5, 10, 20, 35, 50, 75% by default) in three styles:
    rust    - many small pustules, elongated along the leaf
    blotch  - a few large irregular necrotic blotches with dark pycnidia dots
    mildew  - diffuse whitish patches

How "exact" is achieved: each style defines a random score field over the
image (sum of pustule-shaped kernels, or smoothed noise at a style-specific
scale). The lesion is the top-k leaf pixels by score, with
k = round(pct/100 * leaf pixels), so the lesion area is exact to one pixel
whatever the field looks like. The field only controls the *shape* of the
lesions. Rendering never changes which pixels are lesion (pycnidia dots and
mildew texture are drawn inside the lesion, the outline outside the leaf).

Made from scratch for this project (no copyrighted diagrams). Nothing here
reads the severity pipeline's thresholds, so the diagrams stay independent
of the methods being evaluated.

Usage:
    python -m src.severity.area_diagrams --config configs/config.yaml
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.utils.config import load_config

LEVELS = (1, 2, 5, 10, 20, 35, 50, 75)
STYLES = ("rust", "blotch", "mildew")
OUT_DIR = Path("report/figures/area_diagrams")
DISEASE_STYLE = {  # which panel the rating tool opens first for each disease
    "wheat stripe rust": "rust",
    "wheat leaf rust": "rust",
    "wheat powdery mildew": "mildew",
    "wheat septoria blotch": "blotch",
    "wheat bacterial leaf streak (black chaff)": "blotch",
}

LEAF_W, LEAF_H, LEAF_HALF = 900, 130, 48  # canvas per leaf, max half-width of the blade
BG = (255, 255, 255)
LEAF_RGB = (78, 145, 62)
OUTLINE_RGB = (30, 70, 25)
LESION_RGB = {"rust": (214, 118, 28), "blotch": (128, 84, 44), "mildew": (236, 236, 226)}
PYCNIDIA_RGB = (35, 22, 12)


def leaf_mask(width: int = LEAF_W, height: int = LEAF_H, max_half: float = LEAF_HALF) -> np.ndarray:
    """Boolean mask of a horizontal wheat-leaf blade: blunt base on the left,
    long taper to a pointed tip on the right, slight arch."""
    margin = 10
    xs = np.arange(width)
    t = np.clip((xs - margin) / (width - 2 * margin), 0.0, 1.0)
    half = max_half * np.minimum(t / 0.06, 1.0) ** 0.5 * (1.0 - t) ** 0.6
    half[(xs < margin) | (xs > width - margin)] = 0.0
    centre = height / 2 + 10 * np.sin(np.pi * t) - 5
    ys = np.arange(height)[:, None]
    return np.abs(ys - centre[None, :]) < half[None, :]


def _score_field(leaf: np.ndarray, pct: float, style: str, rng: np.random.Generator) -> np.ndarray:
    """Random field whose top-k leaf pixels form lesions of the given style."""
    h, w = leaf.shape
    n_target = pct / 100 * leaf.sum()
    if style == "rust":
        # Pustules ~ 11x5 px, laid in rough lanes along the leaf like stripe/leaf rust.
        n = max(3, int(np.ceil(n_target / 40 * 1.4)))
        ys, xs = np.nonzero(leaf)
        pick = rng.integers(0, len(xs), n)
        impulses = np.zeros((h, w), np.float32)
        impulses[ys[pick], xs[pick]] = 1.0
        field = cv2.GaussianBlur(impulses, (0, 0), sigmaX=4.0, sigmaY=1.6)
    elif style == "blotch":
        noise = rng.standard_normal((h, w)).astype(np.float32)
        field = cv2.GaussianBlur(noise, (0, 0), sigmaX=38, sigmaY=11)
        # Mild pull toward the leaf interior, so small blotches aren't slivers on the edge.
        dist = cv2.distanceTransform(leaf.astype(np.uint8), cv2.DIST_L2, 5)
        field = field / (field.std() + 1e-9) + 1.0 * dist / (dist.max() + 1e-9)
    elif style == "mildew":
        noise = rng.standard_normal((h, w)).astype(np.float32)
        field = cv2.GaussianBlur(noise, (0, 0), sigmaX=14, sigmaY=6)
        field += 0.15 * cv2.GaussianBlur(noise, (0, 0), sigmaX=3, sigmaY=3)
    else:
        raise ValueError(f"style must be one of {STYLES}, got {style!r}")
    return field + 1e-6 * rng.random((h, w), dtype=np.float32)  # break ties so top-k is exact


def lesion_mask(leaf: np.ndarray, pct: float, style: str, seed: int) -> np.ndarray:
    """Lesion mask inside `leaf` covering exactly round(pct% of leaf pixels) pixels."""
    if not 0 <= pct <= 100:
        raise ValueError(f"pct must be in [0, 100], got {pct}")
    rng = np.random.default_rng(seed)
    field = _score_field(leaf, pct, style, rng)
    k = int(round(pct / 100 * leaf.sum()))
    ys, xs = np.nonzero(leaf)
    order = np.argsort(field[ys, xs])[::-1][:k]
    out = np.zeros_like(leaf)
    out[ys[order], xs[order]] = True
    return out


def render_leaf(leaf: np.ndarray, lesion: np.ndarray, style: str, seed: int) -> np.ndarray:
    """RGB image of one diagram leaf. Only lesion pixels get lesion colours,
    and the outline sits just outside the leaf, so the drawn areas match the masks."""
    rng = np.random.default_rng(seed + 1)
    img = np.full((*leaf.shape, 3), BG, np.uint8)
    outline = cv2.dilate(leaf.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & ~leaf
    img[outline] = OUTLINE_RGB
    img[leaf] = LEAF_RGB
    img[lesion] = LESION_RGB[style]
    if style == "blotch":  # pycnidia: sparse dark dots, only on lesion pixels
        dots = lesion & (rng.random(leaf.shape) < 0.02)
        dots = cv2.dilate(dots.astype(np.uint8), np.ones((2, 2), np.uint8)).astype(bool) & lesion
        img[dots] = PYCNIDIA_RGB
    elif style == "mildew":  # powdery texture: brightness jitter on lesion pixels only
        jitter = rng.integers(-18, 8, size=(int(lesion.sum()), 1))
        img[lesion] = np.clip(img[lesion].astype(int) + jitter, 0, 255).astype(np.uint8)
    return img


def make_panel(style: str, seed: int, levels: tuple[int, ...] = LEVELS) -> tuple[Image.Image, list[dict]]:
    """One reference panel (all levels, one style, stacked) + measured coverage per leaf."""
    leaf = leaf_mask()
    label_w, title_h = 90, 36
    panel = Image.new("RGB", (label_w + LEAF_W, title_h + LEAF_H * len(levels)), BG)
    draw = ImageDraw.Draw(panel)
    try:
        font = ImageFont.truetype("arial.ttf", 26)
        title_font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = title_font = ImageFont.load_default()
    draw.text((8, 6), f"{style}-like lesions: % of leaf area affected (synthetic diagram)", fill=(0, 0, 0), font=title_font)
    rows = []
    for i, pct in enumerate(levels):
        leaf_seed = seed * 1000 + STYLES.index(style) * 100 + i
        lesion = lesion_mask(leaf, pct, style, leaf_seed)
        y = title_h + i * LEAF_H
        panel.paste(Image.fromarray(render_leaf(leaf, lesion, style, leaf_seed)), (label_w, y))
        draw.text((10, y + LEAF_H // 2 - 14), f"{pct}%", fill=(0, 0, 0), font=font)
        rows.append({"style": style, "target_pct": pct, "leaf_px": int(leaf.sum()),
                     "lesion_px": int(lesion.sum()), "measured_pct": round(100 * lesion.sum() / leaf.sum(), 4)})
    return panel, rows


def panel_path(style: str, out_dir: Path = OUT_DIR) -> Path:
    return out_dir / f"sad_{style}.png"


def generate_all(seed: int, out_dir: Path = OUT_DIR) -> list[dict]:
    """Write one PNG per style plus coverage.csv (target vs measured %)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for style in STYLES:
        panel, rows = make_panel(style, seed)
        panel.save(panel_path(style, out_dir))
        all_rows += rows
    with open(out_dir / "coverage.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    return all_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic standard area diagrams")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    rows = generate_all(load_config(args.config)["seed"], args.out)
    for r in rows:
        print(f"{r['style']:>6} target {r['target_pct']:>2}%  measured {r['measured_pct']:.4f}%")
    print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()
