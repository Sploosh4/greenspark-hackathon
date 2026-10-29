"""Score the hindcast: skill by model and lead, by region and season, at named localities, plus
reliability of the 'warmer than normal' probability and a year-block bootstrap of the LightGBM gain."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import seasonal as S

OUT = S.ROOT / "outputs"
MODELS = ["clim", "trend", "persistence", "ridge", "lgbm", "ens"]
COLORS = {"trend": "#2a78d6", "persistence": "#eb6834", "ridge": "#1baf7a", "lgbm": "#eda100", "ens": "#e87ba4"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM", 6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}


def scores(g):
    out = {}
    event = (g.obs > g.clim_tgt).astype(float)
    obs_a = g.obs - g.clim_tgt
    mse_clim = ((g.pred_clim - g.obs) ** 2).mean()
    for m in MODELS:
        err = g[f"pred_{m}"] - g.obs
        out[f"rmse_{m}"] = np.sqrt((err ** 2).mean())
        out[f"msss_{m}"] = 1 - (err ** 2).mean() / mse_clim
        if m != "clim":
            out[f"acc_{m}"] = np.corrcoef(g[f"pred_{m}"] - g.clim_tgt, obs_a)[0, 1]
            p = S.prob_above(g[f"pred_{m}"], g.clim_tgt, g[f"sigma_{m}"])
            out[f"bss_{m}"] = 1 - ((p - event) ** 2).mean() / ((0.5 - event) ** 2).mean()
    out["n"] = len(g)
    out["freq_above"] = event.mean()
    return pd.Series(out)


def bootstrap_gain(h, a="ens", b="persistence", n=2000, seed=0):
    """Year-block bootstrap of MSE(b) - MSE(a); years are resampled whole to respect spatial correlation."""
    per_year = h.assign(da=(h[f"pred_{a}"] - h.obs) ** 2, db=(h[f"pred_{b}"] - h.obs) ** 2) \
        .groupby(["test_year", "lead"])[["da", "db"]].mean().reset_index()
    rng = np.random.default_rng(seed)
    years = per_year.test_year.unique()
    rows = []
    for L, g in per_year.groupby("lead"):
        g = g.set_index("test_year")
        diffs = [(g.loc[s, "db"] - g.loc[s, "da"]).mean() for s in (rng.choice(years, len(years)) for _ in range(n))]
        rows.append(dict(lead=L, mse_gain=(g.db - g.da).mean(), lo=np.percentile(diffs, 5), hi=np.percentile(diffs, 95),
                         years_better=int((g.da < g.db).sum()), years=len(g)))
    return pd.DataFrame(rows)


def style(ax):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def plot_skill(by_lead):
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    fig.suptitle("20-year hindcast skill (2006-2025, 255 WA cells); above 0 = better than climatology", color=INK, fontsize=11, x=0.01, ha="left")
    for ax, (key, title) in zip(axes, [("msss", "MSE skill vs climatology"), ("acc", "Anomaly correlation"),
                                       ("bss", "Brier skill, P(warmer than normal)")]):
        for m, c in COLORS.items():
            ax.plot(by_lead.index, by_lead[f"{key}_{m}"], color=c, lw=2, marker="o", ms=5, label=m)
        ax.axhline(0, color=INK2, lw=1)
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_xlabel("Lead month (1 = issue month)", color=INK2, fontsize=9)
        style(ax)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(OUT / "skill_by_lead.png", dpi=150)


def plot_reliability(h):
    p = S.prob_above(h.pred_ens, h.clim_tgt, h.sigma_ens)
    e = (h.obs > h.clim_tgt).astype(float)
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(p, bins) - 1, 0, 9)
    t = pd.DataFrame(dict(p=p, e=e, b=idx)).groupby("b").agg(p=("p", "mean"), e=("e", "mean"), n=("e", "size"))
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(4.6, 5.2), gridspec_kw=dict(height_ratios=[3, 1]), sharex=True)
    ax.plot([0, 1], [0, 1], color=INK2, lw=1, ls="--")
    ax.plot(t.p, t.e, color=COLORS["ens"], lw=2, marker="o", ms=6)
    ax.set_ylabel("Observed frequency", color=INK2, fontsize=9)
    ax.set_title("Reliability, ensemble P(warmer than normal)", color=INK, fontsize=10, loc="left")
    ax2.bar(t.p, t.n, width=0.07, color=COLORS["ens"])
    ax2.set_xlabel("Forecast probability", color=INK2, fontsize=9)
    ax2.set_ylabel("Forecasts", color=INK2, fontsize=9)
    for a in (ax, ax2):
        style(a)
    fig.tight_layout()
    fig.savefig(OUT / "reliability_ens.png", dpi=150)
    return t


def main():
    h = pd.read_csv(OUT / "hindcast_predictions.csv.gz")
    cells = pd.DataFrame(__import__("json").loads((S.ROOT / "data" / "cells.json").read_text()))
    h = h.merge(cells[["cell", "lat"]], on="cell")
    h["month"] = h.target_t % 12 + 1
    h["season"] = h.month.map(SEASON)
    h["region"] = np.where(h.lat > -26, "North (Pilbara/Kimberley)", "South")

    by_lead = h.groupby("lead").apply(scores)
    by_lead.round(3).to_csv(OUT / "skill_by_lead.csv")
    h.groupby(["region", "lead"]).apply(scores).round(3).to_csv(OUT / "skill_by_region_lead.csv")
    h.groupby(["season", "lead"]).apply(scores).round(3).to_csv(OUT / "skill_by_season_lead.csv")
    loc_cells = {S.cell_id(*ll): name for name, ll in S.LOCALITIES.items()}
    loc = h[h.cell.isin(loc_cells)].assign(locality=lambda d: d.cell.map(loc_cells))
    loc.groupby(["locality"]).apply(scores).round(3).to_csv(OUT / "skill_by_locality.csv")
    boot = bootstrap_gain(h)
    boot.round(4).to_csv(OUT / "bootstrap_ens_vs_persistence.csv", index=False)
    boot_t = bootstrap_gain(h, b="trend")
    boot_t.round(4).to_csv(OUT / "bootstrap_ens_vs_trend.csv", index=False)
    boot_l = bootstrap_gain(h, b="lgbm")
    boot_l.round(4).to_csv(OUT / "bootstrap_ens_vs_lgbm.csv", index=False)
    plot_skill(by_lead)
    rel = plot_reliability(h)
    rel.round(3).to_csv(OUT / "reliability_ens.csv")

    pd.set_option("display.width", 200)
    cols = [c for c in by_lead.columns if c.split("_")[0] in ("rmse", "msss", "acc", "bss")]
    print(by_lead[cols].round(3).T)
    print(h.groupby(["region", "lead"]).apply(scores)[["msss_trend", "msss_persistence", "msss_ridge", "msss_lgbm", "msss_ens", "bss_ens"]].round(3))
    print(h.groupby(["season"]).apply(scores)[["msss_trend", "msss_persistence", "msss_ens", "acc_ens", "bss_ens"]].round(3))
    print(loc.groupby("locality").apply(scores)[["rmse_clim", "rmse_trend", "rmse_persistence", "rmse_ens", "msss_ens", "bss_ens"]].round(3))
    print("ens vs persistence\n", boot.round(4))
    print("ens vs trend\n", boot_t.round(4))
    print("ens vs lgbm\n", boot_l.round(4))
    print(rel.round(3))

    bc = rolling_bias_correction(h)
    bc_skill = bc.groupby("lead").apply(lambda g: pd.Series({
        "msss_ens": 1 - ((g.pred_ens - g.obs) ** 2).mean() / ((g.pred_clim - g.obs) ** 2).mean(),
        "msss_ens_bc": 1 - ((g.pred_ens_bc - g.obs) ** 2).mean() / ((g.pred_clim - g.obs) ** 2).mean()}))
    bc_skill.round(3).to_csv(OUT / "skill_bias_corrected_2011_2025.csv")
    recent = bc[bc.test_year >= 2016]
    print("rolling bias correction, 2011-2025\n", bc_skill.round(3))
    print("mean error 2016-25: ens %.3f, ens_bc %.3f" % ((recent.obs - recent.pred_ens).mean(), (recent.obs - recent.pred_ens_bc).mean()))


def rolling_bias_correction(h, years=5):
    """Add the per-lead mean error of the previous `years` hindcast years, using only targets already
    observed before 1 Jan of the test year. Scored on 2011-2025 so every year has a full 5-year history."""
    out = []
    for Y in range(h.test_year.min() + years, h.test_year.max() + 1):
        past = h[(h.test_year >= Y - years) & (h.test_year < Y) & (h.target_t < S.tindex(Y, 1))]
        bias = (past.obs - past.pred_ens).groupby(past.lead).mean()
        t = h[h.test_year == Y].copy()
        t["pred_ens_bc"] = t.pred_ens + t.lead.map(bias)
        out.append(t)
    return pd.concat(out)


if __name__ == "__main__":
    main()
