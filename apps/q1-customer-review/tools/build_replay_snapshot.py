"""Offline inference boundary using the already reviewed, pinned model stage.

No live service, uploads, model fitting or private evaluation inputs are touched.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from importlib.metadata import version

APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
from prototype.replay_snapshot import compose_review,seal,MODE,MODEL_MANIFEST_SHA256
from prototype.inputs import DEFAULT_SOURCE,load_business
from prototype.review import build_review,known_support_links
from prototype.weather import load_weather,derive
from prototype.exports import csv_bytes

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--numerical-stage',type=Path,required=True)
    parser.add_argument('--contract-stage',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--policy',choices=('event_local_B','common_review_B'),default='event_local_B')
    args=parser.parse_args()
    expected={'numpy':'2.3.5','scipy':'1.17.0','scikit-learn':'1.8.0','joblib':'1.5.3','threadpoolctl':'3.6.0'}
    if sys.version_info[:2]!=(3,12) or any(version(name)!=required for name,required in expected.items()):
        raise RuntimeError('Frozen inference requires the reviewed Python3.12/package runtime; no model was loaded')
    sys.path.insert(0,str(args.numerical_stage.resolve()));sys.path.insert(0,str(args.contract_stage.resolve()))
    from adapter import FrozenEngine,comparisons,clean
    from replay_contract import REVIEW,review_rows,recompute_past_heat
    files={str(p.relative_to(args.source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.source.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    tables,audit=load_business(args.source);weather,provenance=load_weather(DEFAULT_SOURCE)
    legacy=build_review(args.source,weather_root=DEFAULT_SOURCE)
    engine=FrozenEngine();past,geometry=recompute_past_heat(weather,provenance,review_as_of=REVIEW,derive=derive)
    query_fixtures={e['id']:{'event_id':e['id'],'classification':'explicit_query_mapping_fixture','window_kind':'hot_window','semantic_parity_verified':False,'rationale':'Explicit hypothetical historical query; not an issued forecast'} for e in legacy['events']}
    current,prepared=comparisons(engine,legacy['customers'],weather,legacy['events'],availability_mode='historical_replay_fixture',query_fixtures=query_fixtures)
    rows=review_rows(tables,weather,past,current,legacy,denominator_policy=args.policy,availability_mode=MODE,linker=known_support_links)
    review=compose_review(legacy,rows,model_manifest_sha256=MODEL_MANIFEST_SHA256,source_files=files,past_events=past,policy=args.policy)
    envelope=seal(clean(review));args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(envelope,allow_nan=False,separators=(',',':'))+'\n')
    expected={**review,'data_mode':'demo','batch_id':'preloaded','batch_revision':review['snapshot_id']}
    args.output.with_suffix('.csv').write_bytes(csv_bytes(expected,[r['customer_id'] for r in rows if r['qualifies']['M5']]))
    print(json.dumps({'snapshot_id':review['snapshot_id'],'review_sha256':envelope['review_sha256'],'customers':len(rows),'model_queries':len(prepared),'policy':args.policy,'source_files':len(files),'output_bytes':args.output.stat().st_size,'past_geometry':geometry},indent=2))

if __name__=='__main__':main()
