from pathlib import Path

from src.data.wheat_self_check import (
    cohens_kappa, parse_agreement_report, sample_balanced_tagged_rows, write_agreement_report,
)
from src.data.wheat_tags import append_tag


def test_cohens_kappa_perfect_agreement() -> None:
    results = [
        ("a.jpg", "d", "close_up", "close_up"),
        ("b.jpg", "d", "wide", "wide"),
        ("c.jpg", "d", "close_up", "close_up"),
        ("d.jpg", "d", "wide", "wide"),
    ]
    assert cohens_kappa(results) == 1.0


def test_cohens_kappa_dominant_category_near_zero() -> None:
    # 29 close_up/close_up matches + 1 wide/close_up mismatch - the exact
    # shape of the real self-check result. High raw agreement (29/30) but
    # the single dominant retag category means almost all of that agreement
    # is expected by chance, so kappa should be ~0, not high.
    results = [("x.jpg", "d", "close_up", "close_up")] * 29 + [("y.jpg", "d", "wide", "close_up")]
    kappa = cohens_kappa(results)
    assert kappa is not None
    assert abs(kappa - 0.0) < 1e-9


def test_cohens_kappa_too_few_results() -> None:
    assert cohens_kappa([]) is None
    assert cohens_kappa([("a.jpg", "d", "close_up", "close_up")]) is None


def test_parse_agreement_report_roundtrip(tmp_path: Path) -> None:
    results = [
        ("a.jpg", "wheat stripe rust", "close_up", "close_up"),
        ("b.jpg", "wheat bacterial leaf streak (black chaff)", "wide", "close_up"),
    ]
    out_path = tmp_path / "tagging_agreement.md"
    write_agreement_report(results, out_path)

    parsed = parse_agreement_report(out_path)

    assert parsed == results


def test_sample_balanced_tagged_rows_only_includes_tagged(tmp_path: Path) -> None:
    tags_csv = tmp_path / "tags.csv"
    append_tag(tags_csv, "a.jpg", "Wheat", "wheat stripe rust", "train", "close_up", "ts")
    append_tag(tags_csv, "b.jpg", "Wheat", "wheat leaf rust", "val", "wide", "ts")

    all_rows = [
        {"name": "a.jpg", "disease": "wheat stripe rust"},
        {"name": "b.jpg", "disease": "wheat leaf rust"},
        {"name": "c.jpg", "disease": "wheat powdery mildew"},  # untagged
    ]

    sample = sample_balanced_tagged_rows(all_rows, tags_csv, n_close_up=20)

    names = {r["name"] for r in sample}
    assert names == {"a.jpg", "b.jpg"}
    by_name = {r["name"]: r["original_tag"] for r in sample}
    assert by_name == {"a.jpg": "close_up", "b.jpg": "wide"}


def test_sample_balanced_tagged_rows_caps_close_up_but_keeps_all_others(tmp_path: Path) -> None:
    tags_csv = tmp_path / "tags.csv"
    all_rows = []
    # 50 close_up images (should be capped down to n_close_up=5)
    for i in range(50):
        name = f"cu_{i}.jpg"
        append_tag(tags_csv, name, "Wheat", "wheat stripe rust", "train", "close_up", "ts")
        all_rows.append({"name": name, "disease": "wheat stripe rust"})
    # a handful of non-close_up tags (should ALL be kept regardless of n_close_up)
    for tag in ["wide", "wide", "non_photo", "skip"]:
        name = f"{tag}_{len(all_rows)}.jpg"
        append_tag(tags_csv, name, "Wheat", "wheat stripe rust", "train", tag, "ts")
        all_rows.append({"name": name, "disease": "wheat stripe rust"})

    sample = sample_balanced_tagged_rows(all_rows, tags_csv, n_close_up=5)

    close_up_count = sum(1 for r in sample if r["original_tag"] == "close_up")
    other_count = sum(1 for r in sample if r["original_tag"] != "close_up")
    assert close_up_count == 5
    assert other_count == 4  # every non-close_up row included, none dropped
    assert len(sample) == 9


def test_sample_balanced_tagged_rows_fewer_close_up_than_requested(tmp_path: Path) -> None:
    tags_csv = tmp_path / "tags.csv"
    append_tag(tags_csv, "a.jpg", "Wheat", "wheat stripe rust", "train", "close_up", "ts")
    all_rows = [{"name": "a.jpg", "disease": "wheat stripe rust"}]

    sample = sample_balanced_tagged_rows(all_rows, tags_csv, n_close_up=20)

    assert len(sample) == 1  # doesn't error when fewer close_up images exist than requested


def test_write_agreement_report(tmp_path: Path) -> None:
    results = [
        ("a.jpg", "wheat stripe rust", "close_up", "close_up"),
        ("b.jpg", "wheat leaf rust", "wide", "close_up"),
    ]
    out_path = tmp_path / "tagging_agreement.md"

    summary = write_agreement_report(results, out_path)

    assert summary["n"] == 2
    assert summary["matches"] == 1
    assert summary["pct"] == 50.0
    assert summary["kappa"] is not None
    content = out_path.read_text(encoding="utf-8")
    assert "Agreement: 1/2 (50.0%)" in content
    assert "Cohen's kappa:" in content
    assert "a.jpg" in content and "b.jpg" in content


def test_write_agreement_report_empty(tmp_path: Path) -> None:
    out_path = tmp_path / "tagging_agreement.md"
    summary = write_agreement_report([], out_path)
    assert summary == {"n": 0, "matches": 0, "pct": 0.0, "kappa": None}
    assert "Cohen's kappa: n/a" in out_path.read_text(encoding="utf-8")
