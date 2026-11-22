import numpy as np
import pytest

from src.uncertainty import phase6_v2 as v2
from tests.test_phase6 import CONFIG, _rec, _split


def test_crosses_treats_zero_as_the_none_low_boundary():
    assert v2.crosses(0.0, 0.5, 0) and not v2.crosses(0.2, 0.5, 0)
    assert v2.crosses(5.0, 4.9, 5) and not v2.crosses(4.0, 4.9, 5)
    assert v2.crosses(float("nan"), 3.0, 20)


def test_flip_breakdown_answers_the_lowest_scores_first():
    recs = [dict(_rec("a", "jpeg", 1, s), clean_severity=4.0, flip=float(f)) for s, f in ((4.5, 0), (6.0, 1), (0.0, 1), (25.0, 1))]
    out = v2.flip_breakdown(recs, np.array([0.0, 1.0, 2.0, 3.0]), [0.5], [0, 5, 20])
    assert out["0.5"] == {"flip": 0.5, "0": 0.0, "5": 0.5, "20": 0.0}
    assert out["1.0"]["0"] == 0.25 and out["1.0"]["20"] == 0.25 and out["1.0"]["flip"] == 0.75


def test_thresholds_among_passed_use_the_passed_scores_only():
    thr = v2.thresholds_among_passed(np.arange(10, dtype=float), [0.8, 0.9])
    assert thr["0.8"] == pytest.approx(7.2) and thr["0.9"] == pytest.approx(8.1)


def test_fit_classifier_cv_returns_out_of_fold_predictions_for_every_record():
    from src.uncertainty import phase6 as p6

    recs = p6.add_errors(_split(12, 1), CONFIG, 3.64)
    predict, info, oof = v2.fit_classifier_cv(recs, True, 42, 5, [0.1, 1.0])
    assert len(oof) == len(recs) and info["C"] in (0.1, 1.0) and np.all((oof >= 0) & (oof <= 1))
    assert predict(recs[:5]).shape == (5,)
