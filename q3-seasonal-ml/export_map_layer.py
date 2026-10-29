"""Package the forecast for a web map: one compact JSON with every cell's six-month outlook per issue and
its hindcast skill per lead, plus a WA outline. Cell squares are built in the browser from lat/lon.

  outputs/ml_outlook_layer.json  - consumed by map-demo/ml-outlook-layer.mjs
  outputs/wa_outline.geojson     - simplified state outline for maps without a basemap
"""
import json

import numpy as np
import pandas as pd

import seasonal as S

OUT = S.ROOT / "outputs"


def cell_skill(h):
    """MSE skill of the ensemble vs climatology, per cell and lead, over the 2006-2025 hindcast."""
    h = h.assign(e_ens=(h.pred_ens - h.obs) ** 2, e_clim=(h.pred_clim - h.obs) ** 2)
    g = h.groupby(["cell", "lead"])[["e_ens", "e_clim"]].mean()
    return (1 - g.e_ens / g.e_clim).unstack("lead")


def r(x, n=2):
    return [round(float(v), n) for v in x]


def main():
    fc = pd.read_csv(OUT / "forecast_grid.csv")
    meta = json.loads((OUT / "forecast_grid.json").read_text())["meta"]
    skill = cell_skill(pd.read_csv(OUT / "hindcast_predictions.csv.gz"))
    cells = pd.DataFrame(json.loads((S.ROOT / "data" / "cells.json").read_text())).set_index("cell")

    issues = []
    for label, g in fc.groupby("issue_label", sort=False):
        months = sorted(g.target_month.unique())
        issues.append(dict(key=months[0], label=label, months=months, uses_partial_month=bool(g.uses_partial_month.iloc[0])))

    out_cells = []
    for cid, c in cells.iterrows():
        rec = dict(id=cid, lat=c.lat, lon=c.lon, land=c.land_frac, skill=r(skill.loc[cid].values), f={})
        for iss in issues:
            g = fc[(fc.cell == cid) & (fc.issue_label == iss["label"])].sort_values("lead")
            rec["f"][iss["key"]] = dict(t=r(g.pred_temp, 1), a=r(g.anom_vs_1991_2020), p=r(g.prob_above_1991_2020),
                                         lo=r(g.p10, 1), hi=r(g.p90, 1), n=r(g.normal_1991_2020, 1))
        out_cells.append(rec)

    localities = [dict(name=n, lat=la, lon=lo, cell=S.cell_id(la, lo)) for n, (la, lo) in S.LOCALITIES.items()]
    layer = dict(meta=dict(meta, skill="MSE skill vs climatology per lead, ensemble, hindcast 2006-2025",
                           generated_from="run_forecast.py + run_backtest.py"),
                 issues=issues, localities=localities, cells=out_cells)
    (OUT / "ml_outlook_layer.json").write_text(json.dumps(layer, separators=(",", ":")))

    gj = json.loads((S.RAW / "naturalearth" / "ne_50m_admin_1.geojson").read_text(encoding="utf-8"))
    wa = next(f for f in gj["features"] if f["properties"].get("name") == "Western Australia")
    geom = wa["geometry"]
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    simple = [[[[round(x, 3), round(y, 3)] for x, y in ring[::2] + [ring[0]]] for ring in p[:1]] for p in polys if len(p[0]) > 20]
    (OUT / "wa_outline.geojson").write_text(json.dumps(dict(type="FeatureCollection", features=[dict(
        type="Feature", properties=dict(name="Western Australia", source="Natural Earth 1:50m admin-1"),
        geometry=dict(type="MultiPolygon", coordinates=simple))]), separators=(",", ":")))
    print(f"{len(out_cells)} cells, {len(issues)} issues, layer {(OUT / 'ml_outlook_layer.json').stat().st_size // 1024} KB")
    print("cells with lead-1 skill < 0.05:", int((skill[1] < 0.05).sum()), " lead-3:", int((skill[3] < 0.05).sum()))


if __name__ == "__main__":
    main()
