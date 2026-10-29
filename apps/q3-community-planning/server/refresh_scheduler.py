"""One-shot local-inbox refresh plus a configurable, non-activating check plan.

No API client, credential reads, background service, cron or automatic download.
An approved retrieval worker may deliver an already-downloaded pair and receipt.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import re
from climate_pack import decode_pair,issue_date,month_at,valid_hash,MAX_GRIB
from source_adapter import SourceError,require,parse,digest

def validate_config(config):
    require(type(config) is dict and config.get('schemaVersion')==1,'refresh_config_contract')
    require(type(config.get('scheduleEnabled')) is bool,'schedule_enablement_explicit')
    require(config.get('releaseDayUTC')==6,'reviewed_release_day_required')
    lag=config.get('releaseLagDays');require(lag is None or type(lag) is int and 0<=lag<=14,'invalid_release_lag')
    require(type(config.get('checkIntervalHours')) is int and 1<=config['checkIntervalHours']<=24,'invalid_check_interval')
    require(config.get('retrievalMode')=='existing_local_inbox_only','unapproved_retrieval_mode')
    return config

def check_plan(now,active_issue,config,last_checked_at=None):
    validate_config(config);active=issue_date(active_issue)
    require(isinstance(now,datetime) and now.tzinfo is not None,'timezone_aware_clock_required')
    now=now.astimezone(timezone.utc);issue=now.strftime('%Y-%m')
    result={'mode':'plan_only','scheduleActivated':False,'networkRequest':False,'issueMonth':issue,'keepActiveIssue':active_issue,'nextCheckAt':(now+timedelta(hours=config['checkIntervalHours'])).isoformat()}
    if not config['scheduleEnabled']:return {**result,'action':'schedule_disabled'}
    if config['releaseLagDays'] is None:return {**result,'action':'release_lag_configuration_required'}
    eligible=issue_date(issue).replace(day=6)+timedelta(days=config['releaseLagDays'])
    result['eligibleFromUTC']=eligible.isoformat()
    if now.date()<eligible:return {**result,'action':'wait_for_release_plus_lag'}
    if active>=issue_date(issue):return {**result,'action':'latest_issue_already_active'}
    if last_checked_at:
        try:checked=datetime.fromisoformat(last_checked_at)
        except (ValueError,TypeError):raise SourceError('invalid_last_checked_time') from None
        require(checked.tzinfo is not None and checked<=now,'invalid_last_checked_time')
        due=checked+timedelta(hours=config['checkIntervalHours'])
        if due>now:return {**result,'action':'wait_for_check_interval','nextCheckAt':due.isoformat()}
    return {**result,'action':'check_existing_local_inbox','validMonths':[month_at(issue,i) for i in range(6)]}

def read_inbox(manifest_path):
    """A manifest names two exact sibling files. Arbitrary paths are forbidden."""
    path=Path(manifest_path)
    require(not path.is_symlink(),'inbox_manifest_symlink')
    with path.open('rb') as stream:raw=stream.read(65537)
    require(len(raw)<=65536,'inbox_manifest_size')
    try:manifest=parse(raw.decode('utf-8'))
    except UnicodeError:raise SourceError('inbox_manifest_encoding') from None
    require(type(manifest) is dict and manifest.get('schemaVersion')==1 and manifest.get('centre')=='ECMWF' and manifest.get('system')=='51','inbox_model_contract')
    issue=manifest.get('issueMonth');issue_date(issue)
    try:
        entries=manifest.get('files');require(type(entries) is dict and set(entries)=={'mean','anomaly'},'both_sources_required')
        paths={}
        for key,item in entries.items():
            require(type(item) is dict and type(item.get('file')) is str and re.fullmatch(r'[A-Za-z0-9_-]+\.grib',item['file']) is not None and valid_hash(item.get('sha256')),'inbox_file_contract')
            candidate=path.parent/item['file']
            require(not candidate.is_symlink() and candidate.resolve().parent==path.parent.resolve(),'inbox_sibling_required')
            require(candidate.is_file() and 0<candidate.stat().st_size<=MAX_GRIB,'inbox_source_missing_or_size')
            paths[key]=candidate
        require(paths['mean']!=paths['anomaly'],'distinct_sources_required')
    except SourceError as error:
        error.issue_month=issue
        raise
    return manifest,paths,digest(raw)

def run_local_check(manifest_path,store,*,promote=False,expected_generation=None,decoder=decode_pair):
    """Validate existing local bytes. Promotion is explicit and compare-and-swap.

    No retry is attempted on errors or uncertain storage outcomes. Already active
    issues are skipped before GRIB decoding, avoiding duplicate source work.
    """
    packet=store.read();require(packet['data'] is not None,'current_source_unavailable')
    if expected_generation is not None:require(packet['generation']==expected_generation,'active_snapshot_changed_restage_required')
    issue=None
    try:
        manifest,paths,mhash=read_inbox(manifest_path);issue=manifest['issueMonth']
        if issue<=packet['data']['mean']['issueDate'][:7]:return {'action':'kept_latest_success','issueMonth':issue,'generation':packet['generation'],'decoded':False,'promoted':False}
        require(issue_date(issue)<=store.clock().date(),'candidate_issue_in_future')
        pair=decoder(paths['mean'],paths['anomaly'],issue,manifest['files']['mean']['sha256'],manifest['files']['anomaly']['sha256'])
        from climate_pack import validate_pair
        receipt=validate_pair(pair['mean'],pair['anomaly'])
        result={'action':'validated_local_pair','issueMonth':issue,'receipt':receipt,'inboxManifestSha256':mhash,'decoded':True,'promoted':False}
        if promote:
            new=store.promote_climate(pair,packet['generation'])
            result.update(action='promoted_local_pair',promoted=True,generation=new['generation'],previousGeneration=packet['generation'])
        return result
    except (OSError,ValueError,KeyError,TypeError) as error:
        # A validated manifest can attach its issue to an incomplete pair.
        issue=issue or getattr(error,'issue_month',None)
        code=str(error) if isinstance(error,SourceError) else 'local_source_io_error'
        if code=='active_snapshot_changed_restage_required':return {'action':'superseded_during_validation','promoted':False,'error':code}
        if isinstance(error,OSError):return {'action':'failed_last_good_retained','promoted':False,'issueMonth':issue,'error':code,'noticePersisted':False,'storageOutcome':'inspect_before_retry'}
        if promote and issue:
            notice='climate_source_incomplete' if code in {'both_sources_required','inbox_source_missing_or_size'} else 'climate_storage_failed' if isinstance(error,OSError) else 'climate_decode_failed' if code.startswith('grib_') or code.startswith('eccodes_') else 'climate_source_invalid'
            try:
                noted=store.record_climate_failure(issue,notice)
                if not noted.get('refreshFailureRecorded'):return {'action':'superseded_during_validation','promoted':False,'issueMonth':issue,'noticePersisted':False}
            except (OSError,ValueError):return {'action':'failed_last_good_retained','promoted':False,'issueMonth':issue,'error':code,'noticePersisted':False,'storageOutcome':'inspect_before_retry'}
        return {'action':'failed_last_good_retained','promoted':False,'issueMonth':issue,'error':code,'noticePersisted':bool(promote and issue)}
