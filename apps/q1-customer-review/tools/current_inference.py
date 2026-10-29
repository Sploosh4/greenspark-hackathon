"""Bounded local frozen-v3 inference for current-synthetic-demo/v1.0.1.

No fitting/reselection, network, generator code or evaluation inputs are used.
"""
from pathlib import Path
from datetime import datetime,date,time,timedelta,timezone
from collections import defaultdict
import hashlib,importlib.util,json,math,sys,resource,time as monotime
from importlib.metadata import version

APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
from prototype.inputs import load_business
from prototype.review import customer_index,records_at
from prototype.public_weather import PERTH,instant,window

MODEL_SHA='c4a09dadf6544992d0c931a11e86e662aa3d2106d513c2165701c08c72e72db7'
CONTRACT='current-synthetic-demo/v1.0.1';LANE='oracle_historical_weather';DAY=timedelta(days=1)

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if hasattr(value,'item'):value=value.item()
    return None if isinstance(value,float) and not math.isfinite(value) else value

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def reported_week(usage,eligible,d):
    latest=max((row['date'] for row in usage),default=None)
    lag=(d-date.fromisoformat(latest)).days if latest else None
    if latest is None:return latest,lag,'missing_usage_history'
    if lag not in (1,2):return latest,lag,'reported_usage_more_than_two_days_old'
    if any(str(date.fromisoformat(latest)-i*DAY) not in eligible for i in range(7)):return latest,lag,'incomplete_reported_week'
    return latest,lag,None

def frozen():
    expected={'numpy':'2.3.5','scipy':'1.17.0','scikit-learn':'1.8.0','joblib':'1.5.3','threadpoolctl':'3.6.0'}
    if sys.version_info[:2]!=(3,12) or any(version(k)!=v for k,v in expected.items()):raise ValueError('Frozen dependency contract differs')
    bundle=APP/'prototype/vendor/frozen_v3'
    if sha(bundle/'FILE_MANIFEST.json')!=MODEL_SHA:raise ValueError('Frozen manifest differs')
    manifest=json.loads((bundle/'FILE_MANIFEST.json').read_text())
    for name,info in manifest['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe frozen path')
        p=bundle/relative
        if p.stat().st_size!=info['bytes'] or sha(p)!=info['sha256']:raise ValueError('Frozen artifact differs')
    spec=importlib.util.spec_from_file_location('current_frozen_predictor',bundle/'predict_v3.py')
    predictor=importlib.util.module_from_spec(spec);spec.loader.exec_module(predictor)
    release=json.loads((bundle/'INFERENCE_RELEASE.json').read_text())
    return predictor,predictor.load_features(),release

def run(payload):
    began=monotime.perf_counter();predictor,features,release=frozen();import numpy as np
    now=instant(payload['as_of']).astimezone(PERTH);received=instant(payload['received_at']);context=payload['weather'];snapshot=context['snapshot'];d=now.date()
    tables,audit=load_business(Path(payload['source_root']));index=customer_index(tables)
    available=instant(context['adapter_loaded_at']) if snapshot else None
    weather_status=window(snapshot,now,context.get('last_error'));weather_by={}
    if snapshot:
        hourly={r['valid_at']:r['temperature_c'] for r in snapshot['hourly']}
        labels=sorted({instant(r['valid_at']).astimezone(PERTH).date() for r in snapshot['hourly']})
        for label in labels:
            begin=datetime.combine(label,time(),PERTH);values=[hourly.get((begin+timedelta(hours=i)).isoformat()) for i in range(24)]
            if all(v is not None for v in values):weather_by[str(label)]=(max(values),min(values))
    weather_reason=None
    if received>now:weather_reason='upload_received_after_calculation'
    elif not snapshot or available>now:weather_reason='forecast_not_available_at_calculation'
    elif weather_status['status']['state']!='fresh':weather_reason='forecast_stale_or_refresh_failed'
    elif any(str(d+i*DAY) not in weather_by for i in range(7)):weather_reason='incomplete_scenario_forecast'
    start,end=str(d),str(d+6*DAY);event={'id':'CURRENT-'+start,'label':'7-day usage scenario','start':start,'end':end,'duration':7,'category':'Fixed current-date synthetic scenario','start_boundary':'known_start','end_boundary':'known_end'}
    weather_rows=[{'date':label,'locality_id':'q1-app/silo-point/-18.20,125.55','tmax_c':pair[0],'tmin_c':pair[1],'weather_available_at':context['adapter_loaded_at']} for label,pair in weather_by.items() if label<start] if snapshot else []
    customers=[];prepared=[];positions=[];excluded=[];cutoff=str(d-DAY);history_start=str(d-731*DAY)
    for c0 in tables['customers']:
        cid=c0['customer_id']
        if c0['account_open_date']>start or c0['account_close_date'] and c0['account_close_date']<=start:excluded.append({'customer_id':cid,'reason':'not_open_on_review_date'});continue
        customer=dict(c0)
        if customer['account_close_date']>start:customer['account_close_date']=''
        usage=[{k:r[k] for k in ('date','import_kwh','supply_status','outage_hours')} for r in index['consumption_daily'].get(cid,()) if history_start<=r['date']<start]
        usage.sort(key=lambda r:r['date']);meters=[]
        for row in usage:
            value,outage=float(row['import_kwh']),float(row['outage_hours'])
            if row['supply_status']=='connected' and outage==0 and math.isfinite(value) and value>=0:meters.append({'date':row['date'],'grid_import_kwh':value,'household_id':'q1-app/customer/'+cid,'locality_id':'q1-app/silo-point/-18.20,125.55','observation_available_at':payload['received_at']})
        eligible={r['date'] for r in meters};latest,lag,usage_reason=reported_week(usage,eligible,d);reason=usage_reason or weather_reason
        if c0['postcode']!='6765' or c0['locality']!='Fitzroy Crossing':reason='locality_not_mapped'
        q={'query_id':'q1-current/'+cid+'/'+start,'event_id':'q1-current/'+start,'household_id':'q1-app/customer/'+cid,'locality_id':'q1-app/silo-point/-18.20,125.55','history_id':'q1-current-history/'+cid,'issue_time':payload['as_of'],'forecast_track':LANE,'window_start':start,'window_end':end,'window_duration_days':7,'left_censored':0,'right_censored':0,'window_kind':'ordinary_control','recent_baseline_kwh':None,'baseline_n_days':0,'baseline_method':'unavailable','n_complete_forecast_days':7}
        b,n,method=features.loader.official_baseline(q,meters,weather_rows);q.update(recent_baseline_kwh=b,baseline_n_days=n,baseline_method=method)
        if b is None or b<=0:reason=reason or 'missing_or_nonpositive_baseline'
        prediction={'event_id':event['id'],'duration':7,'baseline':b,'baseline_n':n,'baseline_method':method,'predicted':None,'increase':None,'event_total':None,'reason':reason,'method_id':'frozen-v3-M5-current-synthetic/v1','comparison':{'provider':'S1','predicted':None,'increase':None,'event_total':None}}
        if not reason:
            forecasts=[{'event_id':q['event_id'],'locality_id':q['locality_id'],'forecast_track':LANE,'issue_time':payload['as_of'],'valid_date':str(d+i*DAY),'forecast_tmax_c':weather_by[str(d+i*DAY)][0],'forecast_tmin_c':weather_by[str(d+i*DAY)][1]} for i in range(7)]
            x=features.features(q,meters,weather_rows,forecasts);positions.append(len(customers));prepared.append((q,x));prediction['feature_evidence']=clean(x)
        if customer['prepayment_meter']=='True':
            ledger=sorted((r for r in index['prepay_daily'].get(cid,()) if r['date']<=cutoff),key=lambda r:r['date'])
            financial=[{'kind':'Prepaid closing credit','date':r['date'],'amount':r['closing_credit'],'source':'prepay_daily.closing_credit'} for r in ledger[-1:]]
        else:
            bills=sorted((r for r in index['bills'].get(cid,()) if r['issue_date']<=cutoff),key=lambda r:r['issue_date'])
            financial=[{'kind':'Bill issued','date':r['issue_date'],'amount':r['amount_due'],'source':'bills.amount_due','id':r['bill_id']} for r in bills[-3:]]
        customers.append({'customer':customer,'usage':usage,'episodes':[],'predictions':[prediction],'financial':financial,'records':records_at(tables,cid,cutoff,index=index),'history_coverage':{'available_days':len(usage),'expected_days':731,'missing_days':731-len(usage),'status':'complete' if len(usage)==731 else 'partial'},'reporting_lag_days':lag,'reported_complete_days':sum(str(date.fromisoformat(latest)-i*DAY) in eligible for i in range(7)) if latest else 0,'latest_reported_usage_date':latest})
    if prepared:
        qs=[q for q,x in prepared];matrix=np.array([[x[k] for k in release['full_columns']] for q,x in prepared],dtype=float)
        m5=predictor.predict_matrix(qs,matrix,release,'central');s1=predictor.predict_matrix(qs,matrix,release,'simple')
        for i,position in enumerate(positions):
            p=customers[position]['predictions'][0];b=p['baseline'];value=float(m5[i]);comparison=float(s1[i])
            if not all(math.isfinite(v) and v>=0 for v in (value,comparison)):raise ValueError('Frozen model returned invalid output')
            p.update(predicted=value,increase=100*(value/b-1),event_total=value*7,reason=None)
            p['comparison'].update(predicted=comparison,increase=100*(comparison/b-1),event_total=comparison*7)
    code={str(p.relative_to(APP)):sha(p) for p in [APP/'tools/current_inference.py',APP/'prototype/current_calculation.py']}
    return clean({'version':'q1-current-synthetic-v1','kind':'calculated_current_synthetic','build':{'id':'q1-current-'+hashlib.sha256(json.dumps(code,sort_keys=True).encode()).hexdigest()[:16],'component_sha256':code},'review_date':start,'history_cutoff':cutoff,'history_window_start':history_start,'history_available_start':min((r['date'] for c in customers for r in c['usage']),default=cutoff),'horizon_start':start,'horizon_end':end,'customers':customers,'events':[event],'past_events':[],'weather':[{'date':label,'postcode':'6765','max_temp':pair[0],'min_temp':pair[1]} for label,pair in sorted(weather_by.items()) if label<=end],'method':{'id':'frozen-v3-M5-current-synthetic/v1','name':'Frozen M5 with S1 comparison; current synthetic scenario'},'input_validation':audit,'excluded_customers':excluded,'provenance':{'business':'Synthetic customer upload, source dates unchanged','estimates':'Frozen M5/S1 numerical scenario; current-weather accuracy unvalidated','weather':'Open-Meteo modelled calendar-day hourly extrema; past weather is modelled, not observations'},'status':{'business':'synthetic current-date demo','weather':'modelled public forecast','current_live_status':'experimental_synthetic','official_bom_category':None,'prediction_accuracy_validated':False},'current_demo':{'contract':CONTRACT,'mode':'current_synthetic_demo','business_received_at':payload['received_at'],'original_row_available_at':None,'inference_as_of':payload['as_of'],'denominator_policy':'frozen_current_B','model_manifest_sha256':MODEL_SHA,'source_track':'open-meteo-modelled-context/v1','estimator_lane':LANE,'weather_snapshot_sha256':context['snapshot_sha256'],'weather_requested_at':snapshot.get('requested_at') if snapshot else None,'weather_retrieved_at':snapshot.get('retrieved_at') if snapshot else None,'weather_adapter_loaded_at':context['adapter_loaded_at'],'provider_issue_at':None,'provider_grid':snapshot.get('provider_grid') if snapshot else None,'weather_statistic':'24-hour Perth calendar extrema from modelled hourly values','query_kind':'ordinary_control','classification':'fixed_usage_scenario_not_heatwave','training_or_reselection':False,'inference_seconds':monotime.perf_counter()-began,'inference_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'available_customers':len(prepared),'reporting_lag_days':sorted({c['reporting_lag_days'] for c in customers if c['reporting_lag_days'] is not None})}})

if __name__=='__main__':
    payload=json.load(sys.stdin);json.dump(run(payload),sys.stdout,allow_nan=False,separators=(',',':'))
