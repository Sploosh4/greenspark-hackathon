# Demo Mockups

Interactive management dashboard for five proposed extensions: heatwave credit forecasts, consumption context, weather-related bill previews, planned-outage preparation and solar benefit-loss alerts.

This is a UI scenario, not a live operational dashboard or a validated predictive model. Alerts, forecasts, estimates, trend values and workflow state are simulated. Customer IDs, retailer, region, selected account characteristics and contact preferences come from the supplied mock-data.zip. No customer names, contact addresses or transcripts are published.

The scenario is fixed at 14 January 2025. Retailer, region and forecast-window filters update all summary panels; extension and priority filters, customer search and sorting apply to the review queue. Contact eligibility in this demonstration requires an explicit proactive-support consent flag and an allowed channel. This fixture rule is not a statement of retailer contact policy.

Horizon Power is selected on first load. Selecting an extension changes the queue heading into a link to that extension's panel. Selecting a region alone changes the heading to Regional exposure; when an extension is also selected, the clickable region tag links to Regional exposure. Clearing the region tag preserves other filters. Each row shows its flag reason; case details show the contributing scenario values and the priority rule.

The 270 raw records (including four explicit overlap scenarios) are preselected illustrative fixtures, not the output of scanning all customers. The browser removes heat, outage, bill, usage and solar candidates that do not qualify before displaying any figures. Priority rules are: heat requires a prepay account, a confirmed matching upcoming or ongoing heat event, a balance read within 24 hours and complete top-up input; projected credit must run out before the end of the heat period, leaving a positive estimated shortfall; the heat credit gap starting in less than 24 hours is Urgent, less than 48 hours is High and later gaps are Review; usage drops must be at least 30%, have explicit checks showing no outage or solar explanation, and have a supporting signal (three or more days of decline, two or more near-zero days in seven days, a prepay self-disconnection in seven days, or usage down at least 30% on hot days); qualifying drops above 65% are Urgent, other qualifying drops are High; bill pressure requires a forecast increase of at least 25% plus at least one missed payment in 90 days, failed direct debit in 90 days, or a positive arrears change between 30 November and 31 December; a forecast increase of at least 40% with two or more distinct payment-stress signals is Urgent, at least 40% with one signal or at least 25% with two signals is High; outage readiness requires the exact premises ID in the affected-premises list, a still-scheduled upcoming interruption and no acknowledgement of the current notice for that event and premises; outage status and complete acknowledgement checks must be no more than 24 hours old; qualifying life-support accounts are Urgent and qualifying outages of at least six hours are High; solar requires an export drop of at least 30%, explicit checks showing neither clouds nor seasonality explains it, at least a 20% shortfall against weather/season-adjusted expected exports, and either imports up at least 20% or shortfalls on at least three comparable sunny days in seven days; a residual shortfall of at least 40% with both supporting signals is High. Other cases are Review. Concession status does not contribute to bill priority. The bill-pressure evaluator filters candidates before any dashboard aggregation, queue, or CSV export. Forecasts and payment-stress fields are illustrative scenario values; the evaluator is a demo rule, not a validated detection model. Distinct signal types, rather than the raw number of events, drive priority.

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
node --test test-bill-pressure.mjs test-usage-changes.mjs test-solar-performance.mjs test-heatwave-credit.mjs test-outage-readiness.mjs test-customer-review.mjs test-exposure-summary.mjs
```

Cloud/season explanations, adjusted solar-export expectations, imports and sunny-day shortfalls are simulated. The archive does not supply the actual weather/irradiance feed or a validated seasonal solar baseline used by these rules. A live implementation would need those inputs aligned to the same account, location and time window. They could come from files, an API or a database; no particular physical folder is required. Unknown explanation status does not qualify.

Usage-context and supporting-indicator values are simulated. Outage and solar explanation flags represent explanations established in the scenario; a live implementation would need to verify whether the event accounts for the drop. Temporal overlap alone does not establish this. Unknown explanation status does not qualify. The usage donut groups each qualifying case once by its primary supporting signal; all matched supporting signals appear in the queue and case evidence.

Heatwave credit uses the fixed scenario assessment time, a timestamped meter balance, average spending before heat and estimated spending during heat. Posted top-ups at or before the meter-read timestamp are already included in that balance. Later posted top-ups up to the assessment time are added once, with estimated spending since the read deducted. Pending or future top-ups are excluded. Recent posted top-ups in the last 72 hours remain visible even when already included. Coverage through the exact end of heat does not flag. Priority and daily chart buckets use when the credit gap overlaps the heat period, so a balance running out days before a distant heat event is not automatically urgent. The seven-day and three-day filters include heat cases by that gap date.

Heat forecasts, heat-period costs, balance snapshots and top-ups are simulated; no live meter or payment feed is connected. Demo heat periods use contiguous scenario days at or above 40°C; this is a fixture convention, not a meteorological heatwave definition. The evaluator requires a confirmed heat-event input and matching location rather than treating temperature alone as an alert. A live implementation needs confirmed local forecasts, timestamped meter balances, reconciled top-ups and spending estimates. Unknown or stale input does not qualify.

Outage readiness uses the current event schedule for dates and duration, not a region-only match or an old duration field. Cancelled, restored, postponed, already-started, past and unknown events are excluded. Acknowledgement must match the event, premises and current notice version. An acknowledgement for a different event/premises or a superseded notice does not acknowledge the current notice. The rules run before all summary counts, regional exposure, the queue and exports. Existing contact-consent rules still apply separately.

Outage premises identifiers, affected-premises lists, event status, schedules, notice versions and acknowledgements are simulated. Customer and life-support profile flags retain their supplied mock source. A live implementation needs an authoritative account-to-premises mapping, current network event records and acknowledgement history matched to the correct premises and notice. The 24-hour freshness and seven-day look-ahead limits are demo conventions. Unknown or stale checks do not qualify as verified unacknowledged outages.

Review queue entries are grouped by retailer and customer after each extension has qualified its candidates and the retailer/region/time context is applied. An extension or chart-day filter selects customers with a matching flag, while retaining all their qualifying flags within that context. A day and extension must match the same flag. Customer priority is the highest priority among their flags; priority filtering uses that customer priority. The overview total and regional exposure count unique customers. Extension panels retain their individual flag counts and priorities. Every reason and its factors is shown; detailed fields remain available for each flag.

Selection, pagination and CSV exports operate on customers. Handoff exports contain one row and one combined draft per customer, all contributing case IDs, signals and reasons. Contact eligibility requires consistent allowed channels and consent across the grouped flags. Legacy prepared case IDs migrate to customer keys, so a prior handoff on one flag blocks repeat preparation through another. Preparation persists across filters, reloads and tabs in the same browser; export rechecks shared browser storage while holding an origin-scoped Web Lock where supported. Another tab receives preparation updates automatically. Activity reset deliberately clears the demonstration state.

This duplicate prevention is browser-local, matching the rest of the demo workflow. It does not coordinate different browsers or team members' computers; a live shared workflow needs server-side preparation records and an idempotent handoff endpoint. Four additional simulated flags create two Horizon heat/usage overlaps and two Synergy bill/solar or bill/usage overlaps, using the same supplied customer/contact profile for each customer. Original candidate records are unchanged.

Regional exposure shows unique affected customers divided by all supplied customer/account profiles for the selected retailer and region, with the main two extension signals counted by unique customer. Regions are sorted by that percentage. A customer with several flags counts once overall and once in each contributing signal, so signal counts can overlap. Priority bars use each customer's highest priority as a percentage of the same regional population. Regions with known accounts but no qualifying flags show zero. Missing or unmatched population evidence shows an unavailable percentage rather than zero.

All extension cards use unique customers and applicable source-backed denominators: heat/prepay accounts; bill/billed accounts; solar/billed solar accounts; usage and outage/all accounts. The supplied population is not reduced to flagged candidates. Retailer/region filters scope both numerator and denominator; forecast-window changes scope the qualifying candidates while retaining that selected population. Overall rates are recomputed from distinct totals, not averaged regional rates. These are illustrative scenario coverage percentages, not measured retailer vulnerability prevalence. Profiles are the supplied archive population, not a newly inferred active-account cohort.

Heat-day counts, usage categories, bill averages, solar averages and outage summaries use one customer per relevant group. Heat, bill and solar panels also show compact contributing-factor counts, and outage region rows show their own affected-account percentages. The usage donut retains its one-primary-driver-per-customer classification. Supporting factors may overlap and are not summed into a customer total. Extension and queue filters continue to select customer reviews without changing the overview's selected retailer/region/time population.

Regional contributing signals are independent keyboard-accessible buttons. Selecting one applies that exact region and extension, clears chart-day/search/priority restrictions and the current selection, starts at page one, and moves to the Review queue. Retailer and forecast window remain unchanged. Each customer still shows every qualifying reason in that region/time context. Selecting the same signal again preserves its filters; the separate region summary retains its region-toggle behaviour. Existing queue region and extension controls can clear each filter independently.

## Team Connect applications

The verified Q1 customer-review and Season Ahead planning sources are now available in [apps/q1-customer-review](apps/q1-customer-review/README.md) and [apps/q3-community-planning](apps/q3-community-planning/README.md). See the [publication scope and limits](docs/team-connect/PUBLICATION.md) and [local container recipes](packaging/team-connect/README.md). The reviewed Sign out patch and explicit authenticated-container mode are included. Private account stores, native service wrappers, provisioning, unfinished ML work and live datasets are excluded.
