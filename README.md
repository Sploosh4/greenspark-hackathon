# Team Connect browser demo

A bounded account-review website for a Horizon Power hardship officer. The five views share one community, customer, case date (12:00 AWST) and weather scenario. All account and operational records are synthetic. ABS postcode context is separately identified.

This five-tool demo is a **rough first draft and needs significant work**. The design, workflows and calculations are open to challenge and change. Treat it as a starting point for discussion and further development.

## Run locally

No container, Node, build step or package installation is needed to run the prepared demo. Python 3 serves a fixed allowlist on loopback, without directory listings or credential access.

```sh
python3 serve-demo.py --port 8787
```

Open **http://127.0.0.1:8787/**. Stop with Ctrl+C. Do not use the earlier `dist/` mockup as the new demo entry point.

## A short demonstration

1. Start with **C105011 / South Hedland / 17 January / January Pilbara heat**. Tool 1, **Anticipate financial struggles**, shows $109.66 credit and seven completed days of delivered energy. Its recent off-supply periods prevent a reliable coverage calculation, so the estimate is withheld. The forecast was issued on 17 January for 20–25 January; later vintages and actual future outcomes are absent.
2. Open **Disclosed needs**. The budgeting concern was explicitly recorded on 16 January. The current contact preference is displayed as a dated record; it does not authorise the demo to contact anyone.
3. Open **Community outlook**. Inspect the twelve-month review-volume ranges, regional capacity assumptions, issued seasonal scenario, postcode Census context and dated area billing/support counts. These support a longer-term planning discussion, without prescribing staffing or outreach actions. The release contains no historical climate observations, and the UI says so.
4. Open **Arrangements**, then select **21 Jan**. The completed support review creates a support check-in arrangement with its review date. It is not an instalment contract or payment transaction.
5. Open **Support journey**. At 17 January the review is accepted but undelivered; on 21 January delivery is recorded while the concern remains ongoing; on 28 January a customer-confirmed resolution appears. The adjacent community campaign uses its own geographic audience denominator. The customer-initiated case is explicitly separate from that campaign.
6. Select **Billed example**. C105019 / Halls Creek / 7 March / northern heat shows a $184.28 current-month estimate against the $167.89 February bill issued on 1 March (+9.8%). Inspect the measured-use arithmetic, tariff, dated payments and forecast. The estimate does not establish ability to pay.

The C105011 date buttons restore that customer while retaining the selected analytical view. Reset restores the original prepaid example. Community selection picks a valid customer in that community; customer, date and scenario controls update the same shared context. Browser back/forward and reload retain URL state.

For an explicitly disclosed cooling example, choose **South Hedland / C101664 / 17 January / January heat**, then **Disclosed needs**. Its recorded temperature-controlled-space need matches the issued heat footprint. No diagnosis is inferred from usage, and payment history does not gate this view.

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

MapLibre GL JS 5.24.0 is vendored from its npm distribution with its stylesheet and licence. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for its source and ABS data attribution. It renders the supplied GeoJSON and selected fictional customer locally, with zoom controls and attribution. No customer-like records or geometries are sent to a map/geocoding API. The MapTiler basemap is clearly unconfigured; no key was read, copied, logged or persisted. Missing MapLibre/WebGL leaves the offline SVG footprint visible and the rest of the demo usable. The default server makes no external requests.

Current live weather remains separate. The sibling prototype and its weather fetcher were not edited. There is no daily scheduler, live-weather app integration, language tool, eligibility decision, action recommendation, auto-contact, account creation, deployment or container.

## Verification

Open **http://127.0.0.1:8787/checks.html** for the 36 deterministic checks against the same functions used by the views. See [VERIFICATION.md](VERIFICATION.md) for browser interactions, source reconciliation and remaining limits.

The previous mockup files and tests remain untouched under `dist/` and the existing top-level test files. Their original documentation is retained in [README.legacy-mockups.md](README.legacy-mockups.md). They are not loaded by the Team Connect server.
