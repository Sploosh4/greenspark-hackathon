"""Application view adapter; original business schemas stay unchanged."""
from __future__ import annotations
from collections import defaultdict
from datetime import date,timedelta
import hashlib
import json
import platform
from pathlib import Path
from .inputs import load_business,DEFAULT_SOURCE
from .weather import load_weather,event_windows
from .prediction import Recent7HeatOffsetBaseline,observed_event,day_range,METHOD
from .work import checkpoint

REVIEW_DATE='2024-11-02'
RELEVANT_NEEDS={'financial_pressure_disclosed':'Financial difficulty','cooling_affordability_concern':'Difficulty paying cooling costs','electricity_rationing_concern':'Concern about electricity costs'}

def decorate_event(raw,i):
    return {**raw,'id':'EHF-'+raw['start'],'label':'Heat period '+str(i+1),'category':'Derived historical heat period','duration':raw.get('full_event_duration_days')}

def customer_index(tables):
    """Group each table once, preserving source ordering within each customer."""
    result={}
    for name,rows in tables.items():
        grouped=defaultdict(list)
        for row in rows:
            checkpoint();grouped[row['customer_id']].append(row)
        result[name]=grouped
    return result

def customer_rows(tables,name,cid,index):
    return tables[name] if index is None else index[name].get(cid,())

def known_support_links(tables,cid,event,cutoff,*,index=None):
    """Temporal overlap only. No need is invented from a bill or account flag."""
    links=[]; seen=set()
    for r in customer_rows(tables,'support_needs_history',cid,index):
        checkpoint()
        if r['customer_id']!=cid or r['need_type'] not in RELEVANT_NEEDS or r['status']!='current': continue
        if r['source_event_date']>cutoff or r['effective_from']>event['end']: continue
        # Later state endpoints are not a past feature. Only boundaries known
        # by this review can close the recorded interval.
        known_end=r['effective_to'] if r['effective_to'] and r['effective_to']<=cutoff else None
        if known_end and known_end<=event['start']: continue
        if r['need_id'] in seen: continue
        seen.add(r['need_id'])
        links.append({'source_table':'support_needs_history','source_id':r['need_id'],'source_event_date':r['source_event_date'],'label':RELEVANT_NEEDS[r['need_type']],'basis':'recorded current difficulty overlaps this historical heat period; not a causal or delivery claim'})
    for table,idcol,datecol,label,statuscol,valid in [
      ('payment_arrangements','arrangement_id','start_date','Arrangement started',None,None),
      ('hardship_programs','hardship_id','assessment_date','Hardship assessment','assessment_outcome',{'accepted','denied'}),
      ('hugs_grants','hugs_id','application_date','Grant application',None,None)]:
        for r in customer_rows(tables,table,cid,index):
            checkpoint()
            if r['customer_id']==cid and event['start']<=r[datecol]<=min(event['end'],cutoff):
                if statuscol and r[statuscol] not in valid: continue
                links.append({'source_table':table,'source_id':r[idcol],'source_event_date':r[datecol],'label':label,'basis':'recorded event date falls inside the historical heat period; no causal/delivery claim'})
    return links

def records_at(tables,cid,cutoff,*,index=None):
    records=[]
    specs=[('payment_arrangements','start_date','arrangement_id','Arrangement started'),('hardship_programs','assessment_date','hardship_id','Hardship assessed'),('hugs_grants','application_date','hugs_id','Grant application'),('support_needs_history','source_event_date','need_id','Difficulty recorded'),('payments','date','payment_id','Payment recorded')]
    for table,datecol,idcol,label in specs:
        seen=set()
        for r in customer_rows(tables,table,cid,index):
            checkpoint()
            if r['customer_id']!=cid or not r[datecol] or r[datecol]>cutoff or r[idcol] in seen: continue
            seen.add(r[idcol])
            if table=='payments' and r['status']!='cleared': continue
            kind=('Bill extension' if r['type']=='bill_extension' else 'Payment plan started') if table=='payment_arrangements' else label
            if table=='support_needs_history' and r['need_type'] not in RELEVANT_NEEDS: kind='Support need recorded'
            records.append({'id':r[idcol],'kind':kind,'date':r[datecol],'source':table+'.'+datecol,**({'amount':r['amount']} if table=='payments' else {})})
    return sorted(records,key=lambda r:(r['date'],r['id']))

def build_review(root=DEFAULT_SOURCE,*,review_date=REVIEW_DATE,provider=None,weather_root=None):
    checkpoint()
    tables,audit=load_business(root)
    checkpoint()
    weather,weather_provenance=load_weather(root if weather_root is None else weather_root)
    past_raw,replay_raw,context=event_windows(weather,weather_provenance,review_date)
    checkpoint()
    cutoff=context['history_cutoff']
    past=[decorate_event(e,i) for i,e in enumerate(past_raw['events'])]
    upcoming=[decorate_event(e,i) for i,e in enumerate(replay_raw['events'])]
    provider=provider or Recent7HeatOffsetBaseline()
    grouped=customer_index(tables)
    usage_by=defaultdict(list)
    for r in tables['consumption_daily']:
        checkpoint()
        if r['date']<=cutoff: usage_by[r['customer_id']].append({k:r[k] for k in ('date','import_kwh','supply_status','outage_hours')})
    customers=[]; excluded=[]
    expected_days=len(day_range(context['history_window_start'],cutoff))
    for source_customer in tables['customers']:
        checkpoint()
        cid=source_customer['customer_id']
        if source_customer['account_open_date']>review_date or (source_customer['account_close_date'] and source_customer['account_close_date']<=review_date):
            excluded.append({'customer_id':cid,'reason':'not_open_on_review_date'});continue
        # No future closure endpoint or later customer history is presented as a feature.
        customer=dict(source_customer)
        if customer['account_close_date']>cutoff: customer['account_close_date']=''
        usage=sorted(usage_by[cid],key=lambda r:r['date']); index={r['date']:r for r in usage}
        checkpoint()
        predictions=provider.predict(usage,past,upcoming,cutoff=cutoff)
        checkpoint()
        episodes=[]
        for event in past:
            checkpoint();links=known_support_links(tables,cid,event,cutoff,index=grouped)
            if not links: continue
            observed=observed_event(index,event,cutoff)
            episodes.append({'id':event['id'],'start':event['start'],'end':event['end'],'label':' / '.join(dict.fromkeys(r['label'] for r in links)),'linked':True,'increase_percent':observed['increase_percent'],'provenance':'derived_temporal_overlap','association_basis':'dated support/difficulty overlaps heat; no weather-causality inference','source_links':links,'calculation':observed})
        if customer['prepayment_meter']=='True':
            ledger=sorted((r for r in grouped['prepay_daily'].get(cid,()) if r['date']<=cutoff),key=lambda r:r['date'])
            financial=[{'kind':'Prepaid closing credit','date':r['date'],'amount':r['closing_credit'],'source':'prepay_daily.closing_credit'} for r in ledger[-1:]]
        else:
            bills=sorted((r for r in grouped['bills'].get(cid,()) if r['issue_date']<=cutoff),key=lambda r:r['issue_date'])
            financial=[{'kind':'Bill issued','date':r['issue_date'],'amount':r['amount_due'],'source':'bills.amount_due','id':r['bill_id']} for r in bills[-3:]]
        available_days=sum(context['history_window_start']<=r['date']<=cutoff for r in usage)
        checkpoint()
        customers.append({'customer':customer,'usage':usage,'episodes':episodes,'predictions':predictions,'financial':financial,'records':records_at(tables,cid,cutoff,index=grouped),'history_coverage':{'available_days':available_days,'expected_days':expected_days,'status':'complete' if available_days==expected_days else 'partial','missing_days':expected_days-available_days}})
    app_root=Path(__file__).resolve().parents[1]
    files=['prototype/current_inputs.py','prototype/replay_snapshot.py','tools/build_replay_snapshot.py','serve.py','prototype/uploads.py','prototype/jobs.py','prototype/work.py','prototype/exports.py','prototype/public_weather.py','prototype/public_source.py','prototype/weather_job.py','prototype/live.py','prototype/vendor/auth/local_auth.py','assets/auth-login.html','assets/auth-login.mjs','assets/auth-session.mjs','docs/UPLOAD-VALIDATION-CONTRACT.json','pdf_export.py','app.mjs','core.mjs','index.html','assets/q1.css','prototype/inputs.py','prototype/weather.py','prototype/prediction.py','prototype/review.py','prototype/vendor/ehf/core.py','prototype/vendor/ehf/adapters.py','prototype/vendor/ehf/calibration-v1.json']
    hashes={name:hashlib.sha256((app_root/name).read_bytes()).hexdigest() for name in files}
    code_hash=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    result={'version':'q1-calculated-historical-v1','build':{'id':'q1-m1-'+code_hash[:16],'code_sha256':code_hash,'component_sha256':hashes,'python':platform.python_version()},'kind':'calculated_historical_replay',**context,'customers':customers,'events':upcoming,'weather':[{k:r[k] for k in ('date','postcode','max_temp','min_temp')} for r in weather if r['date']<=context['horizon_end']],
      'method':provider.method,'past_events':past,'weather_calculation':{'historical':past_raw,'replay':replay_raw},'input_validation':audit,'weather_provenance':weather_provenance,'excluded_customers':excluded,
      'association_rule':'source event date within heat period, or an explicitly relevant current difficulty interval overlaps it; temporal association only',
      'provenance':{'business':'Unchanged Horizon clean synthetic candidate CSVs; source dates retained','estimates':provider.method['name']+'; calculated, unvalidated baseline; no ML or causality claim','episode_links':'Derived date/interval overlap of explicit existing source records and historical EHF periods; not causal','weather':'Real SILO historical interpolated observations; retrospective hindsight after review, not as-issued forecast','baseline':'Latest 7 completed connected, zero-outage days; past heat offsets use their own preceding 7-day means'},
      'status':{'business':'synthetic historical','weather':'real historical replay','current_live_status':'stale_for_current_use','current_weather_forecast':False,'official_bom_category':None,'prediction_accuracy_validated':False}}
    return result
