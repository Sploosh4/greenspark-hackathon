# POA2021 boundary handoff · 27 October 2026

This branch prepares the boundary join without changing the application, customer-centred UI, map style, server allowlist or credentials. It starts from published `fix/community-map-placeholders` commit `9792da1b0a8092f0025dc4883403b48d837207ef`. Remote inspection found no newer heads: `demo` remained at `e3c95f2`, and `main` at `b391688`. Integration awaits the local Demo AI's branch and actual basemap configuration.

## Matching geography

The existing `teamconnect/scenario.json.context` contains 12 records labelled `context_geography: POA2021`, `census_reference_year: 2021`. The statistics field `POA_CODE_2021` stores values such as `POA6722`, while `postcode` stores `6722`.

The official [ABS ASGS2021 POA service](https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/POA/MapServer) exposes a generalised polygon layer, [POA_GEN / layer 1](https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/POA/MapServer/1). Its exact field name is **`poa_code_2021`**, a four-character string; the alias is `POA_CODE_2021`. The query requests GeoJSON with `outSR=4326` for longitude/latitude. Layer 0 is the full-detail polygon counterpart; layer 2 is points and must not be used as a boundary.

The join retains the four-digit code as text and removes only the explicit `POA` prefix from the statistics key. Year, geography and postcode must agree. It does not match by town name, nearest point, bounding box or customer coordinate. Current requested codes: **6450, 6701, 6707, 6714, 6718, 6721, 6722, 6725, 6728, 6743, 6765, 6770**.

ABS [defines Postal Areas](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/non-abs-structures/postal-areas) as statistical approximations of postcodes. They are not town, delivery, property or legal boundaries. The 2021 vintage matches the retained Census/SEIFA context; do not substitute 2026 geography because it is newer. Keep values at POA grain. Do not copy a POA statistic to SA1/SAL polygons or label a whole POA as a selected town's extent. Existing locality-level account aggregates remain separate unless independently aggregated at the same POA grain.

## Licensing and provenance

The official service declares **CC BY 4.0**. Retain this attribution when displaying the overlay: **Australian Bureau of Statistics, ASGS Edition 3, Postal Areas 2021. © Commonwealth of Australia. CC BY 4.0.** See [ABS copyright conditions](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer) and the [licence](https://creativecommons.org/licenses/by/4.0/). No logo, customer location, private record or third-party postcode product is included.

[poa2021-request.json](../teamconnect/geography/poa2021-request.json) records the exact service/query, 12 code pairs, data hashes, attribution and current blocker. **No official geometry was downloaded or committed.** Ordinary shell requests to `geo.abs.gov.au` received `Tunnel connection failed: 403 Forbidden`; an approved network-permission attempt received the same environment-proxy response. Public service documentation was inspectable through browsing. No proxy bypass or alternate host was used to retrieve geometry.

The local worker can fetch the exact public subset, then prepare it:

```sh
python3 scripts/prepare-poa2021-boundaries.py --download
```

Or supply an existing GeoJSON export from that exact service/query:

```sh
python3 scripts/prepare-poa2021-boundaries.py --source /path/to/official-poa2021-export.geojson
```

The importer requires complete, unique matches to all 12 supplied statistics codes. It retains Polygon/MultiPolygon coordinates, islands and holes, and rejects points, unclosed/degenerate/nonfinite geometry, projected coordinates, duplicates, missing codes, truncated collections and mismatched declared geography/year. It performs no clipping, simplification, synthetic polygon construction, subdivision or value allocation. Structural validation does not prove topology or authenticate a supplied file's origin. The operator must verify official acquisition; provided-file mode records that origin is not independently verified.

Successful preparation writes `teamconnect/geography/poa2021.geojson` and `poa2021.provenance.json`, including source/output/statistics hashes, acquisition mode, matched codes, CRS, attribution and transformations. Failed preparation writes no substitute geometry. No generated geometry file is present on this branch.

## Application integration, pending local source

[area-boundaries.mjs](../teamconnect/area-boundaries.mjs) exports `poa2021Code`, `findPoa2021Boundary` and `joinPoa2021Contexts`. The prepared collection must declare `geography: POA2021` and numeric `reference_year: 2021`. A missing, unmatched, wrong-year, wrong-grain, malformed or ambiguous match returns `null` (or is omitted from batch results). A successful join returns references to the original context and whole source feature without modifying either or inventing metrics.

The module is deliberately not imported by `app.mjs`, and the new files are not added to the loopback server's asset allowlist. The integration worker should add only the required assets to its existing server, load them in Community planning, use the selected **postcode context** for the exact join, preserve source attribution and the actual basemap, and omit the overlay if the join is unavailable. Do not add customer markers. Integrate against the published local Demo AI branch after inspecting its head; do not replace that UI with this branch's older `app.mjs`.

## Map configuration contract inspected

At source commit `9792da1`, `initMap` in `teamconnect/app.mjs` supplies a background-only style object. **There is no expected MapTiler environment variable or config file**: no loader reads one. An arbitrary variable would have no effect. `serve-demo.py` has a fixed asset allowlist and a `connect-src 'self'` CSP, so this published source also does not permit remote tile/style connections. These settings were not changed.

The known preview origin is **`http://127.0.0.1:8787`**, loopback only. No external/cloud preview origin was found. Ask the local Demo AI for its published branch/head, actual style/config loader file and variable names, preview origin and basemap QA evidence. Do not send the key itself, create a new key, change allowed origins, or silently relax CSP in this data branch.

## Verification

- `node --test test-*.mjs`: 68/68, including eight new geography-join checks and the 60 retained checks.
- `python3 test-poa2021-boundaries.py`: 7/7 importer tests.
- Module syntax, Python compilation and whitespace checks passed.
- Tests use explicitly temporary triangles; none is map data or a substitute boundary.
- Retained scenario payload and all existing UI/server files are unchanged from `9792da1`.
- Real-geometry preparation, source topology, live tile authentication and visual overlay QA remain unrun because boundary bytes and the local basemap source are unavailable. No merge, deployment or PR creation was attempted.
