"""Fit on every complete month and issue the current outlooks.

  October 2026 issue  - data through Sep 2026 (all complete); covers Oct 2026-Mar 2027, the same
                        months as the Copernicus panel in the Team Connect map.
  November 2026 issue - additionally uses 1-21 October 2026 (partial month, flagged); covers Nov 2026-Apr 2027.

Model: mean of ridge and LightGBM (the hindcast winner). Forecast spread per lead is its out-of-sample error from the 2006-2025 hindcast.
"""
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

import seasonal as S

OUT = S.ROOT / "outputs"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TEMP_CMAP = LinearSegmentedColormap.from_list("temp", ["#fdf1e3", "#f7c08a", "#ec835a", "#c8452c", "#7d1d14"])
PROB_CMAP = LinearSegmentedColormap.from_list("prob", ["#184f95", "#86b6ef", "#f0efec", "#ef9a86", "#a8231f"])
INK, INK2 = "#0b0b0b", "#52514e"


def wa_outline():
    gj = json.loads((S.RAW / "naturalearth" / "ne_50m_admin_1.geojson").read_text(encoding="utf-8"))
    f = next(f for f in gj["features"] if f["properties"].get("name") == "Western Australia")
    polys = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
    return [np.asarray(p[0]) for p in polys if len(p[0]) > 30]


def grid(df, col):
    lats = np.arange(-35.5, -13.0, 1.0)
    lons = np.arange(112.5, 129.0, 1.0)
    g = np.full((len(lats), len(lons)), np.nan)
    for r in df.itertuples():
        g[int(round(r.lat + 35.5)), int(round(r.lon - 112.5))] = getattr(r, col)
    return lons, lats, g


def plot_maps(fc, col, cmap, norm, title, label, path):
    outline = wa_outline()
    targets = sorted(fc.target_t.unique())
    fig, axes = plt.subplots(1, len(targets), figsize=(3.0 * len(targets), 4.3))
    for ax, t in zip(axes, targets):
        d = fc[fc.target_t == t]
        lons, lats, g = grid(d, col)
        im = ax.pcolormesh(np.append(lons - .5, lons[-1] + .5), np.append(lats - .5, lats[-1] + .5), g,
                           cmap=cmap, norm=norm, edgecolors="white", linewidth=0.3)
        for p in outline:
            ax.plot(p[:, 0], p[:, 1], color=INK2, lw=0.6)
        for name, (la, lo) in S.LOCALITIES.items():
            ax.plot(lo, la, "o", ms=3, mfc="white", mec=INK, mew=0.7)
        y, m = S.tdate(int(t))
        ax.set_title(f"{MONTHS[m - 1]} {y}", color=INK, fontsize=10)
        ax.set_xlim(112, 129.2)
        ax.set_ylim(-36, -13)
        ax.set_aspect(1 / np.cos(np.deg2rad(24)))
        ax.axis("off")
    cb = fig.colorbar(im, ax=axes, orientation="horizontal", fraction=0.05, pad=0.04, aspect=50)
    cb.set_label(label, color=INK2, fontsize=9)
    fig.suptitle(title, color=INK, fontsize=11, x=0.01, ha="left")
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main():
    data = S.load(2027, 6)
    last_full = int(np.where(np.isfinite(data.temp).all(0) & ~data.partial)[0].max())
    cutoff = last_full + 1
    base = S.fit_baseline(data.temp, cutoff)
    # CPC publishes Nino 3.4 / SAM a few days after month end. For the issue that uses the partial month,
    # carry the previous month forward rather than let a missing value read as a neutral climate state.
    carried = []
    for name, arr in (("nino34", data.nino34), ("sam", data.sam)):
        if np.isnan(arr[cutoff]):
            arr[cutoff] = arr[cutoff - 1]
            carried.append(f"{name} {S.tdate(cutoff)[0]}-{S.tdate(cutoff)[1]:02d} = {S.tdate(cutoff - 1)[1]:02d} value")
    hind = pd.read_csv(OUT / "hindcast_predictions.csv.gz")
    sigma = (hind.pred_ens - hind.obs).groupby(hind.lead).std()
    # rolling bias correction (see evaluate.rolling_bias_correction): mean error of the last 5 hindcast years
    recent = hind[(hind.test_year > hind.test_year.max() - 5)]
    bias = (recent.obs - recent.pred_ens).groupby(recent.lead).mean()
    # isotonic map from forecast probability to observed frequency, fitted on the bias-corrected 2011-2025 hindcast
    from sklearn.isotonic import IsotonicRegression
    from evaluate import rolling_bias_correction
    bc = rolling_bias_correction(hind)
    calib = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(
        S.prob_above(bc.pred_ens_bc, bc.clim_tgt, bc.sigma_ens), (bc.obs > bc.clim_tgt).astype(float))
    # boosting rounds = median early-stopping point across the hindcast folds
    log = (S.ROOT / "backtest.log").read_text()
    rounds = int(np.median([int(w.split("=")[1]) for w in log.split() if w.startswith("rounds=")]))

    rows = S.build_rows(data, base, range(13, cutoff + 2))
    train = rows[rows.target_t < cutoff]
    model = S.fit_lgbm(train, rounds=rounds)
    ridge = S.fit_ridge(train)
    pers = S.fit_persistence(train)

    normal = S.climatology(data.temp, 1991, 2020)
    cells = data.cells.set_index("cell")
    out = []
    for issue in (cutoff, cutoff + 1):
        fc = rows[rows.issue == issue].copy()
        # ridge fills NaN with 0, which for an index means "neutral"; refuse to forecast on missing predictors
        missing = fc[S.FEATURES].columns[fc[S.FEATURES].isna().any()].tolist()
        assert not missing, f"missing predictors for issue {S.tdate(issue)}: {missing}"
        y, m = S.tdate(issue)
        fc["issue_label"] = f"{MONTHS[m - 1]} {y}"
        fc["uses_partial_month"] = bool(data.partial[issue - 1])
        fc["pred_temp"] = fc.baseline + (model.predict(fc[S.FEATURES]) + S.predict_ridge(ridge, fc)) / 2 \
            + fc.lead.map(bias)
        fc["pred_persistence"] = fc.baseline + S.predict_persistence(pers, fc)
        fc["sigma"] = fc.lead.map(sigma)
        fc["p10"] = fc.pred_temp - 1.2816 * fc.sigma
        fc["p90"] = fc.pred_temp + 1.2816 * fc.sigma
        idx = cells.index.get_indexer(fc.cell)
        fc["normal_1991_2020"] = normal[idx, fc.target_t % 12]
        fc["anom_vs_1991_2020"] = fc.pred_temp - fc.normal_1991_2020
        fc["prob_above_1991_2020_raw"] = S.prob_above(fc.pred_temp, fc.normal_1991_2020, fc.sigma)
        fc["prob_above_1991_2020"] = calib.predict(fc.prob_above_1991_2020_raw)
        fc["prob_above_trend_normal"] = calib.predict(S.prob_above(fc.pred_temp, fc.baseline, fc.sigma))
        fc["target_month"] = [f"{S.tdate(int(t))[0]}-{S.tdate(int(t))[1]:02d}" for t in fc.target_t]
        out.append(fc)
        tag = f"{y}{m:02d}"
        plot_maps(fc, "pred_temp", TEMP_CMAP, plt.Normalize(14, 36),
                  f"ML outlook, monthly mean temperature (°C), {fc.issue_label.iloc[0]} issue",
                  "Predicted monthly mean 2 m temperature, °C (same 14-36 scale as the app)", OUT / f"map_temp_{tag}.png")
        plot_maps(fc, "anom_vs_1991_2020", PROB_CMAP, TwoSlopeNorm(0, -2.5, 2.5),
                  f"Predicted departure from the 1991-2020 monthly average (°C), {fc.issue_label.iloc[0]} issue",
                  "°C warmer (red) or cooler (blue) than the cell's 1991-2020 average for that month", OUT / f"map_anom_{tag}.png")
        plot_maps(fc, "prob_above_1991_2020", PROB_CMAP, TwoSlopeNorm(0.5, 0, 1),
                  f"Chance the month is warmer than its 1991-2020 average, {fc.issue_label.iloc[0]} issue",
                  "Probability (0.5 = no shift from normal)", OUT / f"map_prob_{tag}.png")

    fc = pd.concat(out)
    fc = fc.merge(cells[["lat", "lon"]], left_on="cell", right_index=True, suffixes=("", "_c"))
    keep = ["issue_label", "uses_partial_month", "cell", "lat", "lon", "lead", "target_month", "pred_temp", "p10", "p90",
            "sigma", "normal_1991_2020", "anom_vs_1991_2020", "prob_above_1991_2020", "prob_above_1991_2020_raw",
            "prob_above_trend_normal",
            "baseline", "pred_persistence"]
    fc[keep].round(3).to_csv(OUT / "forecast_grid.csv", index=False)
    meta = dict(model="Mean of ridge and LightGBM on anomalies from per-cell climatology + linear trend", source="NASA POWER MERRA-2 T2M monthly",
                training_through=f"{S.tdate(last_full)[0]}-{S.tdate(last_full)[1]:02d}", rounds=rounds,
                sigma_by_lead=sigma.round(3).to_dict(), bias_correction_by_lead=bias.round(3).to_dict(),
                indices_carried_forward=carried, partial_month="Oct 2026 from daily T2M 1-21 Oct", resolution="1 degree cells, centres at x.5",
                caveat="Experimental statistical outlook; not a Copernicus or BoM product. Monthly means only, not heatwave counts.")
    (OUT / "forecast_grid.json").write_text(json.dumps(dict(meta=meta, cells=fc[keep].round(3).to_dict("records"))))

    loc = {S.cell_id(*ll): n for n, ll in S.LOCALITIES.items()}
    lt = fc[fc.cell.isin(loc)].assign(locality=lambda d: d.cell.map(loc))
    pd.set_option("display.width", 220)
    for issue, g in lt.groupby("issue_label", sort=False):
        print(f"\n== {issue} issue: predicted mean °C [anomaly vs 1991-2020] P(above)")
        tab = g.assign(v=lambda d: d.pred_temp.round(1).astype(str) + " [" + d.anom_vs_1991_2020.round(1).map("{:+.1f}".format)
                       + "] " + (d.prob_above_1991_2020 * 100).round(0).astype(int).astype(str) + "%") \
            .pivot(index="locality", columns="target_month", values="v")
        print(tab)
    wa = fc.groupby(["issue_label", "target_month"]).agg(anom=("anom_vs_1991_2020", "mean"), p=("prob_above_1991_2020", "mean"),
                                                          pmin=("prob_above_1991_2020", "min"), pmax=("prob_above_1991_2020", "max"))
    print(wa.round(2))


if __name__ == "__main__":
    main()
