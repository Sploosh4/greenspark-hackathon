# Q3 seasonal temperature outlook: ML prototype

An experimental, statistically trained outlook of **monthly mean temperature** on the same 1° WA grid as the
Team Connect "WA community outlook" map, with a 20-year out-of-sample hindcast against simple baselines.
Findings, limits and recommendations are in [REPORT.md](REPORT.md).

This is a research model, not a Copernicus or BoM product. It forecasts monthly means and the chance of a
warmer-than-normal month. It does **not** forecast heatwave counts, dates or household exposure.

## Run

```sh
pip install numpy pandas scipy scikit-learn lightgbm matplotlib pytest
python fetch_data.py          # ~510 NASA POWER requests + NOAA indices, cached in data/raw
python run_backtest.py        # rolling-origin hindcast 2006-2025, ~6 min
                              # writes outputs/hindcast_predictions.csv.gz (26 MB, not committed);
                              # evaluate, run_forecast and export_map_layer need it
python evaluate.py            # skill tables and charts in outputs/
python run_forecast.py        # Oct and Nov 2026 issues: outputs/forecast_grid.{csv,json}, maps
python -m pytest -q test_seasonal.py
```

## Files

| File | Purpose |
|---|---|
| `fetch_data.py` | WA cell selection (Natural Earth outline) and cached downloads |
| `seasonal.py` | Data loading, fold-local climatology + trend, features, models |
| `run_backtest.py` | Train on years before Y, forecast every month of Y at leads 1-6, Y = 2006..2025 |
| `evaluate.py` | RMSE, MSE skill, anomaly correlation, Brier skill, reliability, bootstrap |
| `run_forecast.py` | Final fit through Sep 2026 and current outlook grids/maps |
| `test_seasonal.py` | Leakage and convention tests |

`outputs/forecast_grid.json` has one record per cell, issue and target month (`pred_temp`, `p10`, `p90`,
`normal_1991_2020`, `anom_vs_1991_2020`, `prob_above_1991_2020`) so it can be loaded as an alternative layer.

## Map layer

`python export_map_layer.py` packages the forecast for the web: `outputs/ml_outlook_layer.json` (141 KB, every
cell's six months per issue plus its hindcast skill per lead) and `outputs/wa_outline.geojson`.

**Demo:** `python -m http.server 8790 --bind 127.0.0.1` from this folder, then open
http://127.0.0.1:8790/map-demo/. It has no basemap dependency (WA outline only). The controls are:

- **Issue:** the forecast month.
- **Measure:** difference from the 1991–2020 average, chance of a warmer-than-average month, or temperature.
  Temperature uses the app's 14–36 °C scale.
- **Month strip:** arrow keys work.
- **Map / Table:** the table is the readable alternative to the map.
- **Cells:** hover for a tooltip, click for the detail panel. The URL keeps the state.

Cells where the hindcast showed little skill (MSE skill < 0.05) at the selected lead are drawn faded and flagged.

**Adding it to an existing MapLibre map** (for example, the WA community outlook screen):

```js
import { addMlOutlookLayer, MODES } from './ml-outlook-layer.mjs';

const data = await (await fetch('ml_outlook_layer.json')).json();
const ml = addMlOutlookLayer(map, data, {
  issue: '2026-11',          // data.issues[].key
  month: 0,                  // 0-5 = lead 1-6
  mode: 'anom',              // 'anom' | 'prob' | 'temp'
  beforeId: 'place-labels',  // optional: draw under labels
  onSelect: cell => renderAreaPanel(cell),   // cellSummary(): six months, range, normal, skill
  onHover: h => showTooltip(h),
});
// wire the app's own controls
monthStrip.onChange(i => ml.setMonth(i));
measureToggle.onChange(m => ml.setMode(m));
ml.select('-18.5_125.5');    // Fitzroy Crossing cell, same 1-degree convention as the C3S grid
```

Steps for the outlook app:
1. Copy `map-demo/ml-outlook-layer.mjs` and the two output files into the app's static assets.
2. Add a **source toggle** ("Copernicus C3S" / "ML outlook") beside the existing controls.
3. When ML is on, hide the C3S fill layer and call `addMlOutlookLayer`; when it is off, call `ml.remove()`.
4. Keep the app's legend, month strip and side panel, and feed them from `MODES` and `cellSummary`.

Both products use 1° cells with centres at x.5, so a selected cell carries across directly. Compare
**anomalies or probabilities** between products, not absolute °C; the reference datasets differ.

**Monthly refresh:**
1. `fetch_data.py` (delete `data/raw/power_daily_202610` and `data/raw/indices` first so they re-download)
2. `run_forecast.py`
3. `export_map_layer.py`
4. Copy the JSON to the app.

Re-run `run_backtest.py` and `evaluate.py` about once a year.

Tests: `node --test map-demo/test-ml-outlook-layer.mjs`.

## Sources

- NASA POWER (MERRA-2 reanalysis) T2M, monthly 1981-Sep 2026 and daily for Oct 2026. NASA Langley Research Center POWER Project.
- NOAA CPC Niño 3.4 (ERSSTv5) and Antarctic Oscillation (SAM) monthly indices.
- Natural Earth 1:50m admin-1 boundaries (public domain), used only to choose WA cells and draw outlines.
