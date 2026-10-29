# Synthetic historical replay

The customer table, detail view and downloads use one sealed snapshot. Its version covers the input files, frozen model manifest, calculation code, percentage policy and calculated values. Replacing a snapshot changes that version; an export for an old version is rejected.

M5 supplies the main estimate. S1 is the simple comparison shown beside it. Both use the existing frozen v3 delivery; this app does not train or select models. The original app baseline is retained separately and is never substituted into a missing M5 or S1 field.

The provisional `event_local_B` policy compares expected current uplift against current B with observed historical uplift against B at that historical event's start. Each B uses the same frozen baseline rule, but its numerical value can differ. This is a project implementation mapping, not a claim that Josh selected that technical label. `common_review_B` remains an explicit alternative in the offline builder and regression tests.

Historical daily use is the mean of every inclusive event day. Missing usage or an unknown boundary leaves the comparison unavailable. A real zero stays numeric. A customer qualifies when any available current event percentage meets any relevant linked historical percentage. The highest current event estimate determines sorting. Shared account facts appear once.

The fixed review is 2 November 2024 at 03:00 Perth. Separate simulated metadata assumes rows report at noon the following day. Original availability timestamps remain unknown. Of the 731 lookback days, 490 supplied daily dates precede the review, and 489 have reported under that assumption. The snapshot shows the reported rows and the remaining gap.

Future weather is a historical oracle fixture rather than an issued forecast. Historical heat periods are experimental derived indicators. Their following-night temperature pairing is separate from the model's native same-row weather features. Original reporting availability, weather vintages and query-construction parity remain unresolved for operational use. Strict and live modes therefore keep M5 and S1 unavailable.

The frozen synthetic evaluation supports exploratory integration, not real-world accuracy or a universally safer model. The release did not meet the 10% improvement target in both groups; novel high-uplift misses were worse for M5 than S1. This screen estimates electricity use and does not predict payment behaviour, attribute weather causality or make automatic hardship decisions.

The preloaded snapshot covers the reviewed Fitzroy cohort. Uploaded batches keep their existing validated calculation path and version; they do not inherit precomputed customer estimates from this snapshot.
