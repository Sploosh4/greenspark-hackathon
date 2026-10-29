"""Explicit synthetic upload QA subsets; original source files are read only."""
from pathlib import Path
from io import StringIO
import csv,gzip,json
from prototype.inputs import DEFAULT_SOURCE

def encode_rows(name,headers,rows):
    stream=StringIO(newline='');w=csv.DictWriter(stream,fieldnames=headers,lineterminator='\n');w.writeheader();w.writerows(rows)
    raw=stream.getvalue().encode()
    return gzip.compress(raw,mtime=0) if name.endswith('.gz') else raw

def fixture_parts(ids=('C103794',),increase_last_day=False):
    audit=json.loads((DEFAULT_SOURCE/'SCHEMAS-AND-COVERAGE.json').read_text());result=[]
    for spec in audit['files']:
        path=DEFAULT_SOURCE/spec['file'];name=path.name;op=gzip.open if name.endswith('.gz') else open
        with op(path,'rt',newline='') as f:rows=[dict(r) for r in csv.DictReader(f) if r['customer_id'] in ids]
        if increase_last_day and name=='consumption_daily.csv.gz':
            for r in rows:
                if r['customer_id']=='C103794' and r['date']=='2024-11-01':
                    r['import_kwh']=str(float(r['import_kwh'])+7);r['import_peak_kwh']=str(float(r['import_peak_kwh'])+7)
        result.append((name,encode_rows(name,spec['headers'],rows)))
    return result

def mutate(parts,name,change):
    out=list(parts);i=next(i for i,(n,_) in enumerate(out) if n==name);raw=out[i][1]
    if name.endswith('.gz'):raw=gzip.decompress(raw)
    reader=csv.DictReader(StringIO(raw.decode()));headers=reader.fieldnames;rows=list(reader);change(headers,rows)
    out[i]=(name,encode_rows(name,headers,rows));return out

if __name__=='__main__':
    root=Path(__file__).resolve().parent/'upload-fixtures'
    for label,parts in [('valid-A',fixture_parts()),('valid-B',fixture_parts(('C103794','C105072'),True))]:
        folder=root/label;folder.mkdir(parents=True,exist_ok=True)
        for name,raw in parts:(folder/name).write_bytes(raw)
    (root/'PROVENANCE.txt').write_text('Synthetic QA subsets of the unchanged candidate business data. A selects C103794. B selects C103794/C105072 and explicitly adds 7 kWh to C103794 on 2024-11-01 (import and peak component). Fixed historical weather, review date and predictor are unchanged. These are test fixtures, not original business uploads.\n')
    print(root)
