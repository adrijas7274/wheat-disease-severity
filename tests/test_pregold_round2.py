import numpy as np

from src.severity import pregold_round2 as r2
from src.severity import refinement as rf

GREEN, ORANGE, YELLOW = (40, 140, 40), (220, 120, 30), (220, 160, 30)


def _image(*colours: tuple[int, int, int]) -> np.ndarray:
    return np.concatenate([np.full((10, 10, 3), c, np.uint8) for c in colours], axis=1)


def test_c1_without_halo_keeps_only_lesion_colour():
    image = _image(ORANGE, YELLOW, GREEN, YELLOW)
    region = np.ones(image.shape[:2], bool)
    kept = rf.refine_c1(region, image, "rust", 20, halo=False)
    assert kept[:, :10].all() and not kept[:, 10:].any()
    with_halo = rf.refine_c1(region, image, "rust", 20)
    assert with_halo[:, :20].all()  # default unchanged: the touching yellow stripe is added


def _records() -> list[dict]:
    # option (10, True) is exact on every image, (20, False) is 10 points too high
    return [{"name": f"n{i}", "disease": "wheat septoria blotch", "group": "necrotic", "rating": rating,
             "c1": {"B": {(10, True): rating, (20, False): rating + 10}, "A": {(10, True): rating, (20, False): rating}}}
            for i, rating in enumerate([5.0, 10.0, 15.0])]


def test_options_order():
    cand = {g: {"thresholds": [1, 2], "halo": [True, False]} for g in rf.GROUPS}
    assert r2.options(cand)["rust"] == [(1, True), (2, True), (1, False), (2, False)]


def test_candidate_chooses_best_option_also_inside_folds():
    grid = {"rust": [(10, True)], "necrotic": [(20, False), (10, True)], "mildew": [(8, True)]}
    res = r2.evaluate_candidate(_records(), grid, "B")
    assert res["chosen"]["necrotic"] == {"threshold": 10, "halo": True} and res["chosen"]["rust"] is None
    assert res["in_sample"]["mae"] == 0 and res["leave_one_out"]["mae"] == 0


def test_change_rule_needs_more_than_the_limit():
    mk = lambda m: {"leave_one_out": {"mae": m}}
    assert r2.decide({"v1": mk(17.0), "E": mk(14.0), "F": mk(15.0)}, 3.64)["winner"] == "v1"
    d = r2.decide({"v1": mk(17.0), "E": mk(13.0), "F": mk(9.0)}, 3.64)
    assert d["winner"] == "F" and d["changed"] and d["passing"] == ["E", "F"]
    assert r2.decide({"v1": mk(17.0), "E": mk(9.0), "F": mk(9.0)}, 3.64)["winner"] == "E"  # tie goes to E
