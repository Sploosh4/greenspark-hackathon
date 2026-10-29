"""Rolling-origin hindcast: for each test year Y, fit everything on months before 1 Jan Y, then
issue 12 forecasts (Jan..Dec Y, leads 1-6) and score them against what was later observed.

Models compared, all predicting monthly mean temperature per cell:
  clim         cell x calendar-month mean of the training years
  trend        clim + per-cell linear warming trend
  persistence  trend + damped persistence of last month's anomaly (one coefficient per lead)
  ridge        trend + ridge regression on the full feature set (one model per lead)
  lgbm         trend + LightGBM on the full feature set
  ens          mean of ridge and lgbm

Spread (sigma) for each model's probability forecasts comes from an inner validation on the five
years before Y, never from the test year.
"""
import sys
import time

import numpy as np
import pandas as pd

import seasonal as S

TEST_YEARS = range(2006, 2026)
INNER_YEARS = 5
OUT = S.ROOT / "outputs"


def run_fold(data, Y, last_issue):
    cutoff = S.tindex(Y, 1)
    base = S.fit_baseline(data.temp, cutoff)
    rows = S.build_rows(data, base, range(13, min(cutoff + 12, last_issue + 1)))
    train = rows[rows.target_t < cutoff]
    test = rows[(rows.issue >= cutoff) & (rows.issue < cutoff + 12)].dropna(subset=["obs"]).copy()

    v0 = cutoff - 12 * INNER_YEARS
    itrain = train[train.target_t < v0]
    ivalid = train[train.issue >= v0]

    # inner fits: sigma per lead per model and the LightGBM round count
    pers_i, ridge_i = S.fit_persistence(itrain), S.fit_ridge(itrain)
    lgb_i = S.fit_lgbm(itrain, ivalid)
    inner_pred = {
        "trend": np.zeros(len(ivalid)),
        "persistence": S.predict_persistence(pers_i, ivalid),
        "ridge": S.predict_ridge(ridge_i, ivalid),
        "lgbm": lgb_i.predict(ivalid[S.FEATURES]),
    }
    inner_pred["ens"] = (inner_pred["ridge"] + inner_pred["lgbm"]) / 2
    sigma = {m: pd.Series(ivalid.y.values - p).groupby(ivalid.lead.values).std() for m, p in inner_pred.items()}
    clim_sigma = (ivalid.obs - ivalid.clim_tgt).groupby(ivalid.lead).std()

    pers, ridge = S.fit_persistence(train), S.fit_ridge(train)
    lgb = S.fit_lgbm(train, rounds=max(lgb_i.best_iteration, 50))
    yhat = {
        "trend": np.zeros(len(test)),
        "persistence": S.predict_persistence(pers, test),
        "ridge": S.predict_ridge(ridge, test),
        "lgbm": lgb.predict(test[S.FEATURES]),
    }
    yhat["ens"] = (yhat["ridge"] + yhat["lgbm"]) / 2
    test["test_year"] = Y
    test["pred_clim"] = test.clim_tgt
    test["sigma_clim"] = test.lead.map(clim_sigma)
    for m, p in yhat.items():
        test[f"pred_{m}"] = test.baseline + p
        test[f"sigma_{m}"] = test.lead.map(sigma[m])
    imp = pd.Series(lgb.feature_importance("gain"), index=S.FEATURES, name=Y)
    return test, imp, lgb_i.best_iteration


def main():
    data = S.load()
    last_full = int(np.where(np.isfinite(data.temp).all(0) & ~data.partial)[0].max())
    print("last complete month:", S.tdate(last_full))
    OUT.mkdir(exist_ok=True)
    tests, imps = [], []
    years = TEST_YEARS if len(sys.argv) < 2 else [int(a) for a in sys.argv[1:]]
    for Y in years:
        t0 = time.time()
        # targets after the last complete month are dropped; partial months never enter scoring
        test, imp, it = run_fold(data, Y, last_full)
        test = test[test.target_t <= last_full]
        tests.append(test)
        imps.append(imp)
        rmse = {m: np.sqrt(((test[f"pred_{m}"] - test.obs) ** 2).mean()) for m in ["clim", "trend", "persistence", "ridge", "lgbm", "ens"]}
        print(Y, f"{time.time() - t0:.0f}s rounds={it}", " ".join(f"{k}={v:.3f}" for k, v in rmse.items()), flush=True)
    keep = ["cell", "issue", "target_t", "lead", "test_year", "obs", "clim_tgt", "baseline"] + \
           [c for c in tests[0].columns if c.startswith(("pred_", "sigma_"))]
    pd.concat(tests)[keep].to_csv(OUT / "hindcast_predictions.csv.gz", index=False)
    pd.concat(imps, axis=1).to_csv(OUT / "lgbm_feature_importance.csv")


if __name__ == "__main__":
    main()
