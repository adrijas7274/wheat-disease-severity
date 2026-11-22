"""Seeded, non-overlapping image lists for Phase 3 annotation sets.

Sets (see docs/annotation_guidelines.md and the `annotation` section of
configs/config.yaml):
    pilot  - from Training, timing / tool shake-out only
    tuning - from Validation, threshold and prompt tuning only
    gold   - from Test, evaluated once at the end

Eligibility is the same for every set: the image's latest tag is `close_up`
and it is not disputed. Each disease's eligible images are shuffled with the
config seed, giving a fixed annotation *queue*. The queue is longer than the
quota on purpose: if an image is skipped (for a reason the guidelines
allow), the next one in the queue takes its place. The order never changes,
so the annotator can't choose which images get in.
"""

import random
from pathlib import Path

from src.data.wheat_metadata import filter_by_crop_and_disease, load_metadata_rows
from src.data.wheat_tags import load_disputed, load_tags

VALID_SETS = ("pilot", "tuning", "gold")


def eligible_rows(config: dict, split: str) -> list[dict]:
    """Metadata rows for one PlantSeg split ('Training'/'Validation'/'Test')
    that are non-disputed close_up images of a configured disease, sorted by name."""
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = load_metadata_rows(plantseg_dir / "Metadata.csv")
    rows = filter_by_crop_and_disease(rows, config["crop"], config["disease_classes"])
    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
    tags = load_tags(tags_csv)
    disputed = load_disputed(tags_csv)
    keep = [
        r for r in rows
        if r["split"] == split and tags.get(r["name"]) == "close_up" and not disputed.get(r["name"], False)
    ]
    return sorted(keep, key=lambda r: r["name"])


def shuffled_queue(rows: list[dict], seed: int, salt: str) -> list[dict]:
    """Deterministic shuffle of `rows`. `salt` (e.g. set + disease) gives each
    queue its own order while staying reproducible from the one config seed."""
    out = list(rows)
    random.Random(f"{seed}:{salt}").shuffle(out)
    return out


def build_queues(config: dict, set_name: str) -> dict[str, list[dict]]:
    """disease -> full shuffled queue of eligible rows for `set_name`."""
    if set_name not in VALID_SETS:
        raise ValueError(f"set_name must be one of {VALID_SETS}, got {set_name!r}")
    split = config["annotation"]["sets"][set_name]["split"]
    rows = eligible_rows(config, split)
    return {
        disease: shuffled_queue([r for r in rows if r["disease"] == disease], config["seed"], f"{set_name}:{disease}")
        for disease in config["disease_classes"]
    }


QUEUE_FIELDS = ["position", "name", "plant", "disease", "split"]


def frozen_queues(config: dict, set_name: str, queue_dir: Path) -> dict[str, list[dict]]:
    """Like build_queues, but the result is saved to `queue_dir/<set>.csv` the
    first time and read back from there afterwards.

    Why: re-tagging an image (e.g. to non_photo) changes the eligible list,
    and a seeded shuffle of a list one item shorter is a completely different
    order. Freezing keeps the annotation order fixed for the whole set, and
    keeps re-tagged images in the queue (logged as skipped) so they still
    show up in the skip counts.
    """
    import csv

    path = queue_dir / f"{set_name}.csv"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        queues: dict[str, list[dict]] = {d: [] for d in config["disease_classes"]}
        for r in sorted(rows, key=lambda r: int(r["position"])):
            queues[r["disease"]].append({k: r[k] for k in QUEUE_FIELDS if k != "position"})
        return queues
    queues = build_queues(config, set_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        pos = 0
        for q in queues.values():
            for r in q:
                writer.writerow({"position": pos, **{k: r[k] for k in QUEUE_FIELDS if k != "position"}})
                pos += 1
    return {d: [{k: r[k] for k in QUEUE_FIELDS if k != "position"} for r in q] for d, q in queues.items()}


def quota(config: dict, set_name: str, n_available: int) -> int:
    """Images wanted for one disease: the configured per-disease count, capped
    at what's available (wheat leaf rust gold: 10 < 11)."""
    return min(config["annotation"]["sets"][set_name]["per_disease"], n_available)


def pick_recheck(gold_names: list[str], n: int, seed: int) -> list[str]:
    """Seeded random pick of `n` finished gold images for the blind
    self-consistency re-annotation. Sorted input makes it order-independent."""
    names = sorted(gold_names)
    if len(names) < n:
        raise ValueError(f"Need {n} finished gold images for the recheck, have {len(names)}.")
    return random.Random(f"{seed}:recheck").sample(names, n)
