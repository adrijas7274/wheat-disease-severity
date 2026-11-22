from pathlib import Path

import numpy as np
import pytest

from src.severity import area_diagrams as sad
from src.severity import rater_training as rt


def test_session_shape_and_range():
    s = rt.make_session(seed=5)
    assert len(s.leaves) == rt.N_LEAVES
    assert sorted(lf.style for lf in s.leaves).count("rust") == 5  # 5 per style
    assert {lf.style for lf in s.leaves} == set(sad.STYLES)
    for lf in s.leaves:
        assert rt.MIN_PCT <= lf.target_pct <= rt.MAX_PCT
        assert lf.target_pct * 2 == int(lf.target_pct * 2)  # rounded to 0.5
        assert abs(lf.true_pct - lf.target_pct) < 0.01  # exact to one pixel


def test_sessions_differ_by_seed_and_repeat_by_seed():
    a, b = rt.make_session(1), rt.make_session(2)
    assert [lf.target_pct for lf in a.leaves] != [lf.target_pct for lf in b.leaves]
    assert [lf.target_pct for lf in a.leaves] == [lf.target_pct for lf in rt.make_session(1).leaves]


def test_severities_cover_low_range():
    targets = np.concatenate([[lf.target_pct for lf in rt.make_session(k).leaves] for k in range(20)])
    assert (targets < 5).mean() > 0.3  # log-uniform: plenty of practice below 5%


def test_render_matches_true_area():
    lf = rt.make_session(3).leaves[0]
    img = rt.render(lf, upscale=1.0)
    leaf = sad.leaf_mask()
    lesion_px = (img[leaf] == sad.LEAF_RGB).all(axis=1).sum()
    assert leaf.sum() - lesion_px == round(lf.target_pct / 100 * leaf.sum())


def test_summary_bias_and_report(tmp_path: Path):
    s = rt.make_session(4)
    with pytest.raises(ValueError):
        rt.summary(s)
    for lf in s.leaves:
        lf.rating = lf.true_pct + 2.0  # overestimate everything by 2
    sm = rt.summary(s)
    assert sm["n"] == 15 and sm["mae"] == pytest.approx(2.0) and sm["bias"] == pytest.approx(2.0)
    assert "overestimate" in rt.bias_sentence(sm["bias"])
    assert "underestimate" in rt.bias_sentence(-3.0) and "No clear" in rt.bias_sentence(0.2)
    out = tmp_path / "rt.md"
    rt.append_report(out, s, "me")
    rt.append_report(out, s, "me")  # repeating appends a second session
    text = out.read_text(encoding="utf-8")
    assert text.count("## Session") == 2 and text.count("# Rater training") == 1
    assert "Mean absolute error: 2.00" in text
