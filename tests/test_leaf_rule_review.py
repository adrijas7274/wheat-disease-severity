import numpy as np

from src.severity import annotation_core as core
from src.severity import leaf_rule_review as lr
from src.utils.config import load_config

COMBOS = ["tiny + best_score", "tiny + min_area", "base_plus + best_score", "base_plus + min_area"]


def test_group_identical_merges_only_equal_masks():
    a = np.zeros((4, 4), bool)
    b = a.copy()
    b[0, 0] = True
    groups = lr.group_identical({"p": a, "q": b, "r": a.copy()})
    assert groups == [["p", "r"], ["q"]]


def test_tally_credits_every_combo_of_an_item():
    key = {"1": {"name": "x.jpg", "combos": COMBOS[:2]}, "2": {"name": "x.jpg", "combos": COMBOS[2:]},
           "3": {"name": "y.jpg", "combos": COMBOS}}
    counts = lr.tally(key, {"1": "yes", "3": "no"}, COMBOS)
    assert counts[COMBOS[0]] == {"yes": 1, "no": 1, "pending": 0}
    assert counts[COMBOS[3]] == {"yes": 0, "no": 1, "pending": 1}


def test_pick_winner_breaks_ties_by_preference_order():
    counts = {c: {"yes": 5} for c in COMBOS}
    assert lr.pick_winner(counts, COMBOS) == COMBOS[0]
    counts[COMBOS[2]]["yes"] = 6
    assert lr.pick_winner(counts, COMBOS) == COMBOS[2]


def test_load_verdicts_latest_row_wins(tmp_path):
    log = tmp_path / "log.csv"
    core.append_log(log, {"item": "7", "verdict": "yes"}, lr.LOG_FIELDS)
    core.append_log(log, {"item": "7", "verdict": "no"}, lr.LOG_FIELDS)
    assert lr.load_verdicts(log) == {"7": "no"}
    assert lr.load_verdicts(tmp_path / "missing.csv") == {}


def test_config_combos_are_in_tie_break_order():
    assert lr._combos(load_config("configs/config.yaml")) == COMBOS
