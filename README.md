# Team Connect browser demo

A seven-screen account review demo: Customer review, Customer overview, Financial pressure, Disclosed needs, Arrangements, Support journey and Community planning. Account details stay within Customer review; the map belongs to Community planning. All account and operational records are synthetic. ABS postcode context is separately identified.

This demo is a **rough first draft and needs significant work**. Its design, workflows and calculations remain open to change.

Meeting preparation and cloud coordination: [27 October handoff](docs/MANNY_HANDOFF_2026-10-27.md).

## Run locally

From this repository directory:

```sh
python3 serve-demo.py --port 8787
```

Open **http://127.0.0.1:8787/**. Stop with Ctrl+C. Python 3 is the only runtime requirement. The server binds to loopback and serves an explicit asset allowlist.

## Review the seven screens

1. **Customer review** opens first. Search `C105011` and select the customer reference. Search, review reason, account type, area and pagination operate on records known at the selected date. Default ordering is newest flagged date, then customer reference; there are no clickable sort columns in this local UI. This is a record review list, not a risk prediction or outreach eligibility list.
2. **Overview** shows the recorded review reason, flagged date, support, contact preference and account context. The shared customer, area, case date and weather controls apply to every account tab.
3. **Financial pressure** opens the prepaid path for C105011 on 17 January: $109.66 credit. Coverage remains unavailable because there are too few complete on-supply days. **Billed** selects C105019 / Halls Creek / 7 March: $184.28 estimated month bill against $167.89 previously issued (+9.8%). Open **Calculation** for the existing arithmetic and assumptions. **Prepaid** restores the original prepaid example.
4. **Disclosed needs** lists explicit records and their dated weather match. For the cooling example, select South Hedland / C101664 / 17 January / January heat. Contact preferences are records, not contact authorisation.
5. **Arrangements** shows no arrangement for C105011 on 17 January, an active check-in on 21 January, and completion on 28 January. Change **As of** to inspect those states. Missing last-review dates remain Not recorded.
6. **Support journey** separates contacted, offered, accepted, delivered and customer-confirmed resolution. C105011 is accepted but undelivered on 17 January, delivered with an ongoing concern on 21 January, and resolved on 28 January.
7. **Community planning** contains the real MapTiler basemap, matching ABS POA2021 postcode boundary/context, seasonal probabilities, monthly review-volume ranges, capacity assumptions, dated area history and the separate community campaign funnel. Planning period and hazard filters are available. All twelve months remain available in annual view.

Sidebar navigation keeps the account context. Browser back/forward and reload retain URL state. **Reset** restores Customer review and the original date and filters.

The interface follows the approved [seven-screen Figma study](https://www.figma.com/design/tTH4TACibo0u2jVE6JxIH3?node-id=2-2), with populated records, one page title, concise labels and explicit status text. The containerised prototype and legacy mockups are separate.

## Financial scope and assumptions

Tool 1 has prepaid and billed paths, rather than a sixth tool.

- Prepaid credit comes from the canonical financial override. Completed 11:30 intervals establish the 12:00 balance; a top-up exactly at 12:00 is added before any incomplete interval charge. Top-ups in the history are already included. Completed daily delivered use excludes simulator demand. Illustrative days to $0 use at least three complete on-supply days from the preceding week, assume unchanged daily charged spend and no further top-ups, and keep emergency credit separate. This is not a weather-adjusted depletion model.
- For the eight canonical billed accounts, the current-month estimate is recorded completed month-to-date kWh plus remaining calendar days at the preceding fourteen-day measured average (minimum three days), priced using the release's 33¢/kWh, $1.10/day supply and applicable $0.70/day concession assumptions. It is compared with the latest already-issued net bill. The balance uses dated cleared payment allocations, never final paid-status summaries.
- The other 298 billed accounts retain their base usage, bills and payments. Where sufficient inputs exist, the view estimates next-30-day **gross charges**, carrying forward the latest issued bill's effective usage rate and daily supply charge. Its comparison normalises that prior gross bill to 30 days. Actual next bill dates, future tariffs and credits are not supplied, so an exact next net bill is not asserted. Base original due terms are displayed without relying on undated later extensions. Missing rate or usage evidence produces an unavailable estimate.
- Weather is dated context alongside these calculations. No calibrated weather-to-demand multiplier, affordability score or performance claim is supplied. An estimated bill increase is separate from ability to pay.

Q4 displays arrangement states and reviews. No agreed instalment schedule is supplied; the demo never invents a missed-payment judgement. Q2 uses explicit need histories and direct cooling/temperature types for heat matches; it includes general support needs and excludes planned outages.

## Data and as-of rules

The prepared browser data comes from `TeamConnect-Complete-Synthetic-Demo-2025Q1-v1.zip` (`complete-scenario-2025Q1-v1`). The source archive stays outside this repository. Preparation checked extraction paths and reconciled the source; bundled generators were not executed.

`scripts/prepare-teamconnect.py` follows `selection_manifest.json`: 142 prepaid overrides, the complete eight-account billed suite, retained base finance for the other 298 billed accounts, OP25-only funnel records, and distinct base + OP25 need/arrangement episodes. It produces a 4.86 MB browser payload, with 12,780 noon snapshots instead of 613,440 intervals. It excludes latent demand/requested charge, realised hazard magnitude/exposure, old model scores and full-window case statuses.

Every view uses AWST UTC+08. Only completed financial days, dated payments, issued bills, contacts/offers/decisions/deliveries/resolutions and effective episode states available at the case time are displayed. Forecast geometry uses the latest issue on/before the case time and account status at that time. Expired forecasts are labelled historical. Annual scenario inputs were issued on 1 January and are not future observed staff work. `teamconnect/provenance.json` records the prepared data hash and release version and source selection hash.

Rebuild and independently reconcile, using the local extracted release directory:

```sh
python3 scripts/prepare-teamconnect.py /path/to/TeamConnect-Complete-Synthetic-Demo-2025Q1-v1 --out teamconnect
python3 scripts/verify-teamconnect.py /path/to/TeamConnect-Complete-Synthetic-Demo-2025Q1-v1
```

## Maps, weather and dependencies

MapLibre GL JS 5.24.0 renders MapTiler Streets v4 inside Community planning. The loopback server reads only `MAPTILER_API_KEY` from the existing `~/Projects/team-connect/.env.local`; it does not serve or copy that file. Use `--maptiler-env /path/to/.env.local` for another explicitly chosen local file. Never put the value in browser code, commands or documentation.

The `/maptiler/` resource proxy attaches the key upstream, rewrites style/TileJSON/sprite/font URLs to the local origin, and omits the key from browser responses and logs. Browser policy stays restricted to same-origin resources. Both `127.0.0.1` and `localhost` were checked; provider origin restrictions still apply to the actual hostname used. No key or account permission was changed. MapTiler requests reveal the viewed tile area; customer IDs and scenario GeoJSON are not transmitted.

The basemap contains real roads, coastline and place labels. The meeting map draws **only a genuine ABS Postal Area 2021 boundary** joined to the selected postcode's 2021 Census/SEIFA context. The exact code, geography and year must match; otherwise no boundary is substituted. Postal Areas are statistical approximations of postcodes, not legal or town boundaries. Community account histories remain at community grain, separately labelled.

The fictional rectangular forecast footprint and synthetic customer point have been removed from the planning renderer. No individual customer markers are added. Scenario geometry remains in the unchanged source fixture solely for existing account/weather calculations. The earlier SAL locality snapshots remain preserved as reference files; they are not the current map layer and must not be paired with postcode statistics.

The cloud boundary handoff's join helper and importer were reused selectively, without replacing the local UI, financial core or server configuration. Official geometry was acquired directly from its exact ABS query and prepared against all twelve context codes. Runtime files and provenance are under `teamconnect/geography/`; the join helper is `teamconnect/area-boundaries.mjs`. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Pan, zoom, Centre area, boundary visibility and area selection remain available. ResizeObserver and map lifecycle cleanup keep the canvas aligned when its container changes or the planning view is reopened. Failure shows a short error and **Retry map**. The MapTiler logo and provider/data attributions remain visible.

Offline checks: `node --test test-*.mjs`, `python3 test-map-proxy.py`, and `python3 test-poa2021-boundaries.py`. Simulate a basemap outage with `python3 serve-demo.py --port 8788 --missing-basemap`. The diagnostic endpoint `/map-health.json` reports request counts/status only, with no credentials or upstream bodies.

Current live weather remains separate. The sibling prototype and its weather fetcher were not edited. There is no daily scheduler, live-weather app integration, language tool, eligibility decision, action recommendation, auto-contact, account creation, deployment or container.

## Verification

Open **http://127.0.0.1:8787/checks.html** for the 36 deterministic checks against the same functions used by the views. See [VERIFICATION.md](VERIFICATION.md) for browser interactions, source reconciliation and remaining limits.

The previous mockup files and tests remain untouched under `dist/` and the existing top-level test files. Their original documentation is retained in [README.legacy-mockups.md](README.legacy-mockups.md). They are not loaded by the Team Connect server.
