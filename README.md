# Team Connect: Week Ahead and Season Ahead

Two applications support customer review and monthly planning with synthetic business data and attributed public weather. Staff inspect the evidence, choose whether to replace uploaded data and prepare material for human review.

| Application | Completed local functionality | Technical guide |
|---|---|---|
| Week Ahead | Frozen M5/S1 historical replay; authenticated current-date synthetic upload calculations; versioned table/detail/CSV/PDF; Sign out | [Week Ahead](apps/q1-customer-review/README.md) |
| Season Ahead | WA monthly climate/history map and warm-month filtering; named planning areas; dated account context; reusable contract-compliant synthetic financial intake | [Season Ahead](apps/q3-community-planning/README.md) |

This is a local source proposal based on public `349b366`; it has not been pushed or deployed. [Setup](docs/team-connect/SETUP.md), [build identities](docs/team-connect/BUILD-MANIFEST.json), [asset hashes](docs/team-connect/ASSET-MANIFEST.json) and [validation scope](docs/team-connect/VALIDATION.md) distinguish accepted runtime results from this portable source candidate. Full data/model/history assets remain outside Git. No public asset-download release is approved; a source download alone does not reproduce the full demo or create interactive access.

Week Ahead's default native data remains the 37-customer historical replay. The accepted current path calculated M5/S1 scenarios for a fresh 120-customer upload in disposable native/container tests; that pack was not made the live dataset. Current scenarios require fresh reported business data, modelled weather and the pinned model/runtime bundle. They are experimental synthetic usage estimates, not calibrated forecasts, official heatwave classification or payment predictions. Historical replay uses hindsight weather and simulated reporting availability; its strict/live replay modes withhold estimates.

Season Ahead displays six individual monthly ECMWF means and separately labelled SILO observational history. It has no separate three-/six-month aggregate forecast products or daily heatwave probabilities. The live dated snapshot remains 50,000 retained / 46,500 active accounts across 385 areas at 30 June 2025. Fresh 1k/50k synthetic financial packages passed disposable handler/browser acceptance without per-seed registry edits; those cohorts are not the active live data. Declarations and hashes do not authenticate a generator or prove real-world completeness.

Authentication requires separate private identities. Direct server entry points remain loopback previews; current Q1 mode requires the authenticated generic launcher. No passwords, account stores, session secrets, raw uploads or model binaries are included. External review access belongs to the separate DigitalOcean deployment phase. Operational user-guide authoring is paused pending the user's final workflow review; no user PDFs are produced by this proposal.

The original static five-extension scenario remains in `dist/`, with [legacy instructions](docs/legacy-mockups.md). Repository/app licences, [EHF attribution](apps/q1-customer-review/prototype/vendor/ehf/REUSE.md), [climate data provenance](apps/q3-community-planning/data/PROVENANCE.md) and MapLibre credits retain their scope. Final human claims, required security disposition, reviewed public asset strategy and exact publication approval remain gates in the [handover checklist](docs/team-connect/HANDOVER-CHECKLIST.md).
