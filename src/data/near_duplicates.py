"""Near-duplicate check across the PlantSeg splits for the configured crop.

Every train, val and test image of the configured disease classes (all tags,
so nothing is hidden by the tagging) gets a 64-bit difference hash (dHash) and
a 32 x 32 grey thumbnail. A pair is a **candidate** if the hashes differ in at
most `MAX_HAMMING` bits, and a **near-duplicate** if the thumbnails also agree
(mean absolute difference at most `MAX_THUMB_DIFF` grey levels out of 255).

Why two tests: dHash is fast and survives resizing and re-compression, but it
also matches unrelated photos that share a simple layout (one diagonal leaf on
a blurred background). The thumbnail test removes most of those.

What it can't find: crops, mirrored or rotated copies, and copies with a
watermark or border over a large part of the image.

By default this script only reports. With `--write-exclusions` it also writes the
leakage fix decided on 2026-11-14 to `data.split_exclude_file` (see `build_exclusions`),
which `WheatSeverityDataset` applies to train and val. Test is never changed.

    python -m src.data.near_duplicates                      # writes report/tables/near_duplicates.md + a pair sheet
    python -m src.data.near_duplicates --write-exclusions   # also (re)writes the exclusion list
    python -m src.data.near_duplicates --debug              # first 20 images per split
"""

import argparse
import csv
import json
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
from PIL import Image

from src.data.wheat_metadata import filter_by_crop_and_disease, image_path, load_metadata_rows
from src.data.wheat_tags import load_disputed, load_tags
from src.utils.config import load_config
from src.utils.experiment import create_experiment_dir

MAX_HAMMING = 6        # of 64 bits
MAX_THUMB_DIFF = 12.0  # mean absolute grey-level difference of the 32 x 32 thumbnails
TABLE = Path("report/tables/near_duplicates.md")
SHEET = Path("report/figures/near_duplicates/pairs.png")
SPLIT_ORDER = {"Training": 0, "Validation": 1, "Test": 2}


def dhash(img: Image.Image) -> np.ndarray:
    """64-bit difference hash: is each pixel of a 9 x 8 grey thumbnail brighter than its right neighbour."""
    small = np.asarray(img.convert("L").resize((9, 8), Image.LANCZOS), dtype=np.int16)
    return (small[:, 1:] > small[:, :-1]).flatten()


def thumbnail(img: Image.Image) -> np.ndarray:
    """32 x 32 grey thumbnail as float32."""
    return np.asarray(img.convert("L").resize((32, 32), Image.LANCZOS), dtype=np.float32)


def find_pairs(hashes: np.ndarray, thumbs: np.ndarray, max_hamming: int = MAX_HAMMING,
               max_thumb_diff: float = MAX_THUMB_DIFF) -> list[tuple[int, int, int, float]]:
    """(i, j, hamming distance, thumbnail difference) for every near-duplicate pair, i < j."""
    bits = hashes.astype(np.int32)
    dist = bits @ (1 - bits).T + (1 - bits) @ bits.T
    out = []
    for i, j in zip(*np.nonzero(np.triu(dist <= max_hamming, k=1))):
        diff = float(np.abs(thumbs[i] - thumbs[j]).mean())
        if diff <= max_thumb_diff:
            out.append((int(i), int(j), int(dist[i, j]), diff))
    return out


def groups(n: int, pairs: list[tuple[int, int, int, float]]) -> list[list[int]]:
    """Connected groups of near-duplicates (union-find), each sorted, groups of 2 or more only."""
    parent = list(range(n))

    def root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, *_ in pairs:
        parent[root(i)] = root(j)
    by_root: dict[int, list[int]] = {}
    for i in range(n):
        by_root.setdefault(root(i), []).append(i)
    return sorted(g for g in by_root.values() if len(g) > 1)


def build_exclusions(rows: list[dict], pairs: list[tuple[int, int, int, float]]) -> dict[str, list[dict]]:
    """The leakage fix (Adrija, 2026-11-14), from the near-duplicate groups. Test is never touched.

    - train: every image in a group that also has a val or test image is removed; in a group
      that is train-only, one copy is kept (a close_up one if there is one, then first by name).
    - val: an image in a group that also has a test image is removed. Raises if it has a tuning rating.
    - `test_with_train_copy` lists (it does not exclude) the Phase 2 test images that had a copy
      in the Phase 2 training set, for re-scoring the original models without them.
    """
    exclude, leaked = [], []
    for group in groups(len(rows), pairs):
        members = [rows[i] for i in group]
        by_split = {s: [r for r in members if r["split"] == s] for s in SPLIT_ORDER}
        held_out = by_split["Validation"] + by_split["Test"]
        if held_out:
            ref = (by_split["Test"] or by_split["Validation"])[0]
            exclude += [{"name": r["name"], "split": "Training",
                         "reason": f"copy of {ref['name']} ({ref['split']})"} for r in by_split["Training"]]
        elif len(by_split["Training"]) > 1:
            keep = sorted(by_split["Training"], key=lambda r: (r["tag"] != "close_up", r["name"]))[0]
            exclude += [{"name": r["name"], "split": "Training",
                         "reason": f"copy of {keep['name']} (Training), which is kept"}
                        for r in by_split["Training"] if r is not keep]
        if by_split["Test"]:
            for r in by_split["Validation"]:
                if r["rated_set"]:
                    raise ValueError(f"{r['name']} has a {r['rated_set']} rating, so it is not removed from val automatically")
                exclude.append({"name": r["name"], "split": "Validation",
                                "reason": f"copy of {by_split['Test'][0]['name']} (Test)"})
            train_copies = [r["name"] for r in by_split["Training"] if r["phase2"]]
            if train_copies:
                leaked += [{"name": r["name"], "train_copy": train_copies[0]} for r in by_split["Test"] if r["phase2"]]

    def key(e: dict) -> tuple[int, str]:
        return SPLIT_ORDER.get(e.get("split", "Test"), 2), e["name"]

    return {"exclude": sorted(exclude, key=key), "test_with_train_copy": sorted(leaked, key=key)}


def write_exclusions(config: dict, exclusions: dict[str, list[dict]]) -> Path:
    """Write the exclusion list as YAML to `data.split_exclude_file`."""
    import yaml

    out = Path(config["data"]["split_exclude_file"])
    header = ("# Written by `python -m src.data.near_duplicates --write-exclusions`. Do not edit by hand.\n"
              "# Leakage fix decided by Adrija on 2026-11-14 (experiments/LOG.md): duplicate photos removed from\n"
              "# train and val. `exclude` is applied by WheatSeverityDataset; test is never changed.\n"
              "# `test_with_train_copy` only lists the Phase 2 test images that had a copy in the old training set.\n")
    out.write_text(header + yaml.safe_dump(exclusions, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
    return out


def load_rows(config: dict) -> list[dict]:
    """Metadata rows of the configured crop and diseases, with tag, disputed flag and annotation-set membership."""
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = filter_by_crop_and_disease(load_metadata_rows(plantseg_dir / "Metadata.csv"),
                                      config["crop"], config["disease_classes"])
    tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
    tags, disputed = load_tags(tags_csv), load_disputed(tags_csv)
    ann = config["annotation"]
    rated: dict[str, str] = {}
    with open(Path(ann["out_dir"]) / ann["rating_log"], encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["set"] in ("tuning", "gold") and r["status"] == "done":
                rated[r["name"]] = r["set"]
    for r in rows:
        r["tag"] = tags.get(r["name"], "untagged")
        r["disputed"] = disputed.get(r["name"], False)
        r["rated_set"] = rated.get(r["name"], "")
        # the Phase 2 subsets (src/data/wheat_severity_dataset.py): close_up, and non-disputed on test
        r["phase2"] = r["tag"] == "close_up" and not (r["split"] == "Test" and r["disputed"])
    return sorted(rows, key=lambda r: (SPLIT_ORDER[r["split"]], r["name"]))


def _describe(r: dict) -> str:
    extra = [r["tag"]] + (["disputed"] if r["disputed"] else []) + ([f"rated {r['rated_set']}"] if r["rated_set"] else [])
    return f"`{r['name']}` ({r['split']}; {', '.join(extra)})"


def _pair_sheet(config: dict, rows: list[dict], pairs: list[tuple[int, int, int, float]], out: Path, tile: int = 300) -> None:
    """Side-by-side thumbnails of every cross-split pair, numbered as in the report."""
    import cv2

    plantseg_dir = Path(config["data"]["plantseg_dir"])
    strips = []
    for n, (i, j, d, diff) in enumerate(pairs, 1):
        strip = np.full((tile + 30, 2 * tile + 10, 3), 255, np.uint8)
        for k, idx in enumerate((i, j)):
            img = np.asarray(Image.open(image_path(plantseg_dir, rows[idx])).convert("RGB"))[:, :, ::-1]
            s = tile / max(img.shape[:2])
            img = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
            strip[: img.shape[0], k * (tile + 10): k * (tile + 10) + img.shape[1]] = img
        cv2.putText(strip, f"{n}. {rows[i]['split']} / {rows[j]['split']}  bits {d}", (4, tile + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
        strips.append(strip)
    cols = 3
    while len(strips) % cols:
        strips.append(np.full_like(strips[0], 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack([np.hstack(strips[k:k + cols]) for k in range(0, len(strips), cols)]))


def run(config: dict, config_path: str, debug: bool, write: bool = False) -> None:
    """Hash every image, find near-duplicate pairs and write the report (and, with `write`, the exclusion list)."""
    rows = load_rows(config)
    if debug:
        rows = [r for s in SPLIT_ORDER for r in [x for x in rows if x["split"] == s][:20]]
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    hashes, thumbs = [], []
    for r in rows:
        with Image.open(image_path(plantseg_dir, r)) as img:
            img = img.convert("RGB")
            hashes.append(dhash(img))
            thumbs.append(thumbnail(img))
    pairs = find_pairs(np.array(hashes), np.array(thumbs))
    cross = [p for p in pairs if rows[p[0]]["split"] != rows[p[1]]["split"]]

    def section(title: str, keep) -> list[str]:
        sel = [p for p in pairs if keep(rows[p[0]], rows[p[1]])]
        lines = ["", f"## {title}: {len(sel)} pair(s)", ""]
        if sel:
            lines += ["| # | image A | image B | hash bits apart | thumbnail diff |", "|---:|---|---|---:|---:|"]
            lines += [f"| {cross.index(p) + 1 if p in cross else '-'} | {_describe(rows[p[0]])} | {_describe(rows[p[1]])} | {p[2]} | {p[3]:.1f} |"
                      for p in sel]
        return lines

    def splits(a: dict, b: dict, s1: str, s2: str) -> bool:
        return {a["split"], b["split"]} == {s1, s2}

    n_split = {s: sum(r["split"] == s for r in rows) for s in SPLIT_ORDER}
    lines = [f"# Near-duplicate check, {config['crop']} ({date.today().isoformat()})", "",
             "Generated by `python -m src.data.near_duplicates`" + (" --debug" if debug else "") + ". Report only: nothing was changed.", "",
             f"Images hashed: {len(rows)} ({n_split['Training']} train, {n_split['Validation']} val, {n_split['Test']} test), "
             "all tags, the configured disease classes.", "",
             f"A pair is listed if the 64-bit dHash differs in at most {MAX_HAMMING} bits and the 32 x 32 grey thumbnails differ by "
             f"at most {MAX_THUMB_DIFF:g} grey levels on average. Crops, mirrored or rotated copies and heavily watermarked copies "
             "are not found by this method. The `#` column is the pair's number on the pair sheet "
             f"(`{SHEET.as_posix()}`, cross-split pairs only).", "",
             f"**Totals:** {len(pairs)} pair(s) in {len(groups(len(rows), pairs))} group(s); {len(cross)} pair(s) cross a split boundary."]
    lines += section("Within gold (both images have a finished gold rating)",
                     lambda a, b: a["rated_set"] == b["rated_set"] == "gold")
    lines += section("Between tuning and gold (rated images)",
                     lambda a, b: {a["rated_set"], b["rated_set"]} == {"tuning", "gold"})
    lines += section("Train / test, both in the Phase 2 sets (close_up; test non-disputed)",
                     lambda a, b: splits(a, b, "Training", "Test") and a["phase2"] and b["phase2"])
    lines += section("Train / test, at least one image outside the Phase 2 sets",
                     lambda a, b: splits(a, b, "Training", "Test") and not (a["phase2"] and b["phase2"]))
    lines += section("Train / val", lambda a, b: splits(a, b, "Training", "Validation"))
    lines += section("Val / test", lambda a, b: splits(a, b, "Validation", "Test"))
    lines += section("Within one split", lambda a, b: a["split"] == b["split"])
    conflicts = [p for p in pairs if rows[p[0]]["disease"] != rows[p[1]]["disease"]]
    lines += ["", f"## Label conflicts (same photo, two disease names): {len(conflicts)} pair(s)", "",
              "Labels were not changed. `rated` marks a tuning or gold image.", "",
              "| image A | label A | image B | label B | rated |", "|---|---|---|---|---|"]
    for i, j, *_ in conflicts:
        a, b = rows[i], rows[j]
        rated = "; ".join(f"{r['name']}: {r['rated_set']}" for r in (a, b) if r["rated_set"]) or "-"
        lines.append(f"| `{a['name']}` ({a['split']}) | {a['disease'].replace('wheat ', '')} | `{b['name']}` ({b['split']}) "
                     f"| {b['disease'].replace('wheat ', '')} | {rated} |")
    if write and not debug:
        exclusions = build_exclusions(rows, pairs)
        out = write_exclusions(config, exclusions)
        n = {s: sum(e["split"] == s for e in exclusions["exclude"]) for s in SPLIT_ORDER}
        lines += ["", "## Exclusion list", "",
                  f"Written to `{out.as_posix()}`: {n['Training']} train and {n['Validation']} val images removed; "
                  f"{len(exclusions['test_with_train_copy'])} Phase 2 test images listed as having had a copy in training."]
    table = TABLE.with_name("near_duplicates_debug.md") if debug else TABLE
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sheet = SHEET.with_name("pairs_debug.png") if debug else SHEET
    if cross:
        _pair_sheet(config, rows, cross, sheet)
    exp_dir = create_experiment_dir("near_duplicates" + ("_debug" if debug else ""), config_path)
    (exp_dir / "metrics.json").write_text(json.dumps({
        "n_images": len(rows), "n_pairs": len(pairs), "n_cross_split_pairs": len(cross),
        "max_hamming": MAX_HAMMING, "max_thumb_diff": MAX_THUMB_DIFF,
        "pairs": [{"a": rows[i]["name"], "b": rows[j]["name"], "split_a": rows[i]["split"], "split_b": rows[j]["split"],
                   "hamming": d, "thumb_diff": round(diff, 2)} for i, j, d, diff in pairs],
    }, indent=1), encoding="utf-8")
    print("\n".join(lines[6:]))
    print(f"\nWrote {table}; {exp_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--write-exclusions", action="store_true", help="also write data.split_exclude_file")
    args = parser.parse_args()
    run(load_config(args.config), args.config, args.debug, args.write_exclusions)


if __name__ == "__main__":
    main()
