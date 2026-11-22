"""Condition cache: the expensive, method-independent parts of every (image, corruption, level).

For each image of a split and each condition (clean, the ten corruptions x five
levels, and the ablation chains) it stores

    leaf      the SAM 2 leaf for the image's click (frozen leaf rule), re-run on the corrupted image
    region    a model's predicted infected region, at photo resolution
    tta       the same model's region when the input is mirrored (left-right, up-down), mirrored back
    entropy   mean softmax entropy of the model (whole image, and inside its predicted region)
    iou       region IoU against the PlantSeg mask, in the model's padded space (as in Phase 2)

The colour rule, the severity, the Phase 5 preprocessing variants and the Phase 6
gate and uncertainty scores are all cheap functions of (corrupted image, leaf,
region), so they are computed later from this cache without the GPU. The
corrupted image is not stored: it is regenerated deterministically.

Click: the Phase 4 rule (deepest point of the largest infected component that the
click model predicts on the clean image). Splits: `val` and `test` (close_up),
never gold-specific data: no rating and no stored click is read here.

Files (gitignored): `<cache_dir>/<split>/<image name>.leaf.npz` and
`<cache_dir>/<split>/<image name>.<model key>.npz`.

Usage:
    python -m src.corruptions.cache --config configs/config.yaml --experiment configs/experiments/phase5_colour_stage.yaml \
        --model segformer [--splits val test] [--debug]
"""

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from src.corruptions.corruptions import ABLATION_CHAINS, CORRUPTIONS, N_LEVELS, corrupt
from src.utils.config import load_config

CLEAN = ("clean", 0)


def all_conditions(include_ablation: bool = True) -> list[tuple[str, int]]:
    """Clean first, then every corruption x level, then the ablation chains."""
    names = list(CORRUPTIONS) + (list(ABLATION_CHAINS) if include_ablation else [])
    return [CLEAN] + [(n, lv) for n in names for lv in range(1, N_LEVELS + 1)]


def condition_image(image: np.ndarray, condition: tuple[str, int], seed: int, name: str) -> np.ndarray:
    """The (deterministic) corrupted image of one condition; the clean image itself for `clean`."""
    return image if condition[0] == "clean" else corrupt(image, condition[0], int(condition[1]), seed, name)


def pack(mask: np.ndarray) -> np.ndarray:
    return np.packbits(mask.astype(bool))


def unpack(bits: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    return np.unpackbits(bits, count=shape[0] * shape[1]).astype(bool).reshape(shape)


def split_entries(config: dict, split: str) -> list[dict]:
    """close_up images of a split: name, disease, image and mask path."""
    from src.data.wheat_metadata import image_path, mask_path
    from src.data.wheat_severity_dataset import WheatSeverityDataset

    ds = WheatSeverityDataset(config, split=split, subset="close_up")
    return [{"name": r["name"], "disease": r["disease"], "image_path": str(image_path(ds.plantseg_dir, r)),
             "mask_path": str(mask_path(ds.plantseg_dir, r))} for r in ds.rows]


class ConditionCache:
    """Read access to one split of the cache."""

    def __init__(self, cache_dir: str | Path, split: str):
        self.dir = Path(cache_dir) / split

    def has(self, name: str, kind: str) -> bool:
        return (self.dir / f"{name}.{kind}.npz").exists()

    def load(self, name: str, kind: str) -> dict:
        """{'meta': dict, 'masks': {key: packed bits}} of one file (`kind` = 'leaf' or a model key)."""
        with np.load(self.dir / f"{name}.{kind}.npz") as z:
            return {"meta": json.loads(str(z["meta"])), "masks": {k: z[k] for k in z.files if k != "meta"}}

    @staticmethod
    def mask(blob: dict, key: str) -> np.ndarray:
        return unpack(blob["masks"][key], tuple(blob["meta"]["shape"]))

    def save(self, name: str, kind: str, meta: dict, masks: dict[str, np.ndarray]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{name}.{kind}.tmp.npz"
        np.savez_compressed(tmp, meta=json.dumps(meta), **{k: pack(m) for k, m in masks.items()})
        tmp.replace(self.dir / f"{name}.{kind}.npz")


def model_outputs(model, image: np.ndarray, mask: np.ndarray, image_size: int, device) -> dict:
    """Region, mirrored-input regions, entropy and IoU of one model on one image."""
    import torch

    from src.data.severity_transforms import build_transform
    from src.models.inference import resize_mask
    from src.severity.metrics import binary_iou

    out = build_transform(image_size, train=False)(image=image, masks=[mask.astype(np.uint8), np.ones(image.shape[:2], np.uint8)])
    x = out["image"].unsqueeze(0).to(device)
    with torch.no_grad():
        batch = torch.cat([x, torch.flip(x, dims=[3]), torch.flip(x, dims=[2])])
        logits = model(batch)
        logits = torch.stack([logits[0], torch.flip(logits[1], dims=[2]), torch.flip(logits[2], dims=[1])])
        prob = torch.softmax(logits, dim=1)
        entropy = -(prob * torch.log(prob.clamp_min(1e-8))).sum(dim=1)[0].cpu().numpy()
        preds = prob.argmax(dim=1).cpu().numpy().astype(bool)
    true, valid = np.asarray(out["masks"][0]) > 0, np.asarray(out["masks"][1]) > 0
    ys, xs = np.nonzero(valid)
    crop = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
    in_region = preds[0] & valid
    return {
        "region_small": preds[0][crop],
        "masks": {k: resize_mask(p[crop], image.shape) for k, p in zip(("region", "tta_lr", "tta_ud"), preds)},
        "iou": binary_iou(preds[0], true),
        "entropy_image": float(entropy[valid].mean()),
        "entropy_region": float(entropy[in_region].mean()) if in_region.any() else float("nan"),
    }


def build_image(entry: dict, cache: ConditionCache, model_key: str, model, predictor, conditions: list[tuple[str, int]],
                config: dict, image_size: int, device, with_leaf: bool) -> None:
    """Write the model file of one image, and its leaf file when `with_leaf` (the model is then the click model)."""
    from PIL import Image

    from src.models.inference import resize_mask
    from src.severity.auto_click import click_from_region
    from src.severity.leaf_mask import leaf_from_click

    image = np.array(Image.open(entry["image_path"]).convert("RGB"))
    mask = np.array(Image.open(entry["mask_path"]).convert("L")) > 0
    if mask.shape != image.shape[:2]:
        mask = resize_mask(mask, image.shape)
    base = {"name": entry["name"], "disease": entry["disease"], "shape": list(image.shape[:2]),
            "conditions": [list(c) for c in conditions]}
    model_masks, leaf_masks, stats, click = {}, {}, [], None
    for i, cond in enumerate(conditions):
        img = condition_image(image, cond, config["seed"], entry["name"])
        out = model_outputs(model, img, mask, image_size, device)
        for k, m in out["masks"].items():
            model_masks[f"{k}_{i}"] = m
        stats.append({"iou": out["iou"], "entropy_image": out["entropy_image"], "entropy_region": out["entropy_region"]})
        if with_leaf:
            if click is None:  # the clean image comes first
                click = click_from_region(out["region_small"], image.shape)
            predictor.set_image(img)
            leaf_masks[f"leaf_{i}"] = leaf_from_click(predictor, click, config)
    if with_leaf:
        cache.save(entry["name"], "leaf", base | {"click": list(click)}, leaf_masks)
    cache.save(entry["name"], model_key, base | {"stats": stats}, model_masks)


def main() -> None:
    import torch

    from src.models.inference import load_baseline
    from src.severity.sam2_model import load_sam2_predictor

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--experiment", default="configs/experiments/phase5_colour_stage.yaml")
    parser.add_argument("--model", required=True, help="model key in the experiment YAML's `models`")
    parser.add_argument("--splits", nargs="+", default=["val", "test"])
    parser.add_argument("--debug", action="store_true", help="2 images per split (every condition, so the Phase 5 and 6 reports can be built), separate cache folder")
    args = parser.parse_args()
    config = load_config(args.config)
    experiment = yaml.safe_load(Path(args.experiment).read_text(encoding="utf-8"))
    spec = experiment["models"][args.model]
    with_leaf = args.model == experiment["click_model"]
    conditions = all_conditions()
    cache_dir = Path(experiment["cache_dir"] + ("_debug" if args.debug else ""))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_baseline(spec["architecture"], spec["checkpoint"], device)
    predictor = load_sam2_predictor(config) if with_leaf else None
    for split in args.splits:
        cache = ConditionCache(cache_dir, split)
        entries = split_entries(config, split)[:2] if args.debug else split_entries(config, split)
        for k, entry in enumerate(entries, 1):
            if cache.has(entry["name"], args.model) and (not with_leaf or cache.has(entry["name"], "leaf")):
                continue
            if not with_leaf and not cache.has(entry["name"], "leaf"):
                raise RuntimeError(f"No leaf file for {entry['name']}: build the click model ({experiment['click_model']}) first.")
            build_image(entry, cache, args.model, model, predictor, conditions, config, config["image"]["size"], device, with_leaf)
            print(f"[{split}] {k}/{len(entries)} {entry['name']}", flush=True)
    print(f"Cache complete: {cache_dir}")


if __name__ == "__main__":
    main()
