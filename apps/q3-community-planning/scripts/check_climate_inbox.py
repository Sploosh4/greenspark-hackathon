"""Offline local-inbox check. No scheduler registration, download or credentials."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from source_adapter import SnapshotStore,SourceError
from refresh_scheduler import run_local_check,check_plan
from datetime import datetime,timezone

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs-dir',type=Path,default=ROOT/'data/inputs')
    p.add_argument('--runtime-dir',type=Path,default=ROOT/'.runtime')
    p.add_argument('--manifest',type=Path)
    p.add_argument('--plan-config',type=Path)
    p.add_argument('--promote',action='store_true',help='Explicit atomic local cache replacement; never activates a schedule')
    p.add_argument('--expected-generation')
    args=p.parse_args();store=SnapshotStore(args.inputs_dir,args.runtime_dir)
    try:
        if args.plan_config:
            if args.promote or args.manifest:p.error('Plan and local promotion are separate operations')
            issue=store.read()['data']['mean']['issueDate'][:7]
            result=check_plan(datetime.now(timezone.utc),issue,json.loads(args.plan_config.read_text()))
        else:
            if not args.manifest:p.error('--manifest or --plan-config is required')
            if args.promote and not args.expected_generation:p.error('Promotion requires the reviewed current --expected-generation')
            result=run_local_check(args.manifest,store,promote=args.promote,expected_generation=args.expected_generation)
        print(json.dumps(result,indent=2));return int(result['action'].startswith('failed'))
    except (OSError,ValueError,KeyError,TypeError):
        print(json.dumps({'action':'check_failed','detail':'Local source/configuration invalid; inspect before retry. No download or schedule was created.'}));return 1
if __name__=='__main__':raise SystemExit(main())
