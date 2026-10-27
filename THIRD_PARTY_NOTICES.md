# Third-party notices

The repository's MIT licence covers its original code. The following bundled dependency and public statistical extracts retain their own licences and attribution.

## MapLibre GL JS 5.24.0

Copyright MapLibre contributors. The original licence notices, including notices for incorporated code, are retained in [`teamconnect/vendor/maplibre-LICENSE.txt`](teamconnect/vendor/maplibre-LICENSE.txt). MapLibre is distributed under the BSD 3-Clause licence; the retained file also records incorporated components.

Upstream: https://github.com/maplibre/maplibre-gl-js

The unmodified distribution files came from the `maplibre-gl@5.24.0` npm package via unpkg:

| File | SHA-256 |
| --- | --- |
| `maplibre-gl.js` | `45a9b07a9189ce56054c620a947ccf41e291e58c95e9b61533b740aaa65ee5cb` |
| `maplibre-gl.css` | `ab1e70d59ec40465bae7e7030da2f3ccf28133fd502e62bd598eefbadfd7a732` |
| `maplibre-LICENSE.txt` | `ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2` |

## Australian Bureau of Statistics area context

Source: Australian Bureau of Statistics, 2021 Census General Community Profile, Postal Areas, Western Australia; and Socio-Economic Indexes for Areas (SEIFA), Australia, 2021, Postal Area indexes. © Commonwealth of Australia. These public aggregate statistics are provided under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/), subject to the [ABS copyright notice and exceptions](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer).

Original sources:

- [2021 General Community Profile, WA Postal Areas](https://www.abs.gov.au/census/find-census-data/datapacks/download/2021_GCP_POA_for_WA_short-header.zip)
- [SEIFA 2021 Postal Area indexes](https://www.abs.gov.au/statistics/people/people-and-communities/socio-economic-indexes-areas-seifa-australia/2021/Postal%20Area%2C%20Indexes%2C%20SEIFA%202021.xlsx)

The supplied scenario release selects twelve postcode contexts and joins selected Census and SEIFA fields. The demo reuses that prepared join; values are displayed with their 2021 geography and reference year. These are area statistics, not individual customer attributes. No ABS logo, unit-record microdata or endorsement is included.

## Synthetic scenario

Customer, account, support workflow, fictional geometry and weather scenario records are from the supplied `complete-scenario-2025Q1-v1` demonstration release. They are synthetic examples, separate from the real ABS aggregate context above. No private design brief, extracted decision questions or source archive is included in this repository change.

## MapTiler basemap and logo

MapTiler Streets v4 and its sprites, glyphs and vector tiles are fetched at runtime using the user's existing MapTiler configuration, subject to the account and provider terms. The MapTiler logo (`teamconnect/vendor/maptiler-logo.svg`) is the unmodified attribution asset from https://api.maptiler.com/resources/logo.svg, linked to https://www.maptiler.com/ inside the map. Style/source attribution, including MapTiler and OpenStreetMap contributors, is retained. See the [MapTiler attribution guidance](https://docs.maptiler.com/guides/map-design/attribution/add-attribution/) and [copyright information](https://www.maptiler.com/copyright/).

The local compatibility adjustment filters the provider's Road shields layer to records with a non-empty route-reference length. Unnumbered road geometry and name labels remain; the adjustment prevents requesting a nonexistent empty shield sprite.

## Earlier ABS 2021 Suburbs and Localities reference geometry

Source: Australian Bureau of Statistics, ASGS Edition 3, Suburbs and Localities 2021, © Commonwealth of Australia, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), subject to [ABS copyright and exceptions](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer). The twelve selected WA areas are a GeoJSON extract from the [ABS SAL service](https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SAL/MapServer/0), transformed by the service to EPSG:4326 and rounded to six decimal places. Attribution, query source, acquisition time and snapshot hash are retained in `teamconnect/area-boundaries-source.json`.

These are genuine statistical-area approximations of localities, not legal locality boundaries or current warning areas. See the [ABS geographic definition](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/non-abs-structures/suburbs-and-localities). Landgate's differently licensed locality geometry is not bundled.

## ABS 2021 Postal Area geometry used by the meeting map

Australian Bureau of Statistics, ASGS Edition 3, Postal Areas 2021. © Commonwealth of Australia. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), subject to [ABS copyright conditions](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer). Source: [official ABS POA_GEN / layer 1](https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/POA/MapServer/1). These are statistical approximations of postcodes, not town or legal boundaries.

The cloud handoff's reviewed importer fetched the exact twelve four-digit postcode codes using `outSR=4326`. All selected Polygon/MultiPolygon coordinates, rings, islands and holes are retained without additional clipping, simplification, invented subdivision or statistic allocation. Its output and acquisition provenance are `teamconnect/geography/poa2021.geojson` and `poa2021.provenance.json`. The current map joins these to POA2021 statistics by exact code, geography and year; SAL geometry is not used for this layer.
