"""Phone-sized leaf finders for Phase 8, compared against the frozen SAM 2 tiny leaf rule.

Every promptable finder returns SAM-style candidates (3 masks + scores) for one positive tap, and the FROZEN leaf
rule (`src.severity.leaf_mask.select_leaf`, rule and min_share from configs/config.yaml) picks one, exactly as for
SAM 2. The tap + box finder has no candidates and returns one mask.

    mobile_sam      MobileSAM (TinyViT encoder + SAM decoder), ONNX from `src.mobile.export_leaf_models`
    efficient_sam   EfficientSAM-Ti, the authors' ONNX export
    grabcut         no model: OpenCV GrabCut inside a box built from the tap and the predicted infected region

All functions take an RGB uint8 image and a tap (x, y) in its pixels and return bool HxW masks.
"""

from pathlib import Path

import cv2
import numpy as np

MODEL_DIR = Path("data/mobile_models")
SAM_SIZE = 1024
PIXEL_MEAN = np.array([123.675, 116.28, 103.53], np.float32)
PIXEL_STD = np.array([58.395, 57.12, 57.375], np.float32)


def _session(path: Path, threads: int):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


def sam_preprocess(image: np.ndarray) -> tuple[np.ndarray, float]:
    """SAM input: long side resized to 1024 (bilinear), normalised, padded bottom/right; and the scale."""
    h, w = image.shape[:2]
    scale = SAM_SIZE / max(h, w)
    nh, nw = int(h * scale + 0.5), int(w * scale + 0.5)
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    padded = np.zeros((SAM_SIZE, SAM_SIZE, 3), np.float32)
    padded[:nh, :nw] = (resized - PIXEL_MEAN) / PIXEL_STD
    return padded.transpose(2, 0, 1)[None], scale


def sam_postprocess(low_res: np.ndarray, image_shape: tuple[int, ...], scale: float) -> np.ndarray:
    """(N, 256, 256) logits -> (N, H, W) bool: upsample to 1024, crop the padding, resize to the photo."""
    h, w = image_shape[:2]
    nh, nw = int(h * scale + 0.5), int(w * scale + 0.5)
    out = []
    for m in low_res:
        up = cv2.resize(m, (SAM_SIZE, SAM_SIZE), interpolation=cv2.INTER_LINEAR)[:nh, :nw]
        out.append(cv2.resize(up, (w, h), interpolation=cv2.INTER_LINEAR) > 0)
    return np.stack(out)


class MobileSam:
    """MobileSAM ONNX encoder + decoder. `int8` selects the quantised files."""

    def __init__(self, int8: bool = False, threads: int = 4, model_dir: Path = MODEL_DIR):
        suffix = "_int8" if int8 else ""
        self.encoder = _session(model_dir / f"mobile_sam_encoder{suffix}.onnx", threads)
        self.decoder = _session(model_dir / f"mobile_sam_decoder{suffix}.onnx", threads)

    def embed(self, image: np.ndarray) -> dict:
        x, scale = sam_preprocess(image)
        return {"emb": self.encoder.run(None, {"image": x})[0], "scale": scale, "shape": image.shape}

    def candidates(self, state: dict, click: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
        """The 3 multimask candidates and scores (SAM's masks 1-3; mask 0 is the single-mask output)."""
        s = state["scale"]
        pts = np.array([[[click[0] * s, click[1] * s], [0.0, 0.0]]], np.float32)
        labels = np.array([[1.0, -1.0]], np.float32)  # padding point, as in SAM's ONNX usage without a box
        low, scores = self.decoder.run(None, {"image_embeddings": state["emb"], "point_coords": pts, "point_labels": labels})
        return sam_postprocess(low[0, 1:4], state["shape"], s), scores[0, 1:4].astype(float)


class EfficientSam:
    """EfficientSAM-Ti ONNX encoder + decoder (the authors' export; the encoder resizes to 1024 itself)."""

    def __init__(self, int8: bool = False, threads: int = 4, model_dir: Path = MODEL_DIR, max_side: int = SAM_SIZE):
        suffix = "_int8" if int8 else ""
        self.encoder = _session(model_dir / f"efficient_sam_vitt_encoder{suffix}.onnx", threads)
        self.decoder = _session(model_dir / f"efficient_sam_vitt_decoder{suffix}.onnx", threads)
        self.max_side = max_side

    def embed(self, image: np.ndarray) -> dict:
        h, w = image.shape[:2]
        s = min(1.0, self.max_side / max(h, w))  # the decoder upsamples to its input size, so feed at most 1024
        small = cv2.resize(image, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else image
        x = small.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        return {"emb": self.encoder.run(None, {"batched_images": x})[0], "scale": s, "small_shape": small.shape,
                "shape": image.shape}

    def candidates(self, state: dict, click: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
        s = state["scale"]
        pts = np.array([[[[click[0] * s, click[1] * s]]]], np.float32)
        labels = np.array([[[1.0]]], np.float32)
        logits, iou, _ = self.decoder.run(None, {"image_embeddings": state["emb"], "batched_point_coords": pts,
                                                 "batched_point_labels": labels,
                                                 "orig_im_size": np.array(state["small_shape"][:2], np.int64)})
        h, w = state["shape"][:2]
        masks = [cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR) >= 0 for m in logits[0, 0]]
        return np.stack(masks), iou[0, 0].astype(float)


def tap_box(click: tuple[int, int], region: np.ndarray, image_shape: tuple[int, ...], window: float = 0.35,
            pad: float = 0.15) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1): a square of `window` x the short side around the tap, joined with the bounding box of the
    predicted-region component nearest to the tap, padded by `pad` and clipped to the image."""
    h, w = image_shape[:2]
    half = window * min(h, w) / 2
    x0, y0, x1, y1 = click[0] - half, click[1] - half, click[0] + half, click[1] + half
    if region.any():
        n, labels, stats, _ = cv2.connectedComponentsWithStats(region.astype(np.uint8), connectivity=8)
        ys, xs = np.nonzero(labels)
        nearest = labels[ys, xs][np.argmin((xs - click[0]) ** 2 + (ys - click[1]) ** 2)]
        cx, cy, cw, ch = stats[nearest, :4]
        x0, y0, x1, y1 = min(x0, cx), min(y0, cy), max(x1, cx + cw), max(y1, cy + ch)
    px, py = pad * (x1 - x0), pad * (y1 - y0)
    return (int(max(0, x0 - px)), int(max(0, y0 - py)), int(min(w - 1, x1 + px)), int(min(h - 1, y1 + py)))


def grabcut_leaf(image: np.ndarray, click: tuple[int, int], region: np.ndarray, work_side: int = 512,
                 iterations: int = 5) -> np.ndarray:
    """GrabCut in the tap box (outside = background, a disc at the tap = leaf, the predicted region = probable leaf),
    run at `work_side` px, then the connected part containing the tap."""
    h, w = image.shape[:2]
    s = min(1.0, work_side / max(h, w))
    small = cv2.resize(image, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    reg = cv2.resize(region.astype(np.uint8), small.shape[1::-1], interpolation=cv2.INTER_NEAREST).astype(bool)
    c = (min(small.shape[1] - 1, round(click[0] * s)), min(small.shape[0] - 1, round(click[1] * s)))
    x0, y0, x1, y1 = tap_box(c, reg, small.shape)
    # Outside the box is only *probable* background: wheat leaves are long and usually leave any automatic box, and
    # a definite-background outside would put the leaf's own colour into the background model. Only a thin image
    # border is definite background.
    mask = np.full(small.shape[:2], cv2.GC_PR_BGD, np.uint8)
    b = max(1, round(0.02 * min(small.shape[:2])))
    mask[:b], mask[-b:], mask[:, :b], mask[:, -b:] = cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD
    inside = np.zeros_like(reg)
    inside[y0:y1 + 1, x0:x1 + 1] = True
    mask[inside & (mask != cv2.GC_BGD)] = cv2.GC_PR_FGD
    cv2.circle(mask, c, max(2, round(0.02 * min(small.shape[:2]))), int(cv2.GC_FGD), -1)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), mask, None, bgd, fgd, iterations, cv2.GC_INIT_WITH_MASK)
    leaf = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    n, labels = cv2.connectedComponents(leaf, connectivity=8)
    if labels[c[1], c[0]]:
        leaf = (labels == labels[c[1], c[0]]).astype(np.uint8)
    return cv2.resize(leaf, (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
