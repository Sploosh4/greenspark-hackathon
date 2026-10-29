# Season Ahead planning prototype

This application comes from verified source `209bce1ae503d91adaf03a17a1034a6bd72c92e05526cbc82357a8cd86935567`. It provides a local climate map, synthetic business uploads, financial intake, and explicit replacement of validated data. Acknowledging an upload does not activate it.

Run `python -B run.py` from this directory for a loopback preview at `http://127.0.0.1:8797/`. The bundled JSON is a small, dated public climate/context pack with historical synthetic account aggregates. Its provenance and original limits remain in [data/PROVENANCE.md](data/PROVENANCE.md). It does not represent the laptop's active 50,000-account cohort. MapLibre and its licence are retained. An optional MapTiler key file can be passed with `--maptiler-env`; the default is the ignored `.runtime/maptiler.env`. The local boundary remains usable without that provider key.

The 48 large SILO history PNG/gzip layers are distributed separately and are absent here. Their metadata retains the source hashes and dates; the application reports history unavailable until matching assets are supplied in `data/history`. No raw business data, live saved snapshot, CDS credentials or private account store is included.

The direct server defaults to preview mode. Explicit container authentication uses separate read-only identity volumes and session-only cookies; see the [authenticated-container instructions](../../packaging/team-connect/AUTHENTICATED-CONTAINERS.md). Private account stores, native service wrappers and account provisioning are excluded. This remains a local prototype; no container deployment was performed for this publication package. Automatic refresh examples default to disabled; no service or timer is installed by running the application.

Run `python -B -m unittest discover -s tests -p 'test_*.py'` and `node --test tests/*.test.mjs` from this directory. `test_history_archive.py` requires the separately supplied matching history layers. The retained financial test fixture contains synthetic aggregate data and no account records. Optional real-GRIB checks also require their decoder dependencies and compatible public inputs.

The repository [licence](../../LICENSE) covers the application code. Third-party code/data retain their own credits and terms. See [publication scope](../../docs/team-connect/PUBLICATION.md) and [source hashes](../../docs/team-connect/SOURCE-PROVENANCE.json).
