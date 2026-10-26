# Verification · 26 October 2026

The final review uses the recovered `demo` commit `e3c95f2a4b0bed8a24d7c18f36b2808a48edadba` as its base, on local branch `fix/community-map-placeholders`. `main` was older at `b3916880d3bdb19bea84138faf8e0333d9ab2f69`. The original checkout was clean; no worker's changes were reset or overwritten.

## Recovered and reconstructed

Recovered: prepared 2025 fixture and provenance, as-of functions, prepaid and billed calculations, explicit need/arrangement histories, dated support events, issued planning assumptions, Census postcode values, MapLibre assets and loopback server. The scenario payload and hash are unchanged.

Reconstructed from the approved brief: customer-review table, shared account workspace and overview, navigation with retained queue state, separate Community planning layout, concise labels and responsive styling. Figma MCP returned the Starter quota limit on the first design-context read; exact matching to frames 2:2–2:8 is unverified. The implementation uses the supplied 64px header, 240px sidebar, 32px desktop padding, 24px gaps, white cards, #F5F7F7 background and #126A65 teal. Inter is the preferred font; the browser falls back to installed system fonts when Inter is absent.

## Fixed

- Removed the synthetic polygon, customer point and offline sketch. The map draws no boundary without genuine matched geography. Account review stays separate from the area map.
- Search, combined filters, seven sortable columns, empty results, pagination, account navigation and both Back paths preserve review context in the URL. Repeated navigation does not duplicate handlers or canvases.
- Current explicit needs, support and preferred contact use effective records at the case date. A review due today is not labelled overdue.
- Missing contact progression is distinct from an explicit unsuccessful contact; the latest dated decision governs acceptance. Delivery and resolution retain separate states. Campaign cases cannot enlarge the geographic audience denominator.
- Billed monthly estimates are withheld when elapsed usage days are missing. Missing or invalid tariff evidence does not produce NaN estimates. The existing canonical fixture arithmetic is retained.
- Replaced the arrangement screen's incorrect claim that billed review was unavailable. Contact flags use readable labels. Closed accounts retain historical context without receiving new financial review signals.
- Added labelled controls, table column semantics and sort state, keyboard focus cues, a skip link, one page title, mobile layouts, bounded table scrolling and map resize/disposal handling.

## Passed

- `node --test test-*.mjs`: **60/60** (52 retained tests and eight new review/data regression tests).
- Existing `checks.html`: **36/36** against the same core functions as the views.
- `python3 scripts/qa-teamconnect.py --output /tmp/teamconnect-qa`: **16/16 browser QA groups**, using real Chromium at 1440×900 and 390×844. Groups cover sorting/search/combined filters, no results, clear, pagination, customer references, all tabs, repeated clicks, browser Back, Back to review, reload/deep links, invalid URL state, prepaid/billed values, disclosed cooling, dated arrangement and resolution states, area-only maps, resize, zoom, missing library/WebGL and missing data/retry.
- All 12 communities × four weather scenarios × three boundary dates rendered without invalid numeric labels.
- No uncaught browser exceptions or external requests in the browser run. No credentials were used, displayed or added.
- Prepared fixture SHA-256 still matches `provenance.json`: `08f3bed764f6f3e8aab349338bfd7ce8eec7521cb5e233c4533354eb23f0e756`.
- JavaScript syntax, Python compilation and `git diff --check`.
- The server still refuses credential and directory paths. Its CSP is unchanged; only `review.mjs` was added to the asset allowlist.

## Screenshots

All screenshots contain synthetic records only. The seven main screens and billed example are in [docs/qa](docs/qa/): [Customer review](docs/qa/customer-review.png), [Overview](docs/qa/customer-overview.png), [Financial pressure](docs/qa/financial-pressure.png), [Disclosed needs](docs/qa/disclosed-needs.png), [Existing arrangements](docs/qa/existing-arrangements.png), [Support journey](docs/qa/support-journey.png), [Community planning](docs/qa/community-planning.png) and [Billed calculation](docs/qa/billed-pressure.png). The [browser results](docs/qa/results.json) record each QA group.

## Remaining blockers and unrun checks

- **Live basemap:** the recovered code has no MapTiler style/key configuration. Its background-only MapLibre canvas and controls are tested; authenticated basemap/tile networking is not. No API configuration, restriction or service was changed.
- **Real boundaries and climate:** the release has synthetic forecast footprints and real postcode statistics, but no genuine boundary dataset with a valid join or historical climate observations. No replacement geography or climate history was fabricated.
- **Figma:** Starter MCP quota prevents source-frame inspection. This is a reconstruction from the approved brief, not a claim that the missing laptop implementation was recovered.
- **Source reconciliation:** the original extracted release is absent in cloud. The earlier independent 94-file / 613,440-interval reconciliation was not rerun; only the retained prepared payload hash was checked here.
- **Browser coverage:** Chromium desktop/mobile viewport QA passed. Safari, Firefox and a full accessibility audit were not run.
- **Teammate access:** the GitHub CLI metadata read returned `Forbidden`; the dependent collaborator lookup did not run. Namash and Audrey's individual permissions are unverified. Repository access was not changed.
