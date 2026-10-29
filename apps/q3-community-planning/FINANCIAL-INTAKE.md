# Financial support intake

Season Ahead can attach dated synthetic support context to the active business snapshot. Open Manage business data, expand Financial support history, choose the eight files below and confirm they are synthetic. Stage validates them without replacing current context. Review the dated area counts, then choose Replace or Discard. Refresh local data on the map and enable Financial context to see the attached counts.

The four previously reviewed packages remain on their exact pinned registry path. Fresh synthetic packages can use the separate `q3-synthetic-financial-v1` policy described in [SYNTHETIC-FINANCIAL-PACKAGE-CONTRACT-v1.json](SYNTHETIC-FINANCIAL-PACKAGE-CONTRACT-v1.json). That path validates actual rows, relationships, dates, totals and measured resource use before deriving a proposal. A new seed needs no source registry edit. Unknown packages without this explicit contract, or with invalid content, remain rejected. Neither path imports arbitrary real financial systems.

Fresh packages declare that all five synthetic source tables cover the exact retained cohort and recorded window. Their generator name/source hash/seed are uploader-declared provenance; they do not authenticate who generated the rows. The server recomputes file hashes, sizes, counts and aggregates and never executes uploaded code. Internally consistent declared tables are not proof of real-world completeness, representative customer behaviour or complete daily electricity history. New account sources without matching validated financial history retain unavailable support context.

## Input and response

`POST /api/q3/financial/stage` accepts multipart form data with exactly these file fields:

| Field | Exact filename |
|---|---|
| customers | customers.csv |
| usage | consumption_daily.csv.gz |
| manifest | manifest.json |
| arrangements | payment_arrangements.csv.gz |
| hardship | hardship_programs.csv.gz |
| grants | hugs_grants.csv.gz |
| support | support_arrangement_history.csv.gz |
| payments | payments.csv.gz |

Two text fields are required: `synthetic=true` and `baseGeneration`, the current 64-character generation. The separate request ceiling is 32 MiB including multipart framing. The browser reserves 16 KiB for framing. Partial, duplicate and unexpected parts fail; exact filenames and unambiguous Content-Length are required. A shared single validation worker serves the business and financial routes. A busy worker rejects another request before reading its body.

A 202 response means bytes were accepted and validation is pending. It includes a bounded opaque `jobId`, never a passed validation or an active replacement. Poll `GET /api/q3/financial/stage-status?id=...`; states are accepted, validating, ready or failed. A ready result contains an aggregate-only `proposedSupport`, stage ID, base generation, expiry and coverage evidence. No raw customer, debt or medical fields are returned. At most four receipts/proposals are kept for 30 minutes in memory.

`POST /api/q3/financial/replace` takes JSON `stageId` and `baseGeneration`. The generation must still match. `POST /api/q3/financial/discard` takes `stageId`. Replacement is explicit and uses the shared atomic last-good store and advisory lock. Failed validation, stale generation, disk failure or an incomplete package cannot overwrite validated context. Restart retains a completed replacement; uncommitted receipts expire. An unknown acknowledgement outcome is inspected rather than automatically resubmitted.

## Binding and calculation

The legacy pinned registry binds the manifest, all source hashes, geography registry, customer/usage pair, snapshot, two-year window, account coverage and deterministic aggregate. Those entries remain unchanged. For fresh packages, the versioned server validation policy supplies the content checks instead of a per-seed code allowlist. Both routes bind the exact customer/usage pair already active in the business snapshot and require an unchanged base generation before replacement.

Fresh input retains the same CSV headers and eight multipart files. Its manifest adds `synthetic_financial_contract: "q3-synthetic-financial-v1"` and `financial_coverage` containing the exact sorted retained-area postcodes, matching history dates and `complete-synthetic-source-tables` declaration. Existing manifest fields identify a synthetic season-ahead profile, count/window/seed, declared generator/source hash, exact server geography hash and seven table schemas/hashes/measured byte/row counts. Optional QA coverage is metadata only and is not uploaded. Duplicate JSON keys and malformed metadata fail.

The policy checks all customer flags/solar/registration fields used by the synthetic contract, exact usage component sums, unique bounded identifiers, known customer lifecycle boundaries, support parents and complete active/terminal history, positive plan instalment/count reconciliation, hardship assessment/exit states, grant application debt/cap and hardship interval, and the exact cleared grant-payment join. Event dates stay inside the recorded history. Scheduled review dates may extend at most 366 days beyond the snapshot; they do not count as observed future events. Unknown opening evidence remains unknown. Financial payment amounts and plan instalments must be positive ordinary decimal currency; other monetary fields are finite nonnegative exact cents within the policy's numeric bounds, never exponent notation. Grant payments remain counted once.

The server measures gzip output while reading and then checks actual parsed rows against the manifest. Existing 32 MiB request, 16 MiB encoded-file and 96 MiB decoded-file bounds remain. The fresh-policy batch ceiling is 256 MiB decoded across seven CSVs; all five financial tables together may contain at most 2,000,000 rows, each parent table 200,000, support history 400,000, and each other financial table 1,500,000. The original 100k-customer/1.5m-usage limits remain. Rehashing invalid or incomplete content cannot make it valid.

A successful fresh proposal has the versioned `q3-financial-support-v3` aggregate envelope and a server-produced validation receipt. It records policy, declared generator provenance, exact source/cohort hashes, measured file metrics and an aggregate checksum. No endpoint accepts uploaded aggregates or receipts as a replacement source: Replace uses only a server-created stage token and the matching generation. On local restart the server checks the recognised policy, receipt bindings, schema and aggregate/ledger reconciliation. The receipt is an integrity record in the existing private runtime, not signed attestation against an attacker who controls the host's files. No signing secret or raw-row archive is added.

Legacy `q3-financial-support-v2` output remains unchanged and is still checked against its exact reviewed entry. The browser accepts both envelopes, validates policy/shape/count/resource metadata and reconciles the grant ledger before displaying a replacement. Cryptographic receipt checks and source-row validation happen on the server.

Arrangement and hardship counts use distinct accounts active at the dated business snapshot, with support intervals start-inclusive and end-exclusive. The union counts an account once if it belongs to either group. Every begun support parent needs its matching history; absent intervals fail validation. Covered areas with no qualifying records can show zero. An area absent from account coverage remains unavailable. The older statewide fixture deliberately omits Fitzroy Crossing and Halls Creek; fresh packages follow their actual validated coverage.

Grant records join cleared payments once to the grant parent and retained cohort. The two-year ledger describes recorded payments; it does not predict activity or eligibility in later forecast months. Count, recipients and integer cents reconcile to the server-derived aggregate and its source evidence. No individual risk score or general payment-difficulty classification is derived.

| Screen value | Existing source and calculation |
|---|---|
| Active accounts | Customer status/open/close evidence and supplied usage snapshot, unchanged from the business adapter |
| Arrangement accounts | `payment_arrangements` joined to support history, distinct snapshot-active accounts |
| Hardship accounts | `hardship_programs` joined to support history, distinct snapshot-active accounts |
| Either support group | Union of those distinct snapshot-active accounts |
| Paid grant records/amount | Grant parent plus cleared grant payment join, once per recorded event; integer cents summed |
| Recipients in retained cohort | Distinct grant recipients over the recorded window, without a monthly activity assertion |
| Census income | Existing dated public context; unavailable areas stay unavailable |

The Financial context toggle uses the existing insight rail. It adds no financial map colour, export or forecast-based support prediction. Month changes keep the business snapshot and financial window fixed. Public income, SILO history, ECMWF means and model-hindcast anomalies keep their separate sources and definitions.

## Access and recovery

The actual HTTP handlers apply the existing Q3 manager guard before reading private data or request bodies. Mutations also require the Q3 session, CSRF token and exact approved origin when enforcement is configured. Handler tests use ephemeral accounts and cover forged roles, officer access, Q1 cookies and wrong origins. No persistent user, password or session secret is created by the financial intake. The current native service uses the approved separate Q3 identity store and enforced manager launcher; the old preview-mode statement is superseded. Acceptance fixtures never modify that ongoing store.

Only aggregate output, hashes and bounded audit metadata enter the saved snapshot. Raw uploads remain in memory during validation and are released afterwards. Replacing the account source preserves support only if its exact binding still validates; otherwise it clears support and gives an explicit unavailable reason. Climate promotion preserves the independent dated financial attachment. The browser validates a complete replacement packet and retains its last good packet on failure.

The independent functional reviews and regression tests are scoped evidence of these workflows, not a production-security audit. The native climate timer and approved separate manager store are now active. The current acceptance handoff records their activation evidence and limits; no newer real climate issue ingestion or container credential cutover is claimed.
