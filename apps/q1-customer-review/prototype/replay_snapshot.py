"""Sealed synthetic replay view shared by review, detail and server exports.

Inference runs offline in the pinned model environment. This module uses only
the standard library and never loads pickle/joblib, trains, or fetches sources.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import math
from pathlib import Path

SCHEMA='q1-synthetic-replay-snapshot/v1'
MODE='simulated_historical_replay'
POLICIES=('event_local_B','common_review_B')
MAX_BYTES=16*1024*1024
MODEL_MANIFEST_SHA256='c4a09dadf6544992d0c931a11e86e662aa3d2106d513c2165701c08c72e72db7'

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def close(a,b):return math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-10)
def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)

def compose_review(legacy,rows,*,model_manifest_sha256,source_files,past_events,policy='event_local_B'):
    if policy not in POLICIES:raise ValueError('Unknown replay percentage policy')
    result=deepcopy(legacy);mapping={r['customer_id']:r for r in rows}
    if len(mapping)!=len(rows) or set(mapping)!={r['customer']['customer_id'] for r in result['customers']}:raise ValueError('Replay customer mapping differs')
    for row in result['customers']:
        raw=mapping[row['customer']['customer_id']]
        if raw['denominator_policy']!=policy:raise ValueError('Mixed replay policies')
        row['legacy_predictions']=row['predictions'];row['predictions']=[]
        row['usage']=[r for r in row['usage'] if r['date']<='2024-10-31']
        row['financial']=[r for r in row['financial'] if r['date']<='2024-10-31']
        row['records']=[r for r in row['records'] if r['date']<='2024-10-31']
        coverage=row['history_coverage'];coverage['available_days']=len(row['usage']);coverage['missing_days']=coverage['expected_days']-len(row['usage']);coverage['status']='complete' if not coverage['missing_days'] else 'partial'
        for event in raw['events']:
            m5,s1=event['M5'],event['S1'];b=raw['current_baseline']
            row['predictions'].append({'event_id':event['event_id'],'duration':event['duration'],'baseline':b['value'],'baseline_n':b['n'],'baseline_method':b['method'],'predicted':m5['predicted'],'increase':m5['increase'],'event_total':m5['event_total'],'reason':m5['reason'],'method_id':'frozen-v3-M5-simulated-replay','comparison':{'provider':'S1',**deepcopy(s1)},'source_event':deepcopy(event)})
        row['episodes']=[{'id':e['event_id'],'start':e['start'],'end':e['end'],'label':' / '.join(dict.fromkeys(link['label'] for link in e['source_links'])),'linked':True,'increase_percent':e['increase_percent'],'actual_mean':e['actual_mean'],'denominator':e['denominator'],'event_local_baseline':deepcopy(e['event_local_baseline']),'baseline_support':{'n':(e['event_local_baseline'] if policy=='event_local_B' else raw['current_baseline'])['n'],'method':(e['event_local_baseline'] if policy=='event_local_B' else raw['current_baseline'])['method']},'source_links':deepcopy(e['source_links']),'reason':e['reason'],'calculation':{'observed_event_daily_mean':e['actual_mean'],'baseline':e['denominator'],'used':deepcopy(e['actual_inputs'])}} for e in raw['past_episodes']]
        row['replay_evidence']=deepcopy(raw)
    # Geometry comes from the availability-filtered replay, not legacy's tail.
    result['past_events']=deepcopy(past_events)
    result['weather']=[r for r in result['weather'] if r['date']<='2024-10-31' or r['date']>='2024-11-02']
    result['method']={'id':'frozen-v3-M5-simulated-replay','name':'Frozen v3 M5 with S1 comparison','denominator_policy':policy}
    result['replay']={'mode':MODE,'synthetic_business':True,'original_available_at':None,'review_as_of':'2024-11-02T03:00:00+08:00','denominator_policy':policy,'policy_status':'provisional_project_mapping_not_explicit_user_technical_selection','model_manifest_sha256':model_manifest_sha256,'selected_provider':'M5','comparison_provider':'S1','availability_rule':'separate-next-day-noon-reporting-assumption/v1','latest_reported_daily_date':'2024-10-31','future_weather':'historical_oracle_fixture_not_issued_forecast','strict_live_estimates':'unavailable','source_files_sha256':source_files}
    result['provenance']['estimates']='Frozen M5/S1 on synthetic accounts with simulated reporting and historical oracle weather; exploratory replay'
    result['provenance']['baseline']='Frozen v3 baseline rule; historical event-local B by default; original available_at unknown'
    result['status'].update(current_live_status='unavailable',current_weather_forecast=False,prediction_accuracy_validated=False)
    # Input, model, policy and every view value contribute to one immutable ID.
    version=digest(result);result['snapshot_id']='replay-'+version
    return result

def validate_review(review):
    meta=review['replay']
    if meta['mode']!=MODE or meta['original_available_at'] is not None or meta['denominator_policy'] not in POLICIES or meta['review_as_of']!='2024-11-02T03:00:00+08:00':raise ValueError('Invalid synthetic replay contract')
    if review['review_date']!='2024-11-02' or not meta['synthetic_business']:raise ValueError('Only fixed synthetic replay is supported')
    if meta['model_manifest_sha256']!=MODEL_MANIFEST_SHA256:raise ValueError('Unrecognised replay model manifest')
    if 'snapshot_id' in review and review['snapshot_id']!='replay-'+digest({k:v for k,v in review.items() if k!='snapshot_id'}):raise ValueError('Replay identity mismatch')
    customers=set();events={e['id']:e for e in review['events']}
    for row in review['customers']:
        cid=row['customer']['customer_id']
        if cid in customers:raise ValueError('Duplicate replay customer')
        customers.add(cid);seen=set()
        for p in row['predictions']:
            if p['event_id'] in seen or p['event_id'] not in events:raise ValueError('Invalid replay event mapping')
            seen.add(p['event_id']);event=events[p['event_id']]
            duration=(date.fromisoformat(event['end'])-date.fromisoformat(event['start'])).days+1
            if p['duration']!=duration:raise ValueError('Replay event duration mismatch')
            if set(row['replay_evidence']['source_availability'])!={'original_available_at','simulated_review_as_of','rule'}:raise ValueError('Availability provenance missing')
            for estimate in (p,p['comparison']):
                value,change=estimate['predicted'],estimate['increase'];b=p['baseline']
                if value is not None and (not finite(value) or value<0):raise ValueError('Invalid replay prediction')
                expected=None if value is None or b is None or b<=0 else 100*(value/b-1)
                if (change is None)!=(expected is None) or expected is not None and not close(change,expected):raise ValueError('Replay percentage mismatch')
                total=estimate['event_total']
                if (total is None)!=(value is None) or value is not None and not close(total,value*duration):raise ValueError('Replay total mismatch')
        if seen!=set(events):raise ValueError('Missing replay event estimate')
        for e in row['episodes']:
            mean,b,change=e['actual_mean'],e['denominator'],e['increase_percent']
            expected=None if mean is None or b is None or b<=0 else 100*(mean/b-1)
            if (change is None)!=(expected is None) or expected is not None and not close(change,expected):raise ValueError('Past replay percentage mismatch')
            if mean is not None:
                used=e['calculation']['used'];count=(date.fromisoformat(e['end'])-date.fromisoformat(e['start'])).days+1
                if len(used)!=count or not close(sum(r['import_kwh'] for r in used)/count,mean):raise ValueError('Past whole-event mean mismatch')
    return review

def seal(review):
    validate_review(review)
    return {'schema':SCHEMA,'review_sha256':digest(review),'review':review}

def load_snapshot(path,*,source_root,availability_mode='strict'):
    if availability_mode not in (MODE,'strict','live'):raise ValueError('Unknown replay availability mode')
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise ValueError('Replay snapshot exceeds16MiB')
    envelope=json.loads(path.read_bytes())
    if envelope.get('schema')!=SCHEMA or digest(envelope['review'])!=envelope.get('review_sha256'):raise ValueError('Replay snapshot integrity mismatch')
    review=validate_review(envelope['review']);meta=review['replay']
    for name,expected in meta['source_files_sha256'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe replay source path')
        if hashlib.sha256((Path(source_root)/relative).read_bytes()).hexdigest()!=expected:raise ValueError('Replay inputs changed; rebuild snapshot')
    if availability_mode!=MODE:
        for row in review['customers']:
            for p in row['predictions']:
                for estimate in (p,p['comparison']):
                    estimate.update(predicted=None,increase=None,event_total=None,reason='original_availability_and_issued_weather_unverified')
                p.pop('source_event',None)
            row['replay_evidence'].update(events=[],qualifies={'M5':None,'S1':None},highest_increase={'M5':None,'S1':None})
        review['replay']={**meta,'mode':availability_mode,'retained_context':MODE}
        review['snapshot_id']=review['snapshot_id']+'-'+availability_mode
    return review
