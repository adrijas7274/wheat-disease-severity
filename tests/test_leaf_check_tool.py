from pathlib import Path

from src.severity import annotation_core as core
from src.severity import leaf_check_tool as lc
from src.utils.config import load_config


def test_gold_rows_are_the_rated_gold_images_minus_exclusions():
    config = load_config("configs/config.yaml")
    rows = lc.gold_rows(config)
    names = {r["name"] for r in rows}
    assert len(rows) == 50  # 54 rated - 4 in gold_exclude
    assert not names & set(config["annotation"]["gold_exclude"])
    assert all(r["set"] == "gold" and r["status"] == "done" for r in rows)


def test_load_verdicts_latest_row_wins(tmp_path):
    log = tmp_path / "log.csv"
    core.append_log(log, {"name": "a.jpg", "verdict": "correct"}, lc.LOG_FIELDS)
    core.append_log(log, {"name": "a.jpg", "verdict": "not_a_leaf"}, lc.LOG_FIELDS)
    assert lc.load_verdicts(log) == {"a.jpg": "not_a_leaf"}
    assert lc.load_verdicts(tmp_path / "missing.csv") == {}


def test_first_open_resumes_after_checked_images():
    order = ["a", "b", "c"]
    assert lc.first_open(order, {}) == 0
    assert lc.first_open(order, {"a": "correct", "c": "wrong"}) == 1
    assert lc.first_open(order, dict.fromkeys(order, "correct")) == 3


def test_categories_and_counts():
    rows = [{"name": n, "disease": d} for n, d in
            [("a", "wheat leaf rust"), ("b", "wheat leaf rust"), ("c", "wheat stripe rust"), ("d", "wheat stripe rust")]]
    verdicts = {"a": "correct", "b": "correct", "c": "not_a_leaf"}
    cats = lc.categories(rows, verdicts, {"b": "collage", "c": "collage"})
    # an exclusion reason replaces "correct" only; "d" has no verdict yet
    assert cats == {"a": "correct", "b": "collage", "c": "not_a_leaf", "d": "pending"}
    counts = lc.count_categories(rows, cats)
    assert counts["wheat leaf rust"]["correct"] == 1 and counts["wheat leaf rust"]["collage"] == 1
    assert counts["total"]["not_a_leaf"] == 1 and counts["total"]["pending"] == 1


def test_real_leaf_check_matches_the_lock():
    """Fails if any verdict in the real check log changes after the lock."""
    config = load_config("configs/config.yaml")
    ann = config["annotation"]
    assert ann["leaf_check_locked"] is True
    assert lc.verdict_digest(Path(ann["out_dir"]) / "leaf_check_log.csv") == ann["leaf_check_sha256"]


def test_real_evaluation_set_and_exclusion_reasons():
    config = load_config("configs/config.yaml")
    ann = config["annotation"]
    assert set(ann["gold_exclude_reasons"]) <= set(ann["gold_exclude"])
    assert set(ann["gold_exclude_reasons"].values()) <= set(lc.CATEGORIES)
    rows = lc.evaluated_gold_rows(config)
    assert len(rows) == 37
    assert not {r["name"] for r in rows} & set(ann["gold_exclude"])


def test_verdict_digest_ignores_superseded_rows(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    core.append_log(a, {"name": "x.jpg", "verdict": "correct"}, lc.LOG_FIELDS)
    core.append_log(a, {"name": "x.jpg", "verdict": "wrong"}, lc.LOG_FIELDS)
    core.append_log(b, {"name": "x.jpg", "verdict": "wrong"}, lc.LOG_FIELDS)
    assert lc.verdict_digest(a) == lc.verdict_digest(b)
