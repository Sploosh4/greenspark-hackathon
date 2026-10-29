"""Leakage and correctness tests. Run: python -m pytest -q test_seasonal.py"""
import numpy as np
import pandas as pd
import pytest

import seasonal as S


@pytest.fixture(scope="module")
def data():
    return S.load()


def test_grid_complete_and_plausible(data):
    last = S.tindex(2026, 9)
    assert len(data.cells) == 255
    assert np.isfinite(data.temp[:, : last + 1]).all()
    assert 0 < np.nanmin(data.temp) and np.nanmax(data.temp) < 45
    assert data.partial.sum() == 1 and data.partial[S.tindex(2026, 10)]


def test_cell_id_matches_screenshot_convention():
    assert S.cell_id(-18.2, 125.57) == "-18.5_125.5"  # Fitzroy Crossing: 18-19°S, 125-126°E


def test_baseline_ignores_data_after_cutoff(data):
    cutoff = S.tindex(2010, 1)
    a = S.fit_baseline(data.temp, cutoff)
    poisoned = data.temp.copy()
    poisoned[:, cutoff:] += 50
    b = S.fit_baseline(poisoned, cutoff)
    assert np.allclose(a.clim, b.clim) and np.allclose(a.slope, b.slope)


def test_features_do_not_see_target_or_later_months(data):
    """Changing any month >= issue must leave that issue's features unchanged."""
    issue = S.tindex(2015, 6)
    base = S.fit_baseline(data.temp, S.tindex(2015, 1))
    r1 = S.build_rows(data, base, [issue])
    poisoned = S.Data(data.cells, data.temp.copy(), data.partial, data.nino34.copy(), data.sam.copy())
    poisoned.temp[:, issue:] += 50
    poisoned.nino34[issue:] += 5
    poisoned.sam[issue:] += 5
    r2 = S.build_rows(poisoned, base, [issue])
    feats = [f for f in S.FEATURES]
    pd.testing.assert_frame_equal(r1[feats], r2[feats])
    assert not np.allclose(r1.y, r2.y)  # the targets did change, so the poisoning reached the right months


def test_lead_one_targets_issue_month(data):
    base = S.fit_baseline(data.temp, S.tindex(2015, 1))
    r = S.build_rows(data, base, [S.tindex(2015, 10)])
    assert (r[r.lead == 1].target_t == S.tindex(2015, 10)).all()
    assert (r[r.lead == 6].target_t == S.tindex(2016, 3)).all()


def test_prob_above_is_calibrated_gaussian():
    assert S.prob_above(20.0, 20.0, 1.0) == pytest.approx(0.5)
    assert S.prob_above(21.2816, 20.0, 1.0) == pytest.approx(0.9, abs=1e-3)


def test_hindcast_has_no_future_training():
    """Each hindcast row was issued in its test year, and no test year scores a partial month."""
    path = S.ROOT / "outputs" / "hindcast_predictions.csv.gz"
    if not path.exists():
        pytest.skip("run run_backtest.py first")
    h = pd.read_csv(path)
    issue_year = S.START_YEAR + h.issue // 12
    assert (issue_year == h.test_year).all()
    assert h.target_t.max() <= S.tindex(2026, 9)
    assert h.groupby(["test_year", "issue", "lead", "cell"]).size().max() == 1
