"""Independent release hash and interval-to-browser reconciliation. Standard library only."""
import argparse,csv,gzip,hashlib,json
from pathlib import Path
from collections import defaultdict

def verify(source,prepared):
    data=json.loads(prepared.read_text());manifest=json.loads((source/'file_manifest.json').read_text())
    for name,record in manifest['files'].items():
        payload=(source/name).read_bytes()
        assert len(payload)==record['bytes'] and hashlib.sha256(payload).hexdigest()==record['sha256'],name
    totals=defaultdict(lambda:[0,0.0]);noon={};boundary_topups=defaultdict(int);intervals=0
    for r in csv.DictReader((source/'financial/data/prepaid_topups.csv').open()):
        if r['datetime'][11:19]=='12:00:00':boundary_topups[(r['customer_id'],r['datetime'][:10])]+=int(r['amount_cents'])
    with gzip.open(source/'financial/data/prepaid_intervals.csv.gz','rt') as f:
        for r in csv.DictReader(f):
            key=(r['customer_id'],r['date']);totals[key][0]+=int(r['charged_cents']);totals[key][1]+=float(r['delivered_kwh']);intervals+=1
            if r['interval_start'][11:19]=='11:30:00':noon[key]=int(r['closing_credit_cents'])+boundary_topups[key]
    for cid,rows in data['credit'].items():
        for day,balance in rows:assert noon[(cid,day)]==balance,(cid,day)
    for cid,rows in data['daily'].items():
        for r in rows:
            charge,kwh=totals[(cid,r['date'])]
            assert charge==int(r['usage_cost_cents']),(cid,r['date'])
            assert abs(kwh-float(r['import_kwh']))<.0006,(cid,r['date'])
    return {'result':'passed','release_hashes_verified':len(manifest['files']),'intervals_independently_aggregated':intervals,'credit_snapshots_reconciled':len(noon),'daily_charge_and_delivered_energy_rows_reconciled':len(totals)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('release',type=Path);p.add_argument('--prepared',type=Path,default=Path('teamconnect/scenario.json'));a=p.parse_args();print(json.dumps(verify(a.release,a.prepared),indent=2))
