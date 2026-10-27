# Verification — 27 October 2026

Local checks were performed in real Chrome against the loopback server. They validate this bounded synthetic draft, not production suitability or predictive accuracy.

## Current Manny meeting revision · 27 October

The current revision preserves the latest local UI and authorised MapTiler integration, removes planning-map placeholders, and selectively reuses the reviewed cloud POA2021 importer/join files. It does not replace the local UI with the older cloud version or merge either cloud branch.

- **28/28 final browser workflow checks pass.** Customer review: reference search, combined filters, empty results, default date/reference order, pagination, opening accounts, repeated active-tab clicks, browser Back and list return were exercised. Current support excludes ended arrangements; overlapping support/disclosure records are included in the support filter. Search trims whitespace and date-only deadlines become overdue on the following day.
- Account workspace: Overview, prepaid/billed Financial pressure, Disclosed needs, Arrangements and Support journey were checked, including the $109.66 and $184.28 fixtures and dated delivery/resolution progression.
- Planning: real roads, coastline and place labels render. Pan/zoom, area selection, planning filters and consistent canvas/container dimensions after switching views were checked. The only custom layer source is the real postcode area; no fictional polygon or customer marker is rendered. Required MapTiler, OpenStreetMap and ABS attribution remains visible.
- Matching geometry: all 12 official POA2021 geometries were acquired directly via the cloud handoff's fixed ABS query. Source acquisition and output hashes are retained in `teamconnect/geography/poa2021.provenance.json`. The exact postcode, POA geography and 2021 year agree with the retained Census/SEIFA context. No SAL/town-name substitution or finer-area statistic allocation is used. Earlier SAL snapshots remain preserved, but are not drawn.
- The original scenario, provenance and financial core are byte-for-byte unchanged from `e3c95f2`. Release reconciliation passes 94 hashes, 613,440 intervals and 12,780 balances/daily rows.
- **60 Node checks** pass (52 retained legacy checks plus 8 strict boundary-join tests); **5 proxy tests**, **7 boundary-importer tests** and **36 existing browser scenario checks** pass. Browser meeting-flow results and fresh screenshots are in `docs/qa/manny-2026-10-27/`.
- Local configuration uses `MAPTILER_API_KEY` from the existing `~/Projects/team-connect/.env.local`, server-side only. Browser origin: `http://127.0.0.1:8787`. No credentials, restrictions or permissions were changed.
- Remaining differences: clickable column sorting and some cloud core edge-case guards are only on `fix/community-map-placeholders`; they have not been merged. The local default order is tested. Formal geometry topology, dedicated mobile devices and non-Chrome browsers are not claimed. See `docs/MANNY_HANDOFF_2026-10-27.md` for branch comparisons and coordination.

## Earlier MapTiler verification · 26 October


The missing basemap was an integration issue: the earlier renderer used a solid-colour local style, with no runtime key loading or MapTiler resource connection. The approved layout remains intact and the map stays in Community planning.

- Real roads, labels and coastline were checked visually in South Hedland and Carnarvon in the actual in-app browser. The selected South Hedland scenario remains the default. Screenshots were saved separately for review.
- Pan, zoom, Centre area, independent real/synthetic overlays, area selection and return from account tabs were exercised. Canvas dimensions match its container. ResizeObserver is installed and cleaned up when the map is removed.
- A simulated basemap outage shows an explicit error and retry button. Restarting the isolated QA server with the basemap available and clicking Retry map recovered the same view with a single correctly sized canvas.
- Both local hostnames were tested. A fresh localhost browser run and the final verification interval on 127.0.0.1 have no map console warnings/errors. The main server's upstream request diagnostics report zero failed MapTiler requests.
- Real ABS 2021 statistical-area geometry is independent of scenario geometry. The fictional rectangle and customer point are independently labelled/toggled, and the original synthetic coordinates and scenario values are unchanged. Required basemap, ABS and MapTiler logo attribution remain visible.
- The key is read server-side from the existing environment file. Neither the browser style/resources nor source changes contain it. Environment files, traversal and unrelated hosts remain denied. No key or permission changes were made.
- **12/12 browser map checks and 36/36 existing calculation checks passed** after the integration.
- **5/5 offline proxy tests passed**, covering environment parsing, absolute worker URLs, credential redaction/attribution, request allowlisting and safe upstream errors. The existing calculation/data module and scenario remain byte-for-byte unchanged.

## Earlier seven-screen layout verification

Implemented the approved seven-screen Figma layout in the browser demo. The Figma connector hit its plan limit; the user explicitly approved using the browser-visible frames and properties. No exported design images are embedded in the application.

- **20/20 interface checks passed** in the in-app browser: review search/reason filters, empty results, pagination, browser back, overview, both financial paths, disclosures, pre/post-delivery arrangements, delivered/resolved journey, planning, period filtering, empty campaign area, explicit cooling match, missing-data controls/retry and missing-map fallback.
- Every requested screen has one `h1`; the tested screens have no explanatory `p` blocks and no horizontal page overflow at the desktop review size. Section labels, data, recorded support summaries and compact status text remain.
- The map renders only in Community planning. A duplicate fallback SVG display was corrected using an explicit SVG hidden attribute. Map colours match the interface; expired forecasts retain a Historical forecast label.
- The pure calculation module, prepared scenario and provenance files are byte-for-byte unchanged from commit `e3c95f2`.
- The existing **36/36 deterministic browser checks passed** after the layout changes. Source reconciliation still verifies 94 hashes, 613,440 intervals and 12,780 balances/daily rows.
- Seven screen captures and the interface-check results were saved separately for local review.
- This layout revision is local on branch `demo`; no push or deployment was requested for it.

## Earlier scenario verification

- All five views render from the prepared canonical release, with the same selected community/customer/date/scenario. Both prepaid and billed Tool 1 paths render; the billed calculation is inspectable.
- Community/customer selection, date input, scenario selection, billed shortcut, reset and browser back navigation. The current layout uses the As of input instead of the earlier checkpoint buttons.
- C105011's concern is current on 17 January; support is accepted but undelivered then, delivered/ongoing on 21 January, and customer-confirmed resolved on 28 January. Arrangement history is absent before 21 January, active on 21 January and completed at resolution.
- C101664's explicit cooling need appears beside the already-issued heat footprint, without a payment-history filter or inferred diagnosis.
- Twelve-month planning chart, scenario range, capacity table, real postcode Census context and dated community billing/support history render.
- MapLibre local polygon and selected point render with attribution; zoom control responds. When the map library is deliberately served as 404, the offline footprint and support journey still work.
- When scenario JSON is deliberately served as 404, the app shows a retry screen and disables inactive context controls. Retry returns to the same honest error while data remains unavailable.
- Empty Esperance/January campaign shows zero geographic audience and no invented cases. 1 January shows zero completed prior days, no invented top-ups and no forecast issued yet. Missing comparison/rate evidence is unavailable rather than silently substituted.
- Expired forecast validity, effective end exclusivity, future disclosure/arrangement/resolution withholding, account-open forecast matching and dated cleared payment allocation rules are checked.
- **36/36 browser checks passed** in `teamconnect/checks.html`. These cover temporal boundaries, canonical overrides, financial arithmetic and missing data cases.
- Independent standard-library reconciliation verified **94 release file hashes**, aggregated **613,440 intervals**, and matched **12,780 noon balances plus 12,780 daily charge/delivered-use rows**. Re-run with `scripts/verify-teamconnect.py` and the extracted release.
- The local server returns 200 for `/` and scenario JSON, and 404 for `/.env.local`, `/../.git`, `/teamconnect/` and `/vendor/`. It binds 127.0.0.1 and serves an explicit asset allowlist without listings. CSP restricts assets/connections to the local origin and permits MapLibre's local blob worker.
- Python source compiles; repository whitespace check passes. Screenshots are non-sensitive and contain synthetic records only.

## Not tested or deliberately outside this build

- MapTiler origin/key configuration on other deployments, provider/account changes and production hosting are outside this local integration. Current local basemap behaviour is verified above.
- A calibrated weather-to-demand model, validated affordability prediction, actual future net bills for the 298 retained base billed accounts, production tariffs, production eligibility and live customer systems.
- Live 2026 weather integration and historical climate observations. The release supplies fixed fictional forecasts and issued annual scenario inputs; these are labelled accordingly.
- Dedicated mobile-device and non-Chrome browser testing. Responsive CSS is implemented, but a mobile result is not claimed.
- No shared/server workflow writes, real outreach, production hosting, deployment or containerisation.

## Failure-check run commands

```sh
python3 serve-demo.py --port 8788 --missing-data
python3 serve-demo.py --port 8789 --missing-map
python3 serve-demo.py --port 8790 --missing-basemap
```

These are isolated QA switches. The ordinary run command remains `python3 serve-demo.py --port 8787`.

## Screenshot evidence

Seven synthetic demo screenshots were checked visually and saved separately: prepaid review, billed review, explicit cooling need, planning chart, arrangement history, resolved journey and verification results. They contain no visible keys, personal contact details, real people or unrelated browser material. Screenshot storage identifiers and local workspace paths are intentionally omitted from this public repository.

The isolated failure-check servers were stopped after verification. The ordinary loopback server is kept running for local review; restart it with the README command if needed.

## Multiple review reasons follow-up · 27 October 2026

- Preserved the existing table, filter controls and page layout. Each distinct current disclosed reason now has its own line in the existing cell. Financial/other-disclosure filters match any current reason; support-record filtering retains its known-history behaviour and the existing support fallback remains when no current disclosure is present.
- Current reasons exclude resolved/closed disclosures, expired histories and future histories at the selected 12:00 AWST cutoff. Three resolved-only records no longer enter the 17 January list; 101 accounts remain, including eight with multiple reasons. Source scenario data, calculations and map code are unchanged.
- **68 Node tests passed**, including eight focused reason tests covering mixed categories, duplicates, lifecycle/time boundaries, support overlaps/fallbacks and the actual scenario at three dates. **12 Python tests passed** for the map proxy and boundary importer.
- **15 browser checks passed** at `http://127.0.0.1:8787`: multiple reasons in one cell, either disclosure filter preserving the full list, support exclusion/overlap, combined account/area filters, account opening, source disclosure records, returning with filters intact, selected-date changes, reset, pagination, search page reset, and no console warnings/errors.
- Browser evidence: [results](docs/qa/review-reasons-2026-10-27/results.json) and [screenshot](docs/qa/review-reasons-2026-10-27/multiple-review-reasons.png).
