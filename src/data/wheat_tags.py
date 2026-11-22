"""Resumable, append-only CSV-backed tag storage for the wheat image-tagging
tool, with full provenance.

Every tagging action - human or AI review - appends a new row; nothing is
ever deleted or overwritten in place (except remove_last_tag, used only by
the live tool's explicit Undo button). The file is closed immediately after
each write, so progress survives a crash or a closed window.

Columns:
    name, plant, disease, split  - identify the image
    original_tag                 - the human's first-ever tag for this
                                    image, carried forward unchanged on every
                                    later row (including AI review rows)
    tag                          - the current/final tag (what load_tags()
                                    returns - this is what everything else in
                                    the pipeline should use)
    tag_source                   - "human" (tagging tool), "claude_review"
                                    (automated review pass) or
                                    "human_annotation" (re-tagged while
                                    annotating Phase 3 masks, e.g. a
                                    close_up that turned out not to be a photo)
                                    or "human_decision" (re-tagged by an explicit
                                    decision of the project owner outside the tools)
    tagged_at                    - when this row's action happened
    review_reason                - one-line reason, only set on claude_review rows
    disputed                     - "true"/"false". True where a blind
                                    inter-rater check found original_tag and
                                    an independent second tag disagreed. See
                                    report/tables/inter_rater_agreement.md.
                                    Carried forward like original_tag - not
                                    reset by ordinary re-tagging.
"""

import csv
from pathlib import Path

TAG_FIELDNAMES = [
    "name", "plant", "disease", "split", "original_tag", "tag", "tag_source",
    "tagged_at", "review_reason", "disputed",
]
VALID_TAGS = {"close_up", "wide", "non_photo", "skip"}
VALID_SOURCES = {"human", "claude_review", "human_annotation", "human_decision"}


def _all_rows(tags_csv: Path) -> list[dict]:
    if not tags_csv.exists():
        return []
    with open(tags_csv, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _latest_row_per_name(tags_csv: Path) -> dict[str, dict]:
    rows = {}
    for row in _all_rows(tags_csv):
        rows[row["name"]] = row  # dict insertion order -> last row per name wins
    return rows


def load_tags(tags_csv: Path) -> dict[str, str]:
    """name -> current/final tag. Empty dict if tagging hasn't started yet."""
    return {name: row["tag"] for name, row in _latest_row_per_name(tags_csv).items()}


def load_original_tags(tags_csv: Path) -> dict[str, str]:
    """name -> the human's original tag (unaffected by any later review)."""
    return {name: row["original_tag"] for name, row in _latest_row_per_name(tags_csv).items()}


def load_disputed(tags_csv: Path) -> dict[str, bool]:
    """name -> whether a blind inter-rater check disagreed with original_tag.
    Treat this as "worth a human recheck," not as a correctness signal - see
    docs/tagging_guidelines.md and experiments/LOG.md (2026-10-04).
    """
    return {
        name: row.get("disputed", "false") == "true"
        for name, row in _latest_row_per_name(tags_csv).items()
    }


def _write_row(tags_csv: Path, row: dict) -> None:
    tags_csv.parent.mkdir(parents=True, exist_ok=True)
    is_new = not tags_csv.exists()
    with open(tags_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TAG_FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def append_tag(tags_csv: Path, name: str, plant: str, disease: str, split: str, tag: str, tagged_at: str) -> None:
    """Human tagging path (used by the live tool's Tag and Review tabs).

    original_tag carries over from any existing row for this image, or
    equals `tag` itself if this image has never been tagged before.
    """
    if tag not in VALID_TAGS:
        raise ValueError(f"tag must be one of {sorted(VALID_TAGS)}, got {tag!r}")
    existing = _latest_row_per_name(tags_csv).get(name)
    original_tag = existing["original_tag"] if existing else tag
    disputed = existing.get("disputed", "false") if existing else "false"
    _write_row(tags_csv, {
        "name": name, "plant": plant, "disease": disease, "split": split,
        "original_tag": original_tag, "tag": tag, "tag_source": "human",
        "tagged_at": tagged_at, "review_reason": "", "disputed": disputed,
    })


def append_review_tag(
    tags_csv: Path, name: str, plant: str, disease: str, split: str,
    new_tag: str, reason: str, reviewed_at: str,
) -> None:
    """AI review path: change `tag` and record why, without ever touching
    original_tag. Raises if the image has never been tagged (nothing to review).
    """
    if new_tag not in VALID_TAGS:
        raise ValueError(f"new_tag must be one of {sorted(VALID_TAGS)}, got {new_tag!r}")
    existing = _latest_row_per_name(tags_csv).get(name)
    if existing is None:
        raise ValueError(f"{name!r} has never been tagged - nothing to review")
    _write_row(tags_csv, {
        "name": name, "plant": plant, "disease": disease, "split": split,
        "original_tag": existing["original_tag"], "tag": new_tag, "tag_source": "claude_review",
        "tagged_at": reviewed_at, "review_reason": reason,
        "disputed": existing.get("disputed", "false"),
    })


def append_annotation_retag(
    tags_csv: Path, name: str, plant: str, disease: str, split: str,
    new_tag: str, reason: str, retagged_at: str,
) -> None:
    """Phase 3 annotation-tool path: a human found the tag wrong while
    annotating masks. Like append_review_tag (original_tag and disputed are
    carried forward unchanged) but with tag_source "human_annotation".
    """
    if new_tag not in VALID_TAGS:
        raise ValueError(f"new_tag must be one of {sorted(VALID_TAGS)}, got {new_tag!r}")
    existing = _latest_row_per_name(tags_csv).get(name)
    if existing is None:
        raise ValueError(f"{name!r} has never been tagged - nothing to re-tag")
    _write_row(tags_csv, {
        "name": name, "plant": plant, "disease": disease, "split": split,
        "original_tag": existing["original_tag"], "tag": new_tag, "tag_source": "human_annotation",
        "tagged_at": retagged_at, "review_reason": reason,
        "disputed": existing.get("disputed", "false"),
    })


def append_decision_retag(tags_csv: Path, name: str, new_tag: str, reason: str, retagged_at: str) -> None:
    """Re-tag by an explicit human decision made outside the tagging and rating tools.
    Everything except tag, tag_source, tagged_at and review_reason is carried forward."""
    if new_tag not in VALID_TAGS:
        raise ValueError(f"new_tag must be one of {sorted(VALID_TAGS)}, got {new_tag!r}")
    existing = _latest_row_per_name(tags_csv).get(name)
    if existing is None:
        raise ValueError(f"{name!r} has never been tagged - nothing to re-tag")
    _write_row(tags_csv, existing | {"tag": new_tag, "tag_source": "human_decision",
                                     "tagged_at": retagged_at, "review_reason": reason})


def remove_last_tag(tags_csv: Path) -> str | None:
    """Undo: drop the last tagged row. Returns its name, or None if there was
    nothing to undo. Only used by the live tool's explicit Undo button.
    """
    if not tags_csv.exists():
        return None
    with open(tags_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    removed = rows.pop()
    with open(tags_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TAG_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return removed["name"]


def next_untagged_index(rows: list[dict], tags: dict[str, str], start: int = 0) -> int | None:
    """Index into `rows` of the first row (at or after `start`) not already in
    `tags`. None if everything is tagged.
    """
    for i in range(start, len(rows)):
        if rows[i]["name"] not in tags:
            return i
    return None
