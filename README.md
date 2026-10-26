# Team Connect browser demo

An account review demo for a Horizon Power hardship officer. Start in **Customer review**, search or filter the table, then select a customer reference. The shared account workspace has Overview, Financial pressure, Disclosed needs, Existing arrangements and Support journey sections. **Community planning** is a separate workspace.

The account-centred UI was reconstructed from the approved workflow and layout brief. The recovered implementation was `demo` commit `e3c95f2a4b0bed8a24d7c18f36b2808a48edadba`; no newer source was found on the remote branches. Figma access reached its Starter quota, so exact frame fidelity has not been verified.

All customer and operational records are synthetic. The fixed scenario uses 2025 dates at 12:00 AWST. ABS postcode context is separately identified. Records are read only; the demo sends no contact, changes no arrangement and makes no automated eligibility or allocation decision.

## Run locally

```sh
python3 serve-demo.py --port 8787
```

Open **http://127.0.0.1:8787/**. Python 3 is the only runtime requirement. The server binds to loopback and serves an explicit asset allowlist. Stop with Ctrl+C. The earlier `dist/` mockup is not this demo's entry point.

## Review the demo

- Search, community/account/context filters, all seven sort columns and pagination work together. Selecting a reference opens that account. Back to review, browser Back and reload retain URL context.
- **Prepaid example** opens C105011 on 17 January: $109.66 recorded credit. Its off-supply periods leave fewer than three complete on-supply days, so coverage is withheld. On 21 January a support check-in is active and delivered; resolution appears only on 28 January.
- **Billed example** opens C105019 on 7 March: $184.28 estimated current-month bill against the $167.89 latest issued bill (+9.8%). Expand the calculation to inspect usage, tariff and elapsed/remaining days.
- Search **C101664**, open Disclosed needs and use 17 January / Pilbara heat to see a current explicit cooling need alongside an already-issued forecast. No diagnosis is inferred and planned outages are not included.
- Community planning contains the area map frame, six- or twelve-month issued scenario ranges, regional capacity assumptions, dated account/support aggregates and 2021 postcode Census context. Climate observations and genuine boundary geometry are absent from the release.

## Maps

MapLibre GL JS 5.24.0 and its stylesheet are vendored. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The recovered demo has no MapTiler basemap configuration: its style contains only a background layer. This remains clearly labelled; credentials, API restrictions and services were not changed.

The map is confined to Community planning. It adds no customer points, synthetic footprints, fake streets or substitute boundaries, including when MapLibre/WebGL is unavailable. No genuine boundary data joined to the supplied postcode statistics exists in this repository, so no boundary is drawn. MapLibre zoom and attribution controls are retained; real basemap authentication, tiles and provider attribution still need the existing configuration supplied through an authorised follow-up.

## Checks

```sh
node --test test-*.mjs
```

The existing deterministic scenario checks remain at **http://127.0.0.1:8787/checks.html**. Optional browser regression QA requires Python Playwright and Chromium; it starts and stops its own loopback server:

```sh
python3 scripts/qa-teamconnect.py --output /tmp/teamconnect-qa
```

See [VERIFICATION.md](VERIFICATION.md) for results, screenshots and remaining blockers.

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

## Scope

Live weather and the sibling prototype were not edited. There is no daily scheduler, contact sending, account write, deployment or container requirement for this browser demo. The existing CSP and API restrictions remain unchanged.

The earlier mockup and its tests remain under `dist/` and the top-level test files. Its documentation is [README.legacy-mockups.md](README.legacy-mockups.md).
