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
