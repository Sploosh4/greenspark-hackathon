"""Prepare pinned aggregate evidence from the already reviewed synthetic release."""
import argparse,json,sys,re
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'server'))
from source_adapter import canonical,digest,require
from business_upload import derive_business,load_trusted_context
from financial_support import derive_support_context,HEADERS

PINNED={'statewide-1000':'e5b681f61a2036d3efe004222c274fc914c0da5feee5036944de0fd4726d3374','statewide-10000':'dd1e06d2d48b47cfe010c32d6f138a7ff23c3d64b839898daa2829794d44b03e','statewide-50000':'ad563b96dc8b085019b58b64189dbe42b3d4dbf854d36f13f77218e0ae940a29'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fixtures-root',type=Path,required=True);args=parser.parse_args()
    trusted=load_trusted_context(ROOT/'data/inputs');require(trusted is not None,'trusted_upload_context_unavailable');entries={}
    for name,expected in PINNED.items():
        root=args.fixtures_root/name;manifest=(root/'manifest.json').read_bytes();require(digest(manifest)==expected,'reviewed_release_manifest_changed')
        c=(root/'customers.csv').read_bytes();u=(root/'consumption_daily.csv.gz').read_bytes();sidecars={n:(root/n).read_bytes() for n in HEADERS}
        business,_=derive_business(c,u,True,trusted,date(2026,10,28));support=derive_support_context(c,u,True,trusted,date(2026,10,28),business,sidecars,manifest,expected)
        source=json.loads(manifest);require(source['parameters']['start']==support['historyStart'] and source['parameters']['end']==support['historyEnd'] and source['parameters']['count']==business['retainedTotalAccounts'],'financial_reviewed_window')
        entries[expected]={'fixture':name,'customerSourceSha256':digest(c),'usageSourceSha256':digest(u),'snapshotDate':business['snapshotDate'],'historyStart':business['historyStart'],'historyEnd':business['historyEnd'],'geographyRegistrySha256':business['geographyRegistrySha256'],'accountPostcodes':support['coverage']['accountPostcodes'],'retainedAccounts':business['retainedTotalAccounts'],'activeAccounts':business['totalAccounts'],'aggregateSha256':digest(canonical(support)),'sourceHashes':support['sourceHashes'],'classification':'Reviewed complete synthetic support tables, not real customer records or assistance policy'}
    registry={'schemaVersion':1,'contract':'q3-financial-support-v2','classification':'Pinned synthetic demonstration coverage; exact source/aggregate hashes, not new client-supplied authority','fixtures':entries}
    raw=canonical(registry);output=ROOT/'data/financial/registry.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(raw)
    module=ROOT/'server/financial_reference.py';module.write_text(re.sub(r"REGISTRY_SHA='[^']*'", "REGISTRY_SHA='"+digest(raw)+"'",module.read_text()))
    print(json.dumps({'registrySha256':digest(raw),'fixtures':{v['fixture']:{'active':v['activeAccounts'],'areas':len(v['accountPostcodes']),'aggregateSha256':v['aggregateSha256']} for v in entries.values()}}))
if __name__=='__main__':main()
