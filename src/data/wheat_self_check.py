"""Self-agreement check: re-tag a random sample of already-tagged images with
tags hidden, and measure how often the re-tag matches the original.

This is an intra-rater reliability check, not a correctness check - see
docs/tagging_guidelines.md.
"""

import random
import re
from datetime import datetime, timezone
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from src.data.wheat_tags import load_tags


def sample_balanced_tagged_rows(all_rows: list[dict], tags_csv: Path, n_close_up: int = 20) -> list[dict]:
    """Stratified self-check sample: ~n_close_up random close_up images plus
    every wide, non_photo, and skip image, shuffled together, each annotated
    with its original_tag. Unseeded - a fresh sample each call.

    Uniform random sampling over a tag distribution this skewed toward
    close_up (see cohens_kappa docstring) mostly just re-samples close_up,
    which made a prior self-check's kappa come out ~0 despite 96.7% raw
    agreement - not because tagging was unreliable, but because the sample
    had almost no variation to actually test. Including every non-close_up
    tag guarantees the sample can distinguish real agreement from chance.
    """
    tags = load_tags(tags_csv)
    tagged = [dict(r, original_tag=tags[r["name"]]) for r in all_rows if r["name"] in tags]
    close_up = [r for r in tagged if r["original_tag"] == "close_up"]
    others = [r for r in tagged if r["original_tag"] != "close_up"]
    sample = random.sample(close_up, min(n_close_up, len(close_up))) + others
    random.shuffle(sample)
    return sample


def cohens_kappa(results: list[tuple[str, str, str, str]]) -> float | None:
    """Cohen's kappa between original_tag and retag over `results`
    (name, disease, original_tag, new_tag). None if there are fewer than 2
    results (undefined).

    Kappa corrects raw agreement for the agreement expected by chance given
    how skewed the tag distribution is - with this project's tags dominated
    by close_up, a rater who always said "close_up" would score high raw
    agreement despite having no real discriminative signal. Kappa near 0
    despite high raw agreement means exactly that: results depend heavily on
    the realised sample, not just raw-agreement intuition.
    """
    if len(results) < 2:
        return None
    originals = [r[2] for r in results]
    retags = [r[3] for r in results]
    return float(cohen_kappa_score(originals, retags))


_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(?:yes|\*\*no\*\*)\s*\|\s*$")


def parse_agreement_report(path: Path) -> list[tuple[str, str, str, str]]:
    """Parse the (name, disease, original_tag, new_tag) rows back out of an
    already-written report/tables/tagging_agreement.md, so kappa (or
    anything else) can be recomputed without needing the original in-memory
    session.
    """
    results = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ROW_RE.match(line)
        if match and match.group(1) != "name":  # skip the header row
            results.append(match.groups())
    return results


def write_agreement_report(results: list[tuple[str, str, str, str]], out_path: Path) -> dict:
    """results: list of (name, disease, original_tag, new_tag).

    Writes report/tables/tagging_agreement.md and returns a summary dict
    {n, matches, pct, kappa}.
    """
    n = len(results)
    matches = sum(1 for _, _, orig, new in results if orig == new)
    pct = 100.0 * matches / n if n else 0.0
    kappa = cohens_kappa(results)

    lines = [
        "# Tagging self-agreement check",
        "",
        f"Date: {datetime.now(timezone.utc).isoformat()}",
        f"Sample size: {n}",
        f"Agreement: {matches}/{n} ({pct:.1f}%)",
        f"Cohen's kappa: {kappa:.3f}" if kappa is not None else "Cohen's kappa: n/a (fewer than 2 results)",
        "",
        "| name | disease | original_tag | retag | match |",
        "|---|---|---|---|---|",
    ]
    for name, disease, orig, new in results:
        match_str = "yes" if orig == new else "**no**"
        lines.append(f"| {name} | {disease} | {orig} | {new} | {match_str} |")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"n": n, "matches": matches, "pct": pct, "kappa": kappa}
