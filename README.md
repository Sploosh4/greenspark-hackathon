# Demo Mockups

Interactive management dashboard for five proposed extensions: heatwave credit forecasts, consumption context, weather-related bill previews, planned-outage preparation and solar benefit-loss alerts.

This is a UI scenario, not a live operational dashboard or a validated predictive model. Alerts, forecasts, estimates, trend values and workflow state are simulated. Customer IDs, retailer, region, selected account characteristics and contact preferences come from the supplied mock-data.zip. No customer names, contact addresses or transcripts are published.

The scenario is fixed at 14 January 2025. Retailer, region and forecast-window filters update all summary panels; extension and priority filters, customer search and sorting apply to the review queue. Contact eligibility in this demonstration requires an explicit proactive-support consent flag and an allowed channel. This fixture rule is not a statement of retailer contact policy.

Horizon Power is selected on first load. Selecting an extension changes the queue heading into a link to that extension's panel. Selecting a region alone changes the heading to Regional exposure; when an extension is also selected, the clickable region tag links to Regional exposure. Clearing the region tag preserves other filters. Each row shows its flag reason; case details show the contributing scenario values and the priority rule.

The 266 raw records are preselected illustrative fixtures, not the output of scanning all customers. The browser removes heat, outage, bill, usage and solar candidates that do not qualify before displaying any figures. Priority rules are: heat requires a prepay account, a confirmed matching upcoming or ongoing heat event, a balance read within 24 hours and complete top-up input; projected credit must run out before the end of the heat period, leaving a positive estimated shortfall; the heat credit gap starting in less than 24 hours is Urgent, less than 48 hours is High and later gaps are Review; usage drops must be at least 30%, have explicit checks showing no outage or solar explanation, and have a supporting signal (three or more days of decline, two or more near-zero days in seven days, a prepay self-disconnection in seven days, or usage down at least 30% on hot days); qualifying drops above 65% are Urgent, other qualifying drops are High; bill pressure requires a forecast increase of at least 25% plus at least one missed payment in 90 days, failed direct debit in 90 days, or a positive arrears change between 30 November and 31 December; a forecast increase of at least 40% with two or more distinct payment-stress signals is Urgent, at least 40% with one signal or at least 25% with two signals is High; outage readiness requires the exact premises ID in the affected-premises list, a still-scheduled upcoming interruption and no acknowledgement of the current notice for that event and premises; outage status and complete acknowledgement checks must be no more than 24 hours old; qualifying life-support accounts are Urgent and qualifying outages of at least six hours are High; solar requires an export drop of at least 30%, explicit checks showing neither clouds nor seasonality explains it, at least a 20% shortfall against weather/season-adjusted expected exports, and either imports up at least 20% or shortfalls on at least three comparable sunny days in seven days; a residual shortfall of at least 40% with both supporting signals is High. Other cases are Review. Concession status does not contribute to bill priority. The bill-pressure evaluator filters candidates before any dashboard aggregation, queue, or CSV export. Forecasts and payment-stress fields are illustrative scenario values; the evaluator is a demo rule, not a validated detection model. Distinct signal types, rather than the raw number of events, drive priority.

Case review, message copying and CSV handoff are browser-local. No messages are sent and no retailer account is changed. Prepared case state is retained in local browser storage and can be reset in the Activity panel.

## Run a downloaded copy

From this project folder, run:

```sh
python -m http.server 8787 --directory dist
```

Open http://localhost:8787 in your browser. Python 3 is the only tool needed for this command. Any static HTTP server can serve `dist/`; the website has no runtime dependencies or external assets. Serve the folder rather than double-clicking index.html, because the app uses JavaScript modules and fetches data.json.

The prepared scenario is already included as `dist/data.json`. Keep it beside `dist/index.html`, `app.js` and the rule modules. Viewing the demo does not need the ZIP, a Downloads folder, credentials or the original source files. Browser-local case preparation is not shared between computers.

## Rebuild the scenario (optional)

With Python 3, either put the original archive at `data/mock-data.zip` and run `python build-fixtures.py`, or choose any location:

```sh
python build-fixtures.py --data-zip "path/to/mock-data.zip"
```

The archive must contain customers.csv and contact_preferences.csv at its root. Rebuilding replaces dist/data.json deterministically. The original archive is excluded from version control at the default location; share it separately with your teammate. The prepared mock scenario is intentionally included so the GitHub download works as-is.

Optional rule checks, with Node.js installed:

```sh
node --test test-bill-pressure.mjs test-usage-changes.mjs test-solar-performance.mjs test-heatwave-credit.mjs test-outage-readiness.mjs
```

Cloud/season explanations, adjusted solar-export expectations, imports and sunny-day shortfalls are simulated. The archive does not supply the actual weather/irradiance feed or a validated seasonal solar baseline used by these rules. A live implementation would need those inputs aligned to the same account, location and time window. They could come from files, an API or a database; no particular physical folder is required. Unknown explanation status does not qualify.

Usage-context and supporting-indicator values are simulated. Outage and solar explanation flags represent explanations established in the scenario; a live implementation would need to verify whether the event accounts for the drop. Temporal overlap alone does not establish this. Unknown explanation status does not qualify. The usage donut groups each qualifying case once by its primary supporting signal; all matched supporting signals appear in the queue and case evidence.

Heatwave credit uses the fixed scenario assessment time, a timestamped meter balance, average spending before heat and estimated spending during heat. Posted top-ups at or before the meter-read timestamp are already included in that balance. Later posted top-ups up to the assessment time are added once, with estimated spending since the read deducted. Pending or future top-ups are excluded. Recent posted top-ups in the last 72 hours remain visible even when already included. Coverage through the exact end of heat does not flag. Priority and daily chart buckets use when the credit gap overlaps the heat period, so a balance running out days before a distant heat event is not automatically urgent. The seven-day and three-day filters include heat cases by that gap date.

Heat forecasts, heat-period costs, balance snapshots and top-ups are simulated; no live meter or payment feed is connected. Demo heat periods use contiguous scenario days at or above 40°C; this is a fixture convention, not a meteorological heatwave definition. The evaluator requires a confirmed heat-event input and matching location rather than treating temperature alone as an alert. A live implementation needs confirmed local forecasts, timestamped meter balances, reconciled top-ups and spending estimates. Unknown or stale input does not qualify.

Outage readiness uses the current event schedule for dates and duration, not a region-only match or an old duration field. Cancelled, restored, postponed, already-started, past and unknown events are excluded. Acknowledgement must match the event, premises and current notice version. An acknowledgement for a different event/premises or a superseded notice does not acknowledge the current notice. The rules run before all summary counts, regional exposure, the queue and exports. Existing contact-consent rules still apply separately.

Outage premises identifiers, affected-premises lists, event status, schedules, notice versions and acknowledgements are simulated. Customer and life-support profile flags retain their supplied mock source. A live implementation needs an authoritative account-to-premises mapping, current network event records and acknowledgement history matched to the correct premises and notice. The 24-hour freshness and seven-day look-ahead limits are demo conventions. Unknown or stale checks do not qualify as verified unacknowledged outages.
