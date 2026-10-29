"""Monthly-mean temperature outlook for WA 1-degree cells.

Forecast convention follows Copernicus C3S: an issue in month I uses observations up to the end of
month I-1 and covers lead 1..6 = months I..I+5 (lead 1 includes the issue month).

Everything is expressed relative to a *fold-local* baseline (cell-by-calendar-month climatology plus a
per-cell linear warming trend) fitted only on months before the training cutoff, so no future
observation reaches a feature, a baseline or a model.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
START_YEAR = 1981
LEADS = np.arange(1, 7)
MIN_PARTIAL_DAYS = 15  # a current-month mean needs at least this many valid days

# Named localities (approximate town coordinates) mapped to the 1-degree cell containing them.
LOCALITIES = {
    "Kununurra": (-15.77, 128.74), "Broome": (-17.96, 122.24), "Fitzroy Crossing": (-18.20, 125.57),
    "Halls Creek": (-18.22, 127.67), "Port Hedland": (-20.31, 118.60), "Karratha": (-20.74, 116.85),
    "Carnarvon": (-24.88, 113.66), "Geraldton": (-28.78, 114.61), "Kalgoorlie": (-30.75, 121.47),
    "Perth": (-31.95, 115.86), "Esperance": (-33.86, 121.89),
}


def cell_id(lat, lon):
    return f"{np.floor(lat) + 0.5:+.1f}_{np.floor(lon) + 0.5:.1f}"


def tindex(year, month):
    return (year - START_YEAR) * 12 + (month - 1)


def tdate(t):
    return START_YEAR + t // 12, t % 12 + 1


@dataclass
class Data:
    cells: pd.DataFrame          # cell, lat, lon, elevation, land_frac
    temp: np.ndarray             # (n_cells, n_t) monthly mean T2M, NaN where missing
    partial: np.ndarray          # (n_t,) True where the month was built from an incomplete daily record
    nino34: np.ndarray           # (n_t,) Nino 3.4 anomaly
    sam: np.ndarray              # (n_t,) SAM / AAO index

    @property
    def n_t(self):
        return self.temp.shape[1]


def _power_values(path):
    v = json.loads(path.read_text())["properties"]["parameter"]["T2M"]
    return {k: (np.nan if x <= -990 else x) for k, x in v.items()}


def _read_sstoi(path, n_t):
    out = np.full(n_t, np.nan)
    for line in path.read_text().splitlines()[1:]:
        p = line.split()
        if len(p) >= 10:
            t = tindex(int(p[0]), int(p[1]))
            if 0 <= t < n_t:
                out[t] = float(p[9])  # NINO3.4 ANOM
    return out


def _read_aao(path, n_t):
    out = np.full(n_t, np.nan)
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) == 3:
            t = tindex(int(p[0]), int(p[1]))
            if 0 <= t < n_t:
                out[t] = float(p[2])
    return out


def load(end_year=2026, end_month=12):
    cells = pd.DataFrame(json.loads((ROOT / "data" / "cells.json").read_text()))
    n_t = tindex(end_year, end_month) + 1
    temp = np.full((len(cells), n_t), np.nan)
    partial = np.zeros(n_t, bool)
    for i, c in enumerate(cells.cell):
        for k, x in _power_values(RAW / "power_monthly" / f"{c}.json").items():
            y, m = int(k[:4]), int(k[4:])
            if m <= 12 and tindex(y, m) < n_t:
                temp[i, tindex(y, m)] = x
        # Fill months the monthly product does not have yet from daily values.
        daily = _power_values(RAW / "power_daily_202610" / f"{c}.json")
        by_month = {}
        for k, x in daily.items():
            by_month.setdefault((int(k[:4]), int(k[4:6])), []).append(x)
        for (y, m), xs in by_month.items():
            t = tindex(y, m)
            xs = np.array(xs, float)
            if t < n_t and np.isnan(temp[i, t]) and np.isfinite(xs).sum() >= MIN_PARTIAL_DAYS:
                temp[i, t] = np.nanmean(xs)
                partial[t] = np.isfinite(xs).sum() < len(xs)
    return Data(cells, temp, partial,
                _read_sstoi(RAW / "indices" / "sstoi.indices", n_t),
                _read_aao(RAW / "indices" / "aao.ascii", n_t))


# --------------------------------------------------------------------------- baseline

@dataclass
class Baseline:
    clim: np.ndarray    # (n_cells, 12)
    slope: np.ndarray   # (n_cells,) degC per year
    mid_year: float

    def at(self, t):
        """Expected temperature (clim + trend) for every cell at time index/indices t."""
        t = np.asarray(t)
        year = START_YEAR + t // 12 + (t % 12) / 12
        return self.clim[:, t % 12] + np.multiply.outer(self.slope, year - self.mid_year)


def fit_baseline(temp, cutoff, first_t=0):
    """Climatology and linear trend from months first_t..cutoff-1 only."""
    x = temp[:, first_t:cutoff]
    ts = np.arange(first_t, cutoff)
    clim = np.stack([np.nanmean(x[:, ts % 12 == m], axis=1) for m in range(12)], axis=1)
    anom = x - clim[:, ts % 12]
    years = START_YEAR + ts // 12 + (ts % 12) / 12
    ok = np.isfinite(anom)
    slope = np.zeros(len(temp))
    for i in range(len(temp)):
        yy, aa = years[ok[i]], anom[i, ok[i]]
        slope[i] = np.polyfit(yy, aa, 1)[0] if len(yy) > 24 else 0.0
    mid = np.nanmean(years)
    # clim is the mean over the fitting window; centring the trend on that window keeps the mean unchanged.
    return Baseline(clim, slope, mid)


def climatology(temp, first_year, last_year):
    a, b = tindex(first_year, 1), tindex(last_year, 12) + 1
    ts = np.arange(a, b)
    return np.stack([np.nanmean(temp[:, a:b][:, ts % 12 == m], axis=1) for m in range(12)], axis=1)


# --------------------------------------------------------------------------- features

FEATURES = ["lead", "tgt_sin", "tgt_cos", "iss_sin", "iss_cos", "lat", "lon", "elevation", "land_frac",
            "slope", "clim_tgt", "anom_l1", "anom_l2", "anom_l3", "anom_m12", "anom_m120", "local_l1", "local_m3",
            "wa_l1", "wa_m3", "nino_l1", "nino_d3", "sam_l1", "sam_m3"]


def anomalies(data, base):
    """Anomaly of every cell/month against the fold baseline (clim + trend)."""
    return data.temp - base.at(np.arange(data.n_t))


def _neighbour_matrix(cells, radius=2.0):
    lat, lon = cells.lat.values, cells.lon.values
    w = ((np.abs(lat[:, None] - lat[None]) <= radius) & (np.abs(lon[:, None] - lon[None]) <= radius)).astype(float)
    return w / w.sum(1, keepdims=True)


def build_rows(data, base, issues):
    """One row per (issue, lead, cell). Features use only months < issue; target is the anomaly at issue+lead-1."""
    A = anomalies(data, base)
    W = _neighbour_matrix(data.cells)
    wa = np.nanmean(A, axis=0)
    n = len(data.cells)
    frames = []
    for I in issues:
        if I < 13:
            continue
        lag = A[:, I - 3:I]
        local = W @ np.nan_to_num(lag)
        common = dict(
            iss_sin=np.sin(2 * np.pi * (I % 12) / 12), iss_cos=np.cos(2 * np.pi * (I % 12) / 12),
            lat=data.cells.lat.values, lon=data.cells.lon.values, elevation=data.cells.elevation.values,
            land_frac=data.cells.land_frac.values, slope=base.slope,
            anom_l1=lag[:, 2], anom_l2=lag[:, 1], anom_l3=lag[:, 0], anom_m12=np.nanmean(A[:, I - 12:I], axis=1),
            # recent-decade departure from the linear trend: warming has outpaced a 1981-onward line since ~2016
            anom_m120=np.nanmean(A[:, max(0, I - 120):I], axis=1),
            local_l1=local[:, 2], local_m3=local.mean(1), wa_l1=wa[I - 1], wa_m3=np.nanmean(wa[I - 3:I]),
            nino_l1=data.nino34[I - 1], nino_d3=data.nino34[I - 1] - data.nino34[I - 4],
            sam_l1=data.sam[I - 1], sam_m3=np.nanmean(data.sam[I - 3:I]),
        )
        for L in LEADS:
            t = I + L - 1
            if t >= data.n_t:
                continue
            frames.append(pd.DataFrame(dict(
                common, cell=data.cells.cell.values, issue=I, target_t=t, lead=L,
                tgt_sin=np.sin(2 * np.pi * (t % 12) / 12), tgt_cos=np.cos(2 * np.pi * (t % 12) / 12),
                clim_tgt=base.clim[:, t % 12], baseline=base.at(t), y=A[:, t], obs=data.temp[:, t],
            )))
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------- models

def fit_persistence(train):
    """Damped persistence: anomaly(lead) = a_lead * anom_l1, a_lead by least squares."""
    coef = {}
    for L, g in train.groupby("lead"):
        g = g.dropna(subset=["y", "anom_l1"])
        coef[L] = float((g.anom_l1 * g.y).sum() / (g.anom_l1 ** 2).sum())
    return coef


def predict_persistence(coef, rows):
    return rows.lead.map(coef).values * rows.anom_l1.fillna(0).values


def make_ridge():
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.compose import ColumnTransformer
    num = [f for f in FEATURES if f != "lead"]
    # Lead interacts with every predictor in a linear model, so fit one ridge per lead.
    return lambda: make_pipeline(ColumnTransformer([("num", StandardScaler(), num)]), RidgeCV(alphas=np.logspace(-2, 3, 12)))


def fit_ridge(train):
    factory = make_ridge()
    models = {}
    for L, g in train.groupby("lead"):
        g = g.dropna(subset=["y"])
        models[L] = factory().fit(g[FEATURES].fillna(0), g.y)
    return models


def predict_ridge(models, rows):
    out = np.zeros(len(rows))
    for L, idx in rows.groupby("lead").indices.items():
        out[idx] = models[L].predict(rows.iloc[idx][FEATURES].fillna(0))
    return out


LGB_PARAMS = dict(objective="regression", learning_rate=0.03, num_leaves=31, min_data_in_leaf=300,
                  feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0,
                  verbose=-1, seed=7, num_threads=0)


def fit_lgbm(train, valid=None, rounds=600):
    import lightgbm as lgb
    tr = train.dropna(subset=["y"])
    dtr = lgb.Dataset(tr[FEATURES], tr.y)
    if valid is None:
        return lgb.train(LGB_PARAMS, dtr, num_boost_round=rounds)
    va = valid.dropna(subset=["y"])
    return lgb.train(LGB_PARAMS, dtr, num_boost_round=1500, valid_sets=[lgb.Dataset(va[FEATURES], va.y)],
                     callbacks=[lgb.early_stopping(80, verbose=False)])


def prob_above(pred_temp, threshold, sigma):
    """P(observed monthly mean > threshold) under a Gaussian forecast error with spread sigma."""
    return norm.sf((threshold - pred_temp) / sigma)
