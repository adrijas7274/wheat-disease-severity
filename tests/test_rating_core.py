import csv
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.data.wheat_tags import _latest_row_per_name, load_tags
from src.severity import annotation_core as core
from src.severity import rating_core as rc
from src.utils.config import load_config


# ---------------------------------------------------------------- pure logic

def test_validate_rating():
    rc.validate_rating((3, 4), 0.0)  # 0% is a valid rating
    rc.validate_rating((3, 4), 100)
    for click, sev in [(None, 5), ((1, 1), None), ((1, 1), -0.5), ((1, 1), 100.5)]:
        with pytest.raises(ValueError):
            rc.validate_rating(click, sev)


def test_display_to_image_maps_and_clamps():
    assert rc.display_to_image((50, 20), 0.5, (100, 200, 3)) == (100, 40)
    assert rc.display_to_image((500, 500), 0.5, (100, 200, 3)) == (199, 99)


def test_draw_marker_only_touches_a_copy():
    img = np.zeros((100, 100, 3), np.uint8)
    assert (rc.draw_marker(img, None, 1.0) == img).all()
    out = rc.draw_marker(img, (50, 50), 1.0)
    assert out.any() and not img.any()
    assert out[50, 50].tolist() == [255, 0, 255]


def test_skip_reasons_and_retag_reasons():
    assert rc.COLLAGE in rc.SKIP_REASONS and core.NOT_A_PHOTO in rc.SKIP_REASONS
    assert set(rc.RETAG_REASONS) == {rc.COLLAGE, core.NOT_A_PHOTO}
    assert set(core.SKIP_REASONS) < set(rc.SKIP_REASONS)  # same reasons as the mask tool, plus collage


def test_seen_in_mask_pilots_and_exclusion(tmp_path: Path):
    mask_log = tmp_path / "annotation_log.csv"
    assert rc.seen_in_mask_pilots(mask_log) == set()
    core.append_log(mask_log, {"name": "a.jpg", "set": "pilot", "status": "done"})
    core.append_log(mask_log, {"name": "b.jpg", "set": "gold", "status": "done"})
    seen = rc.seen_in_mask_pilots(mask_log)
    assert seen == {"a.jpg"}

    rating_log = tmp_path / "rating_log.csv"
    status = rc.status_with_exclusions(rating_log, "pilot", seen)
    queues = {"d": [{"name": "a.jpg"}, {"name": "c.jpg"}]}
    assert core.next_row(queues, {"d": 1}, status)["name"] == "c.jpg"
    prog = core.progress(queues, {"d": 1}, status)[0]
    assert (prog["done"], prog["skipped"], prog["left_in_queue"]) == (0, 0, 1)


def test_mean_abs_diff():
    mad, diffs = rc.mean_abs_diff({"a": 10, "b": 2, "c": 7}, {"a": 14, "b": 1})
    assert mad == pytest.approx(2.5) and diffs == {"a": 4, "b": 1}
    with pytest.raises(ValueError):
        rc.mean_abs_diff({"a": 1}, {"b": 1})


def test_append_log_custom_fieldnames(tmp_path: Path):
    log = tmp_path / "r.csv"
    core.append_log(log, {"name": "x.jpg", "set": "gold", "severity_pct": 12.5, "unknown": 1}, rc.RATING_FIELDNAMES)
    with open(log, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == rc.RATING_FIELDNAMES and rows[0]["severity_pct"] == "12.5"


def test_gold_digest_changes_only_with_gold_rows(tmp_path: Path):
    log = tmp_path / "r.csv"
    core.append_log(log, {"name": "g.jpg", "set": "gold", "severity_pct": 5.0}, rc.RATING_FIELDNAMES)
    before = rc.gold_digest(log)
    core.append_log(log, {"name": "g.jpg", "set": "recheck", "severity_pct": 9.0}, rc.RATING_FIELDNAMES)
    assert rc.gold_digest(log) == before
    core.append_log(log, {"name": "g.jpg", "set": "gold", "severity_pct": 6.0}, rc.RATING_FIELDNAMES)
    assert rc.gold_digest(log) != before


def test_real_gold_ratings_match_the_lock():
    """Fails if any gold row in the real rating log changes after the lock."""
    config = load_config("configs/config.yaml")["annotation"]
    log = Path(config["out_dir"]) / config["rating_log"]
    assert config["gold_locked"] is True
    assert rc.gold_digest(log) == config["gold_sha256"]


def test_gold_exclusions_are_rated_gold_images():
    """Every evaluation exclusion must name an image that has a finished gold rating."""
    config = load_config("configs/config.yaml")["annotation"]
    status = core.load_status(Path(config["out_dir"]) / config["rating_log"], "gold")
    for name in config["gold_exclude"]:
        assert status[name]["status"] == "done"


# ---------------------------------------------------------------- tool handlers (no browser)

@pytest.fixture
def rater(tiny_config: dict, tmp_path: Path):
    from src.severity.rating_tool import Rater

    config = tiny_config | {"seed": 42, "annotation": {
        "out_dir": str(tmp_path / "ann"), "rating_log": "rating_log.csv", "recheck_n": 1,
        "sets": {"pilot": {"split": "Training", "per_disease": 1},
                 "tuning": {"split": "Validation", "per_disease": 1},
                 "gold": {"split": "Test", "per_disease": 1}},
    }}
    return Rater(config)


def _rows(r) -> list[dict]:
    with open(r.log_csv, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _refused(out, st) -> bool:
    """A refusal returns the same state and leaves every component unchanged."""
    return out[0] is st and all(o == {"__type__": "update"} for o in out[1:])


def test_tool_save_refusals_then_logs(rater):
    out = rater.load_next("pilot")
    st = out[0]
    assert st["row"]["name"] == "stripe_1.jpg"  # only eligible pilot image in the fixture
    assert _refused(rater.save("me", 12.0, 12.0, "", st), st)  # no click yet
    s = st["scale"]  # display copy is enlarged; clicks arrive in display pixels
    st, _, _ = rater.on_click(st, SimpleNamespace(index=(4.5 * s, 6.5 * s)))
    assert _refused(rater.save("me", None, 0, "", st), st)  # no severity yet
    assert _refused(rater.save("me", 150, 100, "", st), st)  # out of range
    assert _refused(rater.save("me", -1, 0, "", st), st)
    assert _refused(rater.save("me", 13.0, 14.5, "", st), st)  # number box and slider out of sync
    assert _refused(rater.save("  ", 12.0, 12.0, "", st), st)  # no rater name
    assert not rater.log_csv.exists()
    nxt = rater.save("me", 12.3, 12.5, " note ", st)  # slider snapping (<= 0.25) is fine
    assert nxt[0] is None  # pilot finished (leaf rust has no train close_up image)
    (row,) = _rows(rater)
    assert (row["status"], row["click_x"], row["click_y"], row["severity_pct"], row["notes"]) == (
        "done", "4", "6", "12.3", "note")
    assert (row["img_w"], row["img_h"]) == ("10", "10") and float(row["rating_s"]) >= 0


def test_tool_refuses_gold_writes_when_locked(rater):
    st = rater.load_next("gold")[0]
    s = st["scale"]
    st, _, _ = rater.on_click(st, SimpleNamespace(index=(4.5 * s, 6.5 * s)))
    rater.config["annotation"]["gold_locked"] = True
    assert _refused(rater.save("me", 12.0, 12.0, "", st), st)
    assert _refused(rater.skip("me", rc.COLLAGE, "", st), st)
    assert not rater.log_csv.exists()


def test_tool_collage_skip_retags_non_photo(rater):
    st = rater.load_next("pilot")[0]
    assert _refused(rater.skip("me", None, "", st), st)  # reason required
    assert _refused(rater.skip("", rc.COLLAGE, "", st), st)  # rater required
    assert not rater.log_csv.exists()
    rater.skip("me", rc.COLLAGE, "", st)
    row = _latest_row_per_name(rater.tags_csv)["stripe_1.jpg"]
    assert (row["tag"], row["original_tag"], row["tag_source"]) == ("non_photo", "close_up", "human_annotation")
    assert load_tags(rater.tags_csv)["stripe_1.jpg"] == "non_photo"


def test_tool_recheck_locked_until_gold_done_then_blind(rater):
    sentinel = {"set": "gold"}
    assert _refused(rater.load_next("recheck", sentinel), sentinel)  # locked: current image kept
    st = rater.load_next("gold")[0]
    assert st["row"]["name"] == "leaf_2.jpg"  # leaf_3 is disputed: excluded
    st, _, _ = rater.on_click(st, SimpleNamespace(index=(1, 1)))
    rater.save("me", 30.0, 30.0, "", st)
    st = rater.load_next("recheck")[0]
    assert st["row"]["name"] == "leaf_2.jpg" and st["click"] is None  # first click not carried over
    assert _refused(rater.skip("me", rc.COLLAGE, "", st), st)  # recheck images can't be skipped
    st, _, _ = rater.on_click(st, SimpleNamespace(index=(2, 2)))
    rater.save("me", 26.0, 26.0, "", st)
    gold = {r["name"]: float(r["severity_pct"]) for r in _rows(rater) if r["set"] == "gold"}
    rech = {r["name"]: float(r["severity_pct"]) for r in _rows(rater) if r["set"] == "recheck"}
    assert rc.mean_abs_diff(gold, rech)[0] == pytest.approx(4.0)


def test_tool_pilot_excludes_mask_pilot_images(rater):
    core.append_log(rater.mask_log_csv, {"name": "stripe_1.jpg", "set": "pilot", "status": "done"})
    assert rater.load_next("pilot")[0] is None


# ---------------------------------------------------------------- display scale, >75% confirm, training

def test_rating_display_scale_enlarges_small_and_maps_back():
    assert rc.rating_display_scale((174, 300, 3)) == pytest.approx(1600 / 300)  # small: enlarged
    assert rc.rating_display_scale((1200, 1600, 3)) == 1.0
    assert rc.rating_display_scale((3000, 4000, 3)) == pytest.approx(2048 / 4000)
    s = rc.rating_display_scale((174, 300, 3))
    # every original pixel survives the round trip through the enlarged display copy
    for x, y in [(0, 0), (150, 87), (299, 173)]:
        assert rc.display_to_image(((x + 0.5) * s, (y + 0.5) * s), s, (174, 300, 3)) == (x, y)


def test_needs_high_confirm():
    assert not rc.needs_high_confirm(75.0, None)
    assert rc.needs_high_confirm(80.0, None)
    assert not rc.needs_high_confirm(80.0, 80.0)
    assert rc.needs_high_confirm(81.0, 80.0)  # a changed value needs a new confirmation


def test_tool_high_rating_needs_second_save(rater):
    st = rater.load_next("pilot")[0]
    assert st["scale"] > 1  # the 10x10 fixture image is enlarged for display
    st, _, _ = rater.on_click(st, SimpleNamespace(index=(9.9 * st["scale"], 0)))
    assert st["click"] == (9, 0)  # logged in original pixels
    assert _refused(rater.save("me", 90.0, 90.0, "", st), st)
    assert not rater.log_csv.exists()
    assert _refused(rater.save("me", 85.0, 85.0, "", st), st)  # value changed: confirm again
    rater.save("me", 85.0, 85.0, "", st)
    assert _rows(rater)[0]["severity_pct"] == "85.0"


def test_tool_training_session_touches_only_its_report(rater, tmp_path: Path):
    rater.training_report = tmp_path / "rater_training.md"
    out = rater.train_start(None)
    tr = out[0]
    assert out[1].ndim == 3 and out[3] is None  # image shown, number box empty
    assert "true" not in out[2].lower()  # hidden value not shown before rating
    assert rater.train_next(tr)[1] == {"__type__": "update"}  # can't skip ahead unrated
    for i in range(15):
        res = rater.train_submit(10.0, "me", tr)
        assert "True:" in res[4]
        assert rater.train_submit(11.0, "me", tr)[4] == {"__type__": "update"}  # no double submit
        if i < 14:
            tr = rater.train_next(tr)[0]
    assert "Mean absolute error" in res[4] and tr["saved"]
    assert rater.training_report.read_text(encoding="utf-8").count("## Session") == 1
    assert not rater.log_csv.exists()  # no rating log touched
    tr2 = rater.train_start(tr)[0]  # repeat with a new set
    assert tr2["session"].seed != tr["session"].seed and tr2["idx"] == 0


# ---------------------------------------------------------------- smooth-workflow features

def test_tool_tuning_autoswitches_to_gold_with_counter(rater):
    out = rater.load_next("tuning")
    st = out[0]
    assert st["row"]["name"] == "leaf_1.jpg"  # the only tuning (val) image in the fixture
    assert "Tuning: 0 / 1" in out[12] and out[11] == {"__type__": "update", "value": "tuning"}
    assert "leaf_1.jpg" not in out[2] and "Validation" not in out[2]  # no file name or split shown
    st, _, _ = rater.on_click(st, SimpleNamespace(index=(1, 1)))
    out = rater.save("me", 5.0, 5.0, "", st)
    st = out[0]
    assert st["set"] == "gold" and st["row"]["name"] == "leaf_2.jpg"  # switched automatically
    assert "Tuning set finished" in out[2] and "Gold: 0 / 1" in out[12]
    assert out[11] == {"__type__": "update", "value": "gold"}  # Set dropdown follows
    assert st["n_session"] == 1  # session count carried over the switch
    st, _, _ = rater.on_click(st, SimpleNamespace(index=(1, 1)))
    out = rater.save("me", 6.0, 6.0, "", st)
    assert out[0] is None and "Gold set finished" in out[2] and "Gold: 1 / 1" in out[12]
    assert {r["set"] for r in _rows(rater)} == {"tuning", "gold"}


def test_tool_break_reminder_every_n(rater, monkeypatch):
    shown = []
    monkeypatch.setattr(gr_mod(), "Info", lambda msg, **k: shown.append(msg))
    rater.break_every = 2
    st = {"set": "pilot", "n_session": 0}
    monkeypatch.setattr(rater, "load_next", lambda s, prev=None: (prev,))
    rater._after_action(st)
    assert not shown
    rater._after_action(st)
    assert len(shown) == 1 and "break" in shown[0]


def test_tool_defaults_from_config(rater):
    assert rater.default_set == "tuning" and rater.break_every == 20


def gr_mod():
    import gradio

    return gradio
