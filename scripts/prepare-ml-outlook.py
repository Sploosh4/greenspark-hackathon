"""Copy the Q3 ML outlook export into teamconnect/ml-outlook/ and record provenance with SHA-256 hashes.

    python3 scripts/prepare-ml-outlook.py q3-seasonal-ml/outputs
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / 'teamconnect' / 'ml-outlook'
FILES = ('ml_outlook_layer.json', 'wa_outline.geojson')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path, help='q3-seasonal-ml/outputs directory')
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(args.source / name, DEST / name)
    layer = json.loads((DEST / 'ml_outlook_layer.json').read_text(encoding='utf-8'))
    provenance = {
        'product': 'Experimental ML seasonal temperature outlook (monthly mean, 1-degree WA cells)',
        'status': 'Research prototype. Not a Copernicus C3S or Bureau of Meteorology product. Monthly means only; no heatwave counts or dates.',
        'issues': [i['label'] for i in layer['issues']],
        'training_through': layer['meta']['training_through'],
        'model': layer['meta']['model'],
        'inputs': ['NASA POWER (MERRA-2) T2M monthly 1981-2026 and daily Oct 2026, NASA Langley Research Center POWER Project',
                   'NOAA CPC Nino 3.4 (ERSSTv5) and Antarctic Oscillation monthly indices',
                   'Natural Earth 1:50m admin-1 outline (public domain)'],
        'evaluation': 'Rolling-origin hindcast 2006-2025; see q3-seasonal-ml/REPORT.md in this repository',
        'relationship_to_demo_scenario': 'Independent of the synthetic 2025 Q1 account scenario and its As-of date.',
        'files': {name: hashlib.sha256((DEST / name).read_bytes()).hexdigest() for name in FILES},
    }
    (DEST / 'provenance.json').write_text(json.dumps(provenance, indent=1), encoding='utf-8')
    print(f"{len(layer['cells'])} cells, issues {provenance['issues']}")


if __name__ == '__main__':
    main()
