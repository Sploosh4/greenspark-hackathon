"""Fetch the inputs for the WA seasonal temperature model.

Sources (all public, no key):
  - NASA POWER (MERRA-2) monthly 2 m air temperature, 1981-present, one point per 1-degree cell centre.
  - NASA POWER daily T2M for the current, incomplete month.
  - NOAA CPC Nino 3.4 (ERSSTv5, sstoi.indices) and SAM/AAO monthly indices.
  - Natural Earth 1:50m admin-1 boundaries, used only to choose which 1-degree cells touch WA.

Every response is cached under data/raw so reruns are offline and reproducible.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from matplotlib.path import Path as PolyPath

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
POWER_MONTHLY = "https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M&community=AG&longitude={lon}&latitude={lat}&start=1981&end=2026&format=JSON"
POWER_DAILY = "https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M&community=AG&longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON"
NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_1_states_provinces.geojson"
INDEX_URLS = {
    "sstoi.indices": "https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices",
    "aao.ascii": "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/daily_ao_index/aao/monthly.aao.index.b79.current.ascii",
}


def download(url, dest, retries=4):
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                body = r.read()
            dest.write_bytes(body)
            return body
        except Exception as e:  # network hiccups and POWER 429s
            if attempt == retries - 1:
                raise RuntimeError(f"{url}: {e}") from e
            time.sleep(5 * (attempt + 1))


def wa_polygons():
    gj = json.loads(download(NE_URL, RAW / "naturalearth" / "ne_50m_admin_1.geojson"))
    feat = next(f for f in gj["features"]
                if f["properties"].get("name") == "Western Australia" and f["properties"].get("admin") == "Australia")
    geom = feat["geometry"]
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [PolyPath(np.asarray(p[0])) for p in polys]


def wa_cells():
    """1-degree cells (centres at x.5) with any part of WA inside them, sampled on a 6x6 sub-grid."""
    polys = wa_polygons()
    offs = (np.arange(6) + 0.5) / 6 - 0.5
    cells = []
    for lat in np.arange(-35.5, -13.0, 1.0):
        for lon in np.arange(112.5, 129.0, 1.0):
            pts = np.array([(lon + dx, lat + dy) for dx in offs for dy in offs])
            frac = max(p.contains_points(pts).mean() for p in polys)
            if frac > 0:
                cells.append({"cell": f"{lat:+.1f}_{lon:.1f}", "lat": float(lat), "lon": float(lon), "land_frac": round(float(frac), 3)})
    return cells


def fetch_cell(c):
    lat, lon = c["lat"], c["lon"]
    m = json.loads(download(POWER_MONTHLY.format(lat=lat, lon=lon), RAW / "power_monthly" / f"{c['cell']}.json"))
    d = json.loads(download(POWER_DAILY.format(lat=lat, lon=lon, start="20261001", end="20261031"),
                            RAW / "power_daily_202610" / f"{c['cell']}.json"))
    c["elevation"] = m["geometry"]["coordinates"][2]
    return c, m, d


def main():
    cells = wa_cells()
    print(f"{len(cells)} WA cells")
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(fetch_cell, cells))
    for name, url in INDEX_URLS.items():
        download(url, RAW / "indices" / name)
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "cells.json").write_text(json.dumps([r[0] for r in results], indent=1))
    print("done")


if __name__ == "__main__":
    main()
