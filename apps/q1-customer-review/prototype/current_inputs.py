"""Current-input diagnostics; no model execution or heat-scoring interface.

Import beside the existing prototype.public_weather module after owner review.
Source dates and original availability are never inferred from upload receipts.
"""
from collections import defaultdict
from datetime import date,datetime,time,timedelta
import hashlib,json,math,re
from prototype.public_weather import normalise,window,instant,PERTH,WeatherError

DAY=timedelta(days=1)
DECISION='q1-current-heat-method-20261029'
SYNTHETIC_MODE='synthetic_current_fixture'
HASH=re.compile(r'^[a-f0-9]{64}$')
DAILY_WINDOW='Perth_calendar_day_00_to_24'
TRACKS=('oracle_historical_weather','synthetic_noisy_forecast')

class ContractError(ValueError):pass

def row_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def day(value):
    try:parsed=date.fromisoformat(value)
    except (ValueError,TypeError) as e:raise ContractError('Canonical source date required') from e
    if parsed.isoformat()!=value:raise ContractError('Canonical source date required')
    return parsed

def stamp(value):
    try:return instant(value).astimezone(PERTH)
    except WeatherError as e:raise ContractError(str(e)) from e

def number(value):
    if isinstance(value,bool) or value in (None,''):return None
    try:result=float(value)
    except (ValueError,TypeError):return None
    return result if math.isfinite(result) else None

def synthetic_manifest(manifest,review,lag):
    if not isinstance(manifest,dict) or manifest.get('schema')!='q1-synthetic-current-business/v1':raise ContractError('Synthetic manifest required')
    if manifest.get('synthetic_business') is not True or manifest.get('real_customer_data') is not False or manifest.get('genuine_as_issued') is not False:raise ContractError('Synthetic purpose must be explicit')
    if stamp(manifest.get('review_as_of'))!=review:raise ContractError('Synthetic review cutoff differs')
    stamp(manifest.get('generated_at')) # Actual generation, not row availability.
    if manifest.get('timezone')!='Australia/Perth' or manifest.get('daily_window')!=DAILY_WINDOW or manifest.get('reporting_lag_days')!=lag:raise ContractError('Daily/reporting contract differs')
    if not isinstance(manifest.get('availability_rule_id'),str) or not manifest['availability_rule_id']:raise ContractError('Simulated reporting rule required')
    files=manifest.get('source_files_sha256')
    if not isinstance(files,dict) or not files or any(not isinstance(k,str) or not isinstance(v,str) or not HASH.fullmatch(v) for k,v in files.items()):raise ContractError('Business file fingerprints required')
    return row_hash(manifest)

def business_readiness(tables,*,review_as_of,availability_records=None,mode='strict',generation_manifest=None,reporting_lag_days=1):
    """Validate row availability without admitting current model outputs.

    Existing upload validation owns all twelve CSV schemas, joins and file-byte
    checks. Sidecars bind exact parsed rows here. A manifest is lineage, not an
    approval switch. Payment/support records are not added as demand features.
    """
    if mode not in ('strict',SYNTHETIC_MODE):raise ContractError('Unknown availability mode')
    review=stamp(review_as_of)
    if type(reporting_lag_days) is not int or reporting_lag_days not in (1,2):raise ContractError('Declare a one- or two-day reporting lag')
    manifest_sha=synthetic_manifest(generation_manifest,review,reporting_lag_days) if mode==SYNTHETIC_MODE else None
    customers={c['customer_id']:c for c in tables['customers']}
    if len(customers)!=len(tables['customers']) or any(not re.fullmatch(r'C[0-9]+',cid) for cid in customers):raise ContractError('Ambiguous or unmapped app customer identity')
    indexed=defaultdict(dict);sidecars={}
    for entry in availability_records or []:
        key=(entry['customer_id'],entry['date']);day(key[1])
        if key in sidecars:raise ContractError('Duplicate availability record')
        sidecars[key]=entry
    for row in tables['consumption_daily']:
        cid,label=row['customer_id'],row['date'];day(label)
        if cid not in customers:raise ContractError('Cross-customer usage identity')
        if label in indexed[cid]:raise ContractError('Duplicate usage date')
        indexed[cid][label]=row
    if any(cid not in indexed or label not in indexed[cid] for cid,label in sidecars):raise ContractError('Orphan availability record')
    end=review.date()-reporting_lag_days*DAY;required=[str(end-(6-i)*DAY) for i in range(7)];rows=[]
    for cid,c in customers.items():
        eligible={};excluded=defaultdict(int);unknown=0
        for label,row in indexed[cid].items():
            if day(label)>=review.date():continue
            value,outage=number(row.get('import_kwh')),number(row.get('outage_hours'))
            if value is None or value<0 or outage!=0 or row.get('supply_status')!='connected':excluded['invalid_or_interrupted_usage']+=1;continue
            meta=sidecars.get((cid,label))
            if meta is None:unknown+=1;continue
            if meta.get('row_sha256')!=row_hash(row):excluded['row_fingerprint_mismatch']+=1;continue
            if mode==SYNTHETIC_MODE:
                if meta.get('original_available_at') is not None or meta.get('basis')!='generator_simulated_schedule' or meta.get('source_manifest_sha256')!=manifest_sha or meta.get('availability_rule_id')!=generation_manifest['availability_rule_id']:excluded['invalid_simulated_lineage']+=1;continue
                available=meta.get('simulated_available_at')
            else:
                if meta.get('basis')!='original_source_record' or not isinstance(meta.get('evidence_sha256'),str) or not HASH.fullmatch(meta['evidence_sha256']) or meta.get('timezone')!='Australia/Perth' or meta.get('daily_window')!=DAILY_WINDOW:unknown+=1;continue
                available=meta.get('original_available_at')
            if available is None:unknown+=1;continue
            try:available=stamp(available)
            except ContractError:excluded['invalid_availability_time']+=1;continue
            if available<datetime.combine(day(label)+DAY,time(),PERTH):excluded['availability_before_daily_window_closed']+=1;continue
            if available>review:excluded['not_available_at_review']+=1;continue
            eligible[label]=value
        usable=[label for label in required if label in eligible];source_dates=[label for label in indexed[cid] if day(label)<review.date()]
        mapped=c.get('postcode')=='6765' and c.get('locality')=='Fitzroy Crossing'
        rows.append({'customer_id':cid,'household_id':'q1-app/customer/'+cid,'locality_id':'q1-app/silo-point/-18.20,125.55' if mapped else None,'identity_basis':'namespaced_app_identity_not_benchmark_membership','locality_mapped':mapped,'latest_source_usage_date':max(source_dates,default=None),'latest_eligible_usage_date':max(eligible,default=None),'recent_eligible_days':len(usable),'recent_complete':len(usable)==7,'recent_imports':[{'date':d,'import_kwh':eligible.get(d)} for d in required],'unknown_availability_rows':unknown,'excluded_counts':dict(excluded),'availability_basis':mode,'current_estimate':None,'current_estimate_reason':'current_weather_and_model_contract_not_admitted' if len(usable)==7 else 'current_reported_usage_unavailable','account_status':'source_dated_state_not_verified_current'})
    return {'review_as_of':review.isoformat(),'availability_mode':mode,'required_usage_start':required[0],'required_usage_end':required[-1],'reporting_lag_days':reporting_lag_days,'customers':rows,'schema_changes':False,'date_shifting':False,'model_inference_performed':False,'current_estimates_available':False}

def temperature_context(raw,*,review_as_of,adapter_loaded_at,source_last_error=None):
    """Calendar-day hourly extrema, with availability separate from issuance."""
    review=stamp(review_as_of)
    try:snapshot=normalise(raw)
    except (WeatherError,TypeError,KeyError,ValueError):
        result=window(None,review);result['status']['reason']='invalid_public_source';result['temperature_display']='unavailable';result['heat_classification']={'status':'unavailable','reason':'invalid_public_source','decision_id':DECISION,'official_bom_category':None};return result
    return normalised_temperature_context(snapshot,review_as_of=review_as_of,adapter_loaded_at=adapter_loaded_at,source_last_error=source_last_error)

def normalised_temperature_context(snapshot,*,review_as_of,adapter_loaded_at,source_last_error=None,start_offset=1):
    """Consume an immutable copy already validated by PublicWeatherStore."""
    review=stamp(review_as_of)
    if start_offset not in (0,1):raise ContractError('Unsupported seven-day display offset')
    if snapshot is None:
        result=window(None,review);result.update(temperature_display='unavailable',heat_classification={'status':'unavailable','reason':'no_valid_snapshot','decision_id':DECISION,'official_bom_category':None})
        if start_offset==0:
            for i,entry in enumerate(result['days']):entry['date']=str(review.date()+i*DAY)
            result.update(horizon_start=result['days'][0]['date'],horizon_end=result['days'][-1]['date'])
        return result
    loaded=stamp(adapter_loaded_at)
    retrieved=stamp(snapshot['retrieved_at'])
    if loaded<retrieved:raise ContractError('Adapter load precedes source retrieval')
    available=max(retrieved,loaded)
    if available>review:
        result=window(None,review);result.update(source={k:v for k,v in snapshot.items() if k!='hourly'},temperature_display='unavailable');result['status']['reason']='source_not_available_to_adapter_at_review'
    else:result=window(snapshot,review,source_last_error);result['temperature_display']='available' if result['status']['state']=='fresh' else 'saved_stale_temperatures_only'
    if start_offset==0:
        index={r['valid_at']:r['temperature_c'] for r in snapshot['hourly']} if available<=review else {}
        for i,entry in enumerate(result['days']):
            label=review.date()+i*DAY;begin=datetime.combine(label,time(),PERTH);values=[index.get((begin+timedelta(hours=h)).isoformat()) for h in range(24)];complete=all(v is not None for v in values)
            entry.update(date=str(label),max_temp=max(values) if complete else None,min_temp=min(values) if complete else None,status='available' if complete else 'unavailable',reason=None if complete else 'missing_or_null_forecast_hour')
        result.update(horizon_start=result['days'][0]['date'],horizon_end=result['days'][-1]['date']);result['status']['complete_target_days']=sum(e['status']=='available' for e in result['days'])
    result['availability']={'requested_at':snapshot['requested_at'],'retrieved_at':snapshot['retrieved_at'],'adapter_loaded_at':loaded.isoformat(),'available_to_adapter_at':available.isoformat(),'model_issued_at':snapshot['model_issued_at'],'retrieval_is_not_issuance':True}
    result['spatial_context']={'requested_town':snapshot['town_coordinates'],'actual_forecast_grid':snapshot['provider_grid'],'actual_forecast_elevation_m':snapshot.get('provider_elevation_m'),'SILO_reference_grid':[-18.2,125.55],'spatial_bridge_admitted':False,'declared_model':None,'downscaling_configuration':'not_explicit_in_retained_response'}
    by_hour={r['valid_at']:r['kind'] for r in snapshot['hourly']}
    for entry in result['days']:
        start=datetime.combine(day(entry['date']),time(),PERTH)
        entry.update(window_start=start.isoformat(),window_end_exclusive=(start+DAY).isoformat(),statistic='extrema_of_24_hourly_temperature_samples_Perth_calendar_day',basis=sorted({by_hour.get((start+timedelta(hours=h)).isoformat(),'missing') for h in range(24)}),observed=False,heat_classification=None)
    result['heat_classification']={'status':'unavailable','reason':'temperature_only_method_decision','decision_id':DECISION,'official_bom_category':None};result['current_customer_estimates_available']=False
    return result

def observed_context(retained,*,review_as_of):
    """Separate decoded observations; never a mixed series or heat category."""
    review=stamp(review_as_of);eligible=[];excluded=defaultdict(int);seen=set()
    for row in retained.get('windows',[]):
        label=row['date'];d=day(label)
        if label in seen:raise ContractError('Duplicate observed window')
        seen.add(label)
        if row.get('status')!='available_in_staging' or row.get('issues'):excluded['source_window_unavailable']+=1;continue
        begin,end=stamp(row['window_start']),stamp(row['window_end']);expected=datetime.combine(d,time(9),PERTH)
        if begin!=expected or end!=expected+DAY:raise ContractError('Observed window definition changed')
        if stamp(row['staged_loaded_at'])<stamp(row['snapshot_available_at']):raise ContractError('Observed staging load precedes snapshot availability')
        if any(stamp(row[key])>review for key in ('snapshot_available_at','staged_loaded_at','window_end')):excluded['not_available_at_review']+=1;continue
        maximum,minimum=row['components']['tmax'],row['components']['following_tmin'];hi,lo=number(maximum.get('value_c')),number(minimum.get('value_c'))
        if maximum.get('date')!=label or minimum.get('date')!=str(d+DAY):raise ContractError('Following-night pair changed or Tmax shifted twice')
        if any(p.get('source_classification')!='interpolated_observations' or p.get('grid')!=[-18.2,125.55] or p.get('units')!='degC' or p.get('source_codes') is not None for p in (maximum,minimum)):raise ContractError('Observed source identity changed')
        for component,variable,nominal in ((maximum,'max_temp',d),(minimum,'min_temp',d+DAY)):
            url=f'https://silo-open-data.s3.ap-southeast-2.amazonaws.com/Official/daily/{variable}/{nominal.year}/{nominal:%Y%m%d}.{variable}.tif'
            if component.get('source_url')!=url or not isinstance(component.get('source_bundle_sha256'),str) or not HASH.fullmatch(component['source_bundle_sha256']) or component.get('identity_kind')!='retained_range_envelope_sha256':raise ContractError('Observed component reference changed')
        if any(not end<=stamp(p['retrieved_at'])<=stamp(row['snapshot_available_at']) for p in (maximum,minimum)):raise ContractError('Observed component availability contradicts physical window/snapshot')
        if hi is None or lo is None or lo>hi or not -90<=lo<=hi<=65:excluded['invalid_or_inverted_observed_pair']+=1;continue
        midpoint=number(row.get('dmt_c'))
        if midpoint is None or not math.isclose(midpoint,(hi+lo)/2,rel_tol=0,abs_tol=1e-10):raise ContractError('Observed midpoint differs from source pair')
        references={role:{key:p.get(key) for key in ('date','variable','source_url','source_bundle_sha256','identity_kind','source_object_etag','retrieved_at','native_representation')} for role,p in row['components'].items()}
        eligible.append({'date':label,'window_start':begin.isoformat(),'window_end_exclusive':end.isoformat(),'max_temp_c':hi,'min_temp_c':lo,'source_classification':'interpolated_observations','source_codes':None,'source_provenance':{'snapshot_available_at':row['snapshot_available_at'],'staged_loaded_at':row['staged_loaded_at'],'app_ingested_at':row.get('app_ingested_at'),'adapter_reference_version':row.get('adapter_reference_version'),'day_window_reference_version':row.get('day_window_reference_version'),'components':references}})
    eligible.sort(key=lambda r:r['date'])
    return {'windows':eligible,'complete_windows':len(eligible),'first_window':eligible[0]['date'] if eligible else None,'last_window':eligible[-1]['date'] if eligible else None,'excluded_counts':dict(excluded),'app_ingested_at':retained.get('app_ingested_at'),'source_grid':[-18.2,125.55],'calibration_admitted':False,'combined_with_forecasts':False,'heat_classification':None}

def model_contract_gaps(*,review_as_of):
    review=stamp(review_as_of).date();app=[str(review+i*DAY) for i in range(1,8)];released=[str(review+i*DAY) for i in range(7)]
    return {'released_tracks':list(TRACKS),'actual_generic_forecast_relabelled_as_released_track':False,'provider_issue_time_required_for_temperature_display':False,'as_issued_accuracy_assessment_available':False,'current_source_to_frozen_track_mapping':'not_admitted','frozen_horizon':{'start':released[0],'end':released[-1]},'q1_horizon':{'start':app[0],'end':app[-1]},'overlap_dates':[d for d in app if d in released],'uncovered_q1_dates':[d for d in app if d not in released],'missing_full_90_or_365_day_history_is_automatically_fatal':False,'missing_support_counts_must_be_encoded':True,'EHF_is_a_frozen_M5_feature':False,'heat_event_query_semantics_require_separate_contract':True,'heat_classification_available':False,'current_customer_estimates_available':False,'reason_codes':['source_grid_statistic_and_fixed_model_bridge_unaccepted','external_forecast_track_mapping_unaccepted','query_window_construction_not_released_for_current_sources','Q1_day7_outside_frozen_issue_plus6','original_business_availability_and_current_context_unverified'],'decision_id':DECISION,'numeric_fixture_experiment':'possible_only_under_explicit_synthetic_input_and_weather_lane_contract; no_current_release_or_accuracy_claim','scoring_interface_present':False}

def current_payload(raw,tables,*,review_as_of,adapter_loaded_at,availability_records=None,mode='strict',generation_manifest=None,reporting_lag_days=1,observations=None,source_last_error=None):
    result=temperature_context(raw,review_as_of=review_as_of,adapter_loaded_at=adapter_loaded_at,source_last_error=source_last_error)
    business=business_readiness(tables,review_as_of=review_as_of,availability_records=availability_records,mode=mode,generation_manifest=generation_manifest,reporting_lag_days=reporting_lag_days)
    for row in business['customers']:
        row.update(latest_usage_date=row['latest_source_usage_date'],complete_recent_days=row['recent_eligible_days'],estimate=None,estimate_reason=row['current_estimate_reason'])
    result.update(business=business,model_admission=model_contract_gaps(review_as_of=review_as_of))
    result['observed_context']=observed_context(observations,review_as_of=review_as_of) if observations is not None else None
    return result
