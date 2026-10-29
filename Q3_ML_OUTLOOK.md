# Q3 ML temperature outlook: run, test and method guide

Branch `namash_q3` · 29 October 2026 · status: **experimental, for team review**

This guide covers the seasonal temperature outlook built for the **Long-term Natural Disaster Planner (Q3)**:
how to run it on localhost, how to test it, the tech stack, and which ML algorithm is used, why and how.

The outlook forecasts **monthly mean temperature** for 255 one-degree WA cells, one to six months ahead, plus
the chance that each month is warmer than its 1991–2020 average. It does **not** forecast heatwave counts, dates
or customer-level outcomes. It is not a Copernicus or Bureau of Meteorology product.

Full results and limits: [q3-seasonal-ml/REPORT.md](q3-seasonal-ml/REPORT.md).

---

## 1. What is in this branch

| Path | What it is |
|---|---|
| `q3-seasonal-ml/` | The ML pipeline: data download, training, 20-year backtest, forecast, map export, report |
| `q3-seasonal-ml/map-demo/` | Standalone outlook map (no MapTiler key needed) |
| `teamconnect/ml-outlook-panel.mjs` | "WA temperature outlook" panel in the demo's Community planning screen |
| `teamconnect/ml-outlook-layer.mjs` | Reusable MapLibre layer (1° cells, colour scales, cell summaries) |
| `teamconnect/ml-outlook/` | The exported forecast, WA outline and `provenance.json` with SHA-256 hashes |
| `scripts/prepare-ml-outlook.py` | Copies a new forecast export into the demo and rewrites the provenance hashes |
| `test-ml-outlook-layer.mjs` | Tests for the layer and the shipped data |

---

## 2. Run on localhost

### Prerequisites
- **Python 3.11+** (3.11.9 was used)
- **Node.js 18+**, for the tests only
- A **MapTiler API key**, only for the street basemap in the postcode "Area view" map. The ML outlook map works without it.

### A. Team Connect demo, with the ML panel

1. **Optional: set up the MapTiler key.** Create `~/Projects/team-connect/.env.local` (on Windows,
   `C:\Users\<you>\Projects\team-connect\.env.local`) containing:
   ```
   MAPTILER_API_KEY=your_key_here
   ```
   - Never commit this file. `.gitignore` already excludes `.env*`.
   - To keep the file elsewhere, add `--maptiler-env path\to\.env.local` when starting the server.
2. **Start the server** from the repository root (`python3` on macOS/Linux, `python` on Windows):
   ```bash
   python serve-demo.py --port 8787
   ```
3. **Open http://127.0.0.1:8787/** and use `127.0.0.1`, not `localhost`. MapTiler keys are usually restricted to
   allowed origins: the current key accepts `127.0.0.1` and rejects `localhost` with
   "Key usage restricted". To use `localhost` as well, add it to the key's allowed origins in MapTiler.
4. **Find the panel:** go to **Community planning**, then either scroll below the Area view or choose
   **View → Temperature outlook (ML)**.

What you should see:
- **Area view:** MapTiler streets with the community's ABS postcode boundary. Without a key it shows
  "Map could not load"; nothing else is affected.
- **WA temperature outlook:**
  - a map of WA 1° cells coloured by the ML forecast
  - Forecast issue picker, measure buttons (Difference / Chance warmer / Temperature) and a month strip
  - the selected community's six-month table
  - click any cell to inspect it, then **← Back to ⟨community⟩**
  - faded cells: little skill in past forecasts at that lead time

Stop the server with Ctrl+C. To check the key without opening the app, request
http://127.0.0.1:8787/map-health.json: it reports `configured` and request counts, never the key.

### B. Standalone outlook map (no key, no demo data)

```bash
cd q3-seasonal-ml
python -m http.server 8790 --bind 127.0.0.1
```

Open **http://127.0.0.1:8790/map-demo/**. It has the same controls, plus a **Table** view and URL-shareable state.

### C. Re-run the ML pipeline

```bash
cd q3-seasonal-ml
pip install numpy pandas scipy scikit-learn lightgbm matplotlib pytest
python fetch_data.py        # about 510 NASA POWER requests + NOAA indices, cached in data/raw (about 5 min)
python run_backtest.py      # 20-year rolling hindcast (about 6 min); writes outputs/hindcast_predictions.csv.gz
python evaluate.py          # skill tables and charts in outputs/
python run_forecast.py      # latest issues: outputs/forecast_grid.{csv,json} and maps
python export_map_layer.py  # outputs/ml_outlook_layer.json for the web map
cd ..
python scripts/prepare-ml-outlook.py q3-seasonal-ml/outputs   # copy into the demo + refresh provenance hashes
```

Notes:
- `data/raw/` and `outputs/hindcast_predictions.csv.gz` (26 MB) are not committed. Run `fetch_data.py` and
  `run_backtest.py` once after cloning.
- **Monthly refresh,** after NOAA CPC and NASA POWER publish the previous month (around the 5th–10th):
  1. Delete `data/raw/power_daily_202610` and `data/raw/indices`.
  2. Run `fetch_data.py`, then `run_forecast.py`, then `export_map_layer.py`, then `prepare-ml-outlook.py`.
  3. Re-run `run_backtest.py` and `evaluate.py` about once a year.

---

## 3. Tests

| Command (from repository root unless noted) | What it checks | Result on this branch |
|---|---|---|
| `node --test test-*.mjs` | All demo logic, plus `test-ml-outlook-layer.mjs`: every community maps to a forecast cell; 1° geometry and values match the export; range, normal, anomaly and low-skill flags are consistent; fixed colour scales; provenance hashes match the shipped files | **88 / 88 pass** |
| `python test-map-proxy.py` | MapTiler proxy: allowlist, key redaction, URL rewriting | OK |
| `python test-poa2021-boundaries.py` | ABS postcode boundary import | OK |
| `node --test q3-seasonal-ml/map-demo/test-ml-outlook-layer.mjs` | Standalone map layer against the exported data | **4 / 4 pass** |
| `cd q3-seasonal-ml && python -m pytest -q test_seasonal.py` (after `fetch_data.py`) | **Leakage tests:** the baseline ignores data after the cutoff; changing any month at or after an issue leaves its features unchanged; lead 1 is the issue month; probability maths; every hindcast row was issued in its own test year | **7 / 7 pass** |

**Browser checks,** done in Chromium on Windows:
- initial load, every control, real cell clicks and the back button
- community switching, reload and URL restore
- leaving and returning to the screen, with old maps cleaned up
- both maps rendering with the key at `127.0.0.1`

Not yet tested: mobile, Firefox/Safari, and a Vercel deployment. See [VERIFICATION.md](VERIFICATION.md).

---

## 4. Tech stack

| Layer | Technology |
|---|---|
| ML and data | Python 3.11 · NumPy · pandas · SciPy · **scikit-learn** (`RidgeCV`, `IsotonicRegression`) · **LightGBM 4.6** · Matplotlib · pytest |
| Front end | Plain ES modules and HTML/CSS, **no build step** · **MapLibre GL JS 5.24.0** (vendored, BSD-3) |
| Local server | Python `http.server` (`serve-demo.py`): serves only allowlisted files, with a MapTiler proxy that keeps the key server-side |
| Hosting option | Vercel (`vercel.json`, serverless MapTiler proxy in `api/maptiler.mjs`, key in the `MAPTILER_API_KEY` environment variable) |
| Tests | Node built-in test runner (`node --test`) · Python `unittest` / `pytest` |
| Data sources | **NASA POWER** (MERRA-2 reanalysis) monthly and daily 2 m temperature · **NOAA CPC** Niño 3.4 (ERSSTv5) and SAM indices · **Natural Earth** 1:50m WA outline · ABS POA 2021 boundaries · MapTiler Streets basemap |

No paid services or accounts are needed for the ML part. Only the street basemap needs a MapTiler key.

---

## 5. The ML algorithm: what, why and how

### What it predicts
For every 1° cell and forecast issue month **I**, it predicts the monthly mean 2 m temperature for months
**I … I+5**. This is the same lead convention as Copernicus C3S: an October issue covers October to March.

Three outputs per cell and month:
- **Predicted temperature** with an **80% range**
- **Difference from the 1991–2020 average**
- **Calibrated probability that the month will be warmer than its 1991–2020 average**

### The model: an ensemble of two
**Final forecast = baseline + average(ridge prediction, LightGBM prediction) + bias correction**

1. **Baseline:** for each cell, its climatology for the calendar month plus its own linear warming trend
   since 1981 (median +0.16 °C per decade). The models predict the **anomaly** from this baseline, not the raw
   temperature, so they learn the departures rather than re-learning the seasons.
2. **Ridge regression** (scikit-learn `RidgeCV`, one model per lead month): a regularised linear model. It is
   stable and robust when the signal is weak.
3. **LightGBM** (gradient-boosted decision trees): learns non-linear interactions. For example, El Niño's effect
   on WA depends on the season and the region. It uses early stopping, so it stops adding trees once a validation
   period stops improving.
4. **Rolling bias correction:** adds the average forecast error of the previous five years, per lead time.
   Warming has recently outpaced the long-term linear trend.
5. **Probability calibration:** forecast errors are treated as a bell curve, with the spread measured from
   20 years of out-of-sample errors. The resulting probabilities are then calibrated with
   `IsotonicRegression`, so "80%" really means about 80%.

### Predictors (features)
- **Climate drivers:** Niño 3.4 (El Niño / La Niña) last month and its 3-month change; the Southern Annular Mode
  last month and its 3-month mean
- **Recent temperature:** the cell's anomaly for each of the last 3 months, and its 12-month and 10-year averages
- **Regional temperature:** the neighbourhood (±2°) and WA-wide anomalies
- **Time and place:** lead time, target and issue month (as seasonal cycles), latitude, longitude, elevation,
  land fraction, the cell's warming trend and its normal temperature

### Why LightGBM, and why not LightGBM alone
- **Why LightGBM:**
  - Seasonal climate effects interact by season and region, and tree models capture that without hand-built
    interaction terms.
  - It trains in seconds on about 800,000 rows and handles missing values.
  - It is the standard strong choice for tabular data.
  - Its most important feature was Niño 3.4, which matches the known physics.
- **Why not alone:**
  - The real signal is weak, and the 255 cells in a month move together. The effective sample is closer to
    "years × months" than 800,000 independent rows.
  - LightGBM stopped learning after a median of only 78 rounds, a sign of overfitting risk.
  - Ridge was better 1–2 months ahead and LightGBM 4–6 months ahead. **Their average was statistically better
    than LightGBM alone at leads 1–3, and equal at 4–6.**
- **Why not deep learning or a physics model:**
  - About 45 years of monthly data is too little for deep nets to beat simpler models.
  - Physics-based seasonal forecasts already exist (Copernicus C3S). The right next step is to compare
    against them, or blend with them, not to rebuild them.

### How it was validated (no data leakage)
- **Rolling-origin hindcast:** for each year Y from 2006 to 2025, everything (baseline, trend, models, error
  spread) is fitted only on data before 1 January Y. All 12 issues of year Y are then forecast and scored.
  That gives 20 years × 12 issues × 6 leads × 255 cells.
- **Inner validation** on the five years before Y sets LightGBM's number of rounds and each model's error spread.
- **Unit tests** prove that changing any future month does not change a forecast's inputs.
- **Baselines compared:**
  - climatology (predict the normal)
  - trend
  - damped persistence (last month's anomaly, shrunk with lead)
  - ridge alone and LightGBM alone
- **Year-block bootstrap** (resampling whole years) checks that the improvements are not luck.

### Results (backtest)

| Lead (months ahead) | 1 | 3 | 6 |
|---|---|---|---|
| Average error, ensemble | 1.01 °C | 1.07 °C | 1.08 °C |
| Average error, "predict the normal" | 1.13 °C | 1.12 °C | 1.12 °C |
| Squared-error reduction vs normal (bias-corrected, 2011–2025) | **23%** | **13%** | **10%** |
| Warmer/cooler call correct, ensemble | 65% | 61% | 60% |
| Same, for "always say warmer" | 61% | 61% | 61% |

Other results:
- **Unusual months** (more than 1.5 °C from normal): the direction is right 72% of the time.
- **Ranges:** the actual temperature fell inside the stated 80% range 78% of the time.
- **Where it works best:** summer and the north. Broome, Perth, Port Hedland and Fitzroy Crossing are good;
  Karratha and Carnarvon show no useful skill.

**Honest summary:** the skill is real but modest, which is normal for seasonal temperature forecasting. At 3–6
months its warmer/cooler call is barely better than "always warmer". Its value is in the size of the departure
and in unusual months.

### Current outlook (November 2026 issue)
- **All of WA:** about +1.2 to +1.7 °C above the 1991–2020 average through April 2027, with about a 75–80%
  chance of each month being warmer than average.
- **Where the warmth comes from:**
  - about +0.45 °C long-term warming trend
  - about +0.33 °C recent faster warming
  - about +0.7 °C the current climate state: the strong 2026 El Niño (Niño 3.4 at +2.8 °C) and a warm September

---

## 6. Known limits and next steps

**Limits**
- Reanalysis grid data (about 50 km), not station records. It has not yet been checked against SILO or
  ACORN-SAT stations.
- The Indian Ocean Dipole index is not yet included; it matters for south-west WA in winter and spring.
- Strong El Niño years are rare in the training data, so the response to the current event is less certain.
- **Not yet compared with Copernicus C3S backtests.** This is the key test before choosing between the two
  products or blending them.
- The November issue uses October 1–21 and carries the September climate indices forward. Re-run in early
  November.

**Q3 coverage**
- This covers the **seasonal outlook** part of Q3.
- Still to build:
  - the annual **historical heat-exposure** view (needs an agreed heatwave definition)
  - a "what changed since the last issue" view
  - a handoff to the Short-term Heatwave Planner (Q1)
  - an officer usability session
- Per the 28 October decision, Q3 is meant to be a separate application. The standalone map is the closest to
  that, and the panel in this demo is for review.
