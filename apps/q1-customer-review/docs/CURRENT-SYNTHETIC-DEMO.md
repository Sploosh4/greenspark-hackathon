# Current-date synthetic demo

Upload the twelve business CSV/CSV.GZ files. The app validates them and calculates a current scenario before asking you to replace the active uploaded batch. The preloaded historical replay remains separate.

The current scenario covers today through six days ahead: seven whole Perth calendar days, matching the existing frozen model. M5 estimates average grid imports in kWh/day. Its percentage change is `100 × (estimate / baseline − 1)`; total imports are the daily estimate times seven. S1 is the simple comparison. The generator does not upload model answers.

The app uses the unchanged frozen v3 features and model files. The baseline uses at least 14 ordinary days in the preceding 56 days, otherwise valid usage within 56 days, otherwise 90 days. Positive baseline use is required for percentages. Missing data remains missing and genuine zero stays numeric.

Seven complete reported daily usage records are required, ending one or two days before review. A two-day lag stays visible. For the 29 October 2026 pack, 21–27 October is complete and 28 October is absent. The frozen latest-calendar-week feature therefore has six usage days; no value is filled or moved. If yesterday is reported but interrupted or invalid, it cannot silently become a two-day reporting delay.

Actual completed upload receipt is when the records become known to this app. Original source availability remains unknown. Calculation time is separate from forecast retrieval, adapter load and unknown provider issuance. No original availability or forecast issue time is backdated.

Weather inputs are calendar-day extrema of modelled hourly Open-Meteo values at the returned grid. Past modelled weather stays modelled. The adapter uses the existing oracle-trained estimator lane without renaming the real source oracle weather. This is an unvalidated current-weather connection, not a new model, calibration exercise, accuracy result or official heatwave forecast. The fixed scenario is an ordinary query window; heatwave classification stays unavailable.

The table, detail, current-weather scenario panel, filtered CSV and selected PDF share one business/weather/calculation version. Source changes invalidate older exports. Successful daily weather refresh recalculates changed inputs and reuses identical inputs. Missing/stale weather, an incomplete reported week, usage more than two days old or failed inference gives a specific unavailable reason. Reload estimates can retry a failed calculation after a short backoff. Prior successful results and the historical replay are retained without relabelling them current.

Current mode defaults to all customers and estimates because it does not invent historical heat-linked comparisons. Historical replay keeps its existing filters. Account/payment/support facts are dated context for human review, not payment predictions or automatic hardship decisions.
