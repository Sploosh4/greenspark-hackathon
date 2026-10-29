"""Bounded one-shot CDS refresh. Registration/enablement is a separate action.

No implicit resubmission after uncertain/failed jobs; no credential persistence.
Only the two reviewed ECMWF51 monthly products and fixed WA box are requested.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import fcntl,json,logging,os,re,stat,tempfile
from climate_pack import issue_date,month_at,MAX_GRIB
from refresh_scheduler import run_local_check
from source_adapter import require,digest,SourceError

ENDPOINT='https://cds.climate.copernicus.eu/api'
PRODUCTS={'mean':('seasonal-monthly-single-levels','2m_temperature'),'anomaly':('seasonal-postprocessed-single-levels','2m_temperature_anomaly')}

def scheduled_at_or_after(instant,config):
    interval=config['checkIntervalHours'];hour=config.get('checkHourUTC',12)
    for day in [0,1]:
        midnight=instant.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=day)
        for h in range(24):
            slot=midnight+timedelta(hours=h)
            if (h-hour)%interval==0 and slot>=instant:return slot
    raise SourceError('invalid_schedule')

def timer_text(config):
    # The saved timer must be regenerated from the same reviewed configuration.
    plan(datetime(2026,1,1,tzinfo=timezone.utc),'2026-01',config)
    hours=','.join(f'{h:02d}' for h in range(24) if (h-config.get('checkHourUTC',12))%config['checkIntervalHours']==0)
    return '[Unit]\nDescription=Check Season Ahead climate availability\n\n[Timer]\nOnCalendar=*-*-* '+hours+':00:00 UTC\nPersistent=true\nUnit=season-ahead-climate-update.service\n\n[Install]\nWantedBy=timers.target\n'

def plan(now,active,config):
    require(type(config) is dict and config.get('schemaVersion')==1,'auto_config')
    require(type(config.get('enabled')) is bool,'auto_enablement_explicit')
    lag=config.get('releaseLagDays');interval=config.get('checkIntervalHours')
    require(type(lag) is int and 0<=lag<=14 and type(interval) is int and interval in {1,2,3,4,6,8,12,24},'auto_schedule_bounds')
    require(type(config.get('checkHourUTC',12)) is int and 0<=config.get('checkHourUTC',12)<=23,'auto_schedule_hour')
    require(config.get('releaseDayUTC')==6,'reviewed_release_day_required')
    require(isinstance(now,datetime) and now.tzinfo is not None,'timezone_aware_clock_required')
    now=now.astimezone(timezone.utc);issue=now.strftime('%Y-%m');issue_date(active)
    eligible=datetime.fromisoformat(issue+'-06T00:00:00+00:00')+timedelta(days=lag)
    next_check=now+timedelta(hours=interval)
    action='check_cds' if now>=eligible and active<issue else 'wait_for_release_plus_lag'
    if active>=issue:
        action='latest_issue_already_active'
        next_check=datetime.fromisoformat(month_at(issue,1)+'-06T00:00:00+00:00')+timedelta(days=lag)
    elif now<eligible:next_check=eligible
    if not config['enabled']:action='disabled'
    return {'action':action,'issueMonth':issue,'activeIssue':active,'eligibleFromUTC':eligible.isoformat(),'nextEligibleCheckAt':scheduled_at_or_after(next_check,config).isoformat(),'scheduleState':'not_inspected'}

def request(kind,issue):
    require(kind in PRODUCTS,'source_kind');issue_date(issue)
    return {'originating_centre':'ecmwf','system':'51','variable':[PRODUCTS[kind][1]],'product_type':['ensemble_mean'],'year':[issue[:4]],'month':[issue[5:]],'leadtime_month':[str(i) for i in range(1,7)],'data_format':'grib','area':[-13,112,-36,130]}

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(prefix='.refresh-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)

def official_client():
    """Read only the already-approved native credential; never log/copy it."""
    path=(Path.home()/'.cdsapirc');info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600,'existing_private_credential_required')
    config={k.strip():v.strip() for k,v in (line.split(':',1) for line in path.read_text().splitlines() if ':' in line)}
    require(config.get('url')==ENDPOINT and bool(config.get('key')),'existing_credential_endpoint')
    from ecmwf.datastores import Client
    logging.disable(logging.CRITICAL)
    return Client(url=ENDPOINT,key=config['key'],maximum_tries=1,timeout=30,progress=False,log_callback=lambda *args,**kwargs:None)

def once(store,config,state_dir,*,now=None,client_factory=official_client,local_check=run_local_check):
    now=now or datetime.now(timezone.utc);packet=store.read()
    require(packet['data'] is not None,'current_source_unavailable')
    result=plan(now,packet['data']['mean']['issueDate'][:7],config)
    # This branch precedes both directory creation and credential/client access.
    if result['action']!='check_cds':return {**result,'networkRequest':False,'promoted':False}
    root=Path(state_dir);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/'.refresh.lock').open('a+b') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {**result,'action':'already_running','networkRequest':False,'promoted':False}
        last=root/'last-check.json'
        if last.exists():
            previous=json.loads(last.read_text());checked=datetime.fromisoformat(previous['checkedAt'])
            require(checked.tzinfo is not None and checked<=now,'invalid_last_check_time')
            due=checked+timedelta(hours=config['checkIntervalHours'])
            if due>now:return {**result,'action':'wait_for_check_interval','nextEligibleCheckAt':scheduled_at_or_after(due,config).isoformat(),'networkRequest':False,'promoted':False}
        issue=result['issueMonth'];folder=root/issue;folder.mkdir(exist_ok=True,mode=0o700)
        state_path=folder/'jobs.json'
        state=json.loads(state_path.read_text()) if state_path.exists() else {'issueMonth':issue,'jobs':{}}
        require(state.get('issueMonth')==issue and type(state.get('jobs')) is dict,'refresh_state_invalid')
        result={**result,'networkRequest':False,'promoted':False}
        try:
            client=None;entries={}
            for kind,(dataset,_) in PRODUCTS.items():
                spec=request(kind,issue);entry=state['jobs'].get(kind)
                if entry:
                    require(entry.get('requestSha256')==digest(json.dumps(spec,sort_keys=True).encode()),'cached_request_mismatch')
                    require(entry.get('phase') not in {'submitting','failed'},'submission_outcome_requires_reconciliation')
                target=folder/(kind+'.grib')
                if entry and entry.get('phase')=='downloaded':
                    with target.open('rb') as f:raw=f.read(MAX_GRIB+1)
                    require(0<len(raw)<=MAX_GRIB and digest(raw)==entry.get('sha256'),'cached_download_invalid')
                else:
                    if client is None:client=client_factory()
                    result['networkRequest']=True
                    if entry is None:
                        # A failed availability check creates no job; retry on a later check.
                        client.apply_constraints(dataset,spec)
                        entry={'requestSha256':digest(json.dumps(spec,sort_keys=True).encode()),'phase':'submitting'}
                        state['jobs'][kind]=entry;atomic_json(state_path,state)
                        remote=client.submit(dataset,spec)
                        require(type(remote.request_id) is str and re.fullmatch(r'[A-Za-z0-9-]{1,128}',remote.request_id),'remote_job_id')
                        entry.update(requestId=remote.request_id,phase='submitted');atomic_json(state_path,state)
                    else:remote=client.get_remote(entry['requestId'])
                    status=remote.json.get('status')
                    if status in {'failed','dismissed'}:
                        entry['phase']='failed';atomic_json(state_path,state);raise SourceError('remote_job_requires_reconciliation')
                    if status!='successful':
                        store.record_climate_failure(issue,'climate_source_incomplete')
                        result.update(action='waiting_for_existing_job',source=kind)
                        atomic_json(root/'last-check.json',{**result,'checkedAt':now.isoformat()})
                        return result
                    partial=folder/(kind+'.part')
                    require(not partial.exists() and not target.exists(),'existing_download_requires_reconciliation')
                    remote.download(str(partial))
                    with partial.open('rb') as f:raw=f.read(MAX_GRIB+1)
                    require(0<len(raw)<=MAX_GRIB and raw.startswith(b'GRIB') and raw.endswith(b'7777'),'download_size_or_framing')
                    os.replace(partial,target);entry.update(phase='downloaded',sha256=digest(raw));atomic_json(state_path,state)
                entries[kind]={'file':target.name,'sha256':entry['sha256']}
            manifest=folder/'manifest.json'
            atomic_json(manifest,{'schemaVersion':1,'centre':'ECMWF','system':'51','issueMonth':issue,'files':entries})
            # Take a fresh generation after network waits: business uploads may have finished.
            current=store.read()
            outcome=local_check(manifest,store,promote=True,expected_generation=current['generation'])
            result.update(outcome)
            fresh=plan(now,store.read()['data']['mean']['issueDate'][:7],config)
            result.update(activeIssue=fresh['activeIssue'],nextEligibleCheckAt=fresh['nextEligibleCheckAt'])
            atomic_json(root/'last-check.json',{**result,'checkedAt':now.isoformat()})
            return result
        except Exception as error:
            # Error text, headers, client repr and signed URLs must never be persisted.
            code=str(error) if isinstance(error,SourceError) else 'cds_request_or_storage_failed'
            try:store.record_climate_failure(issue,'climate_source_incomplete')
            except Exception:pass
            result.update(action='failed_last_good_retained',error=code)
            atomic_json(root/'last-check.json',{**result,'checkedAt':now.isoformat()})
            return result
