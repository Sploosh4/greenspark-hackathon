"""One-shot refresh entry point; timer registration is separate and explicit."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from automatic_refresh import once,plan,timer_text
from source_adapter import SnapshotStore
from datetime import datetime,timezone

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--runtime-dir',type=Path,default=ROOT/'.runtime')
    p.add_argument('--plan-only',action='store_true')
    p.add_argument('--print-timer',action='store_true',help='Render matching timer text; does not install or activate it')
    args=p.parse_args()
    try:
        config=json.loads(args.config.read_text())
        if args.print_timer:
            print(timer_text(config),end='');return 0
        store=SnapshotStore(ROOT/'data/inputs',args.runtime_dir)
        if args.plan_only:result=plan(datetime.now(timezone.utc),store.read()['data']['mean']['issueDate'][:7],config)
        else:result=once(store,config,args.runtime_dir/'climate-refresh')
        print(json.dumps(result,indent=2));return int(result['action']=='failed_last_good_retained')
    except Exception:
        print(json.dumps({'action':'configuration_or_storage_failed','promoted':False,'detail':'Inspect local configuration and last-good state; credentials/errors omitted.'}));return 1
if __name__=='__main__':raise SystemExit(main())
