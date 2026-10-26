# Verification — 26 October 2026

Local checks were performed in real Chrome against the loopback server. They validate this bounded synthetic draft, not production suitability or predictive accuracy.

## Passed

- All five views render from the prepared canonical release, with the same selected community/customer/date/scenario. Both prepaid and billed Tool 1 paths render; the billed calculation is inspectable.
- Community selection (Esperance) and customer selection (South Hedland C101664), date input (1 January), scenario selection, C105011 date checkpoints, billed shortcut, reset and browser back navigation.
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

- MapTiler basemap authentication and remote tile/network behaviour: the existing key remains untouched. Local geometry rendering and map-library failure were tested.
- A calibrated weather-to-demand model, validated affordability prediction, actual future net bills for the 298 retained base billed accounts, production tariffs, production eligibility and live customer systems.
- Live 2026 weather integration and historical climate observations. The release supplies fixed fictional forecasts and issued annual scenario inputs; these are labelled accordingly.
- Dedicated mobile-device and non-Chrome browser testing. Responsive CSS is implemented, but a mobile result is not claimed.
- No shared/server workflow writes, real outreach, production hosting, deployment or containerisation.

## Failure-check run commands

```sh
python3 serve-demo.py --port 8788 --missing-data
python3 serve-demo.py --port 8789 --missing-map
```

These are isolated QA switches. The ordinary run command remains `python3 serve-demo.py --port 8787`.

## Screenshot evidence

Seven synthetic demo screenshots were checked visually and saved separately: prepaid review, billed review, explicit cooling need, planning chart, arrangement history, resolved journey and verification results. They contain no visible keys, personal contact details, real people or unrelated browser material. Screenshot storage identifiers and local workspace paths are intentionally omitted from this public repository.

The owned local QA servers were stopped after verification. Restart the ordinary server with the README command.
