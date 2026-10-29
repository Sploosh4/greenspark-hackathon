# Q1 customer review prototype

This source combines the verified `q1-m1-291739b9a9cf2484` snapshot with the reviewed `d83e19778fc51ebd` Sign out patch. It supports synthetic account uploads, historical review, CSV/PDF exports and scheduled public-weather refreshes. The historical estimate uses `recent7-plus-past-heat-offset/v1`. No trained ML model or live heat classification has been promoted in this branch.

Set `Q1_SOURCE_DIR` to an authorised synthetic input pack containing `SCHEMAS-AND-COVERAGE.json`, its declared business files and `Fitzroy-Crossing-6765-HISTORICAL-INPUTS`. The default is `data/input-pack` inside this app. That pack is deliberately excluded from Git. Missing inputs produce an unavailable review rather than invented values. `Q1_SHARED_WEATHER_CACHE` can point to an existing public-weather cache; its default is `runtime/public-weather/shared-latest.json`.

For a local synthetic preview, use Python 3.13 with the PDF dependencies in `../../packaging/team-connect/requirements-q1.txt`, then run `python -B serve.py --port 8891 --weather-source cache`. The direct entry point binds to loopback and opens in preview mode. Explicit container authentication uses the reviewed read-only identity adapter; see the [authenticated-container instructions](../../packaging/team-connect/AUTHENTICATED-CONTAINERS.md). Private account stores, native service wrappers and account provisioning are excluded.

Authenticated users have a visible Sign out action. It revokes the server session, clears displayed/client-held data and returns to sign-in. Failed or unconfirmed requests keep protected content hidden and allow a retry. The patch also prevents delayed requests and browser back/forward restoration from redisplaying a closed session view.

Run the Python tests from this directory after setting `Q1_SOURCE_DIR` and running `python -B -m prototype.build`. That command creates an ignored derived report used by the snapshot's regression tests. Run `python -B -m unittest discover -s tests -p 'test_*.py'` and `node --test tests/*.test.mjs`. Canonical-port HTTP tests skip unless their opt-in is enabled; do not use an occupied live-service port for tests.

`assets/review-fixture.json` is an authored synthetic UI fixture retained for the JavaScript tests. Its example estimates are not evidence of prediction accuracy. The input pack, generated reports, exports, passwords and runtime data are absent from this publication.

See [publication scope](../../docs/team-connect/PUBLICATION.md), [source hashes](../../docs/team-connect/SOURCE-PROVENANCE.json), this app's [licence](LICENSE) and the retained [EHF method attribution](prototype/vendor/ehf/REUSE.md).
