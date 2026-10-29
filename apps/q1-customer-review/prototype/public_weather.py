"""Read-only public forecast adapter and last-good local ingestion.

Consumes the existing authorised public-weather writer's cache. It never sends
business data, creates credentials, changes real dates or labels forecasts as
observations. Generic Open-Meteo responses do not supply model issue time.
"""
from datetime import datetime,time,timedelta,timezone
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit,parse_qs
import hashlib,json,math,os,re,threading,uuid,copy
from .uploads import write_json

PERTH=ZoneInfo('Australia/Perth')
SHARED_CACHE=Path(os.environ.get('Q1_SHARED_WEATHER_CACHE', Path(__file__).resolve().parents[1]/'runtime/public-weather/shared-latest.json'))
MAX_BYTES=4*1024*1024
FRESH_HOURS=24
LAT,LON=-18.19714,125.56663
PUBLIC_CONTRACT='open-meteo-modelled-context/v1'
PAST_DAYS,FORECAST_DAYS=35,12

class WeatherError(ValueError):pass

def instant(value):
    try:result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (AttributeError,TypeError,ValueError) as e:raise WeatherError('Invalid source timestamp') from e
    if result.tzinfo is None:raise WeatherError('Source timestamp needs its UTC offset')
    return result

def utc(value):return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def normalise(raw):
    if not isinstance(raw,dict) or raw.get('schema_version')!=1 or raw.get('dataset_kind')!='live_forecast':raise WeatherError('Unsupported public forecast snapshot')
    if not isinstance(raw.get('source_url'),str):raise WeatherError('Missing public source URL')
    url=urlsplit(raw['source_url'])
    if raw.get('provider')!='Open-Meteo' or url.scheme!='https' or url.netloc!='api.open-meteo.com' or url.path!='/v1/forecast':raise WeatherError('Unsupported public provider contract')
    requested,retrieved=instant(raw.get('requested_at')),instant(raw.get('retrieved_at'))
    if retrieved<requested:raise WeatherError('Retrieval precedes request')
    issue=raw.get('model_issued_at')
    if issue is not None and instant(issue)>retrieved:raise WeatherError('Model issue follows retrieval')
    records=raw.get('localities',[])
    if not isinstance(records,list):raise WeatherError('Missing locality list')
    matches=[r for r in records if isinstance(r,dict) and isinstance(r.get('location'),dict) and r['location'].get('postcode')=='6765']
    if len(matches)!=1:raise WeatherError('Need exactly one Fitzroy Crossing 6765 record')
    record=matches[0];location=record['location'];forecast=record.get('forecast',{})
    if not isinstance(forecast,dict):raise WeatherError('Invalid forecast object')
    if location.get('name')!='Fitzroy Crossing' or (location.get('latitude'),location.get('longitude'))!=(LAT,LON):raise WeatherError('Town identity does not match the reviewed coordinate contract')
    if forecast.get('timezone')!='Australia/Perth' or forecast.get('utc_offset_seconds')!=28800:raise WeatherError('Forecast must use Australia/Perth')
    elevation=forecast.get('elevation')
    if elevation is not None and (type(elevation) not in (int,float) or not math.isfinite(elevation)):raise WeatherError('Invalid provider elevation')
    coordinates=[forecast.get('latitude'),forecast.get('longitude')]
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in coordinates):raise WeatherError('Invalid provider grid')
    a,b=map(math.radians,(LAT,coordinates[0]));delta=math.sin((b-a)/2)**2+math.cos(a)*math.cos(b)*math.sin(math.radians(coordinates[1]-LON)/2)**2
    if 6371*2*math.asin(min(1,math.sqrt(delta)))>100:raise WeatherError('Provider grid is outside the reviewed town area')
    if not isinstance(forecast.get('hourly_units'),dict) or forecast['hourly_units'].get('temperature_2m') not in ('°C','degC'):raise WeatherError('Hourly temperature needs Celsius units')
    hourly=forecast.get('hourly',{})
    if not isinstance(hourly,dict):raise WeatherError('Invalid hourly object')
    stamps=hourly.get('time');values=hourly.get('temperature_2m')
    if not isinstance(stamps,list) or not isinstance(values,list) or len(stamps)!=len(values) or not 24<=len(stamps)<=24*108:raise WeatherError('Invalid bounded hourly series')
    samples=[];previous=None
    for stamp,value in zip(stamps,values):
        try:d=datetime.fromisoformat(stamp)
        except (TypeError,ValueError) as e:raise WeatherError('Invalid hourly time') from e
        d=d.replace(tzinfo=PERTH) if d.tzinfo is None else d.astimezone(PERTH)
        if d.minute or d.second or d.microsecond or (previous is not None and d!=previous+timedelta(hours=1)):raise WeatherError('Hourly sequence has a gap, duplicate or off-hour timestamp')
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not -90<=value<=65):raise WeatherError('Invalid hourly temperature')
        samples.append({'valid_at':d.isoformat(),'temperature_c':value});previous=d
    start=instant(record.get('valid_from'));end=instant(record.get('valid_until_exclusive'))
    if start!=instant(samples[0]['valid_at']) or end!=instant(samples[-1]['valid_at'])+timedelta(hours=1):raise WeatherError('Validity metadata does not match hourly samples')
    extended=raw.get('q1_source_contract')==PUBLIC_CONTRACT
    if raw.get('q1_source_contract') is not None and not extended:raise WeatherError('Unsupported Q1 source contract')
    if extended:
        query=parse_qs(url.query,strict_parsing=True)
        expected={'latitude':[str(LAT)],'longitude':[str(LON)],'hourly':['temperature_2m'],'timezone':['Australia/Perth'],'timeformat':['iso8601'],'temperature_unit':['celsius'],'past_days':[str(PAST_DAYS)],'forecast_days':[str(FORECAST_DAYS)]}
        if query!=expected:raise WeatherError('Extended public request differs from the bounded contract')
        day=requested.astimezone(PERTH).date()
        if start!=datetime.combine(day-timedelta(days=PAST_DAYS),time(),PERTH) or end!=datetime.combine(day+timedelta(days=FORECAST_DAYS),time(),PERTH):raise WeatherError('Extended response does not cover the exact requested dates')
        if issue is not None:raise WeatherError('Generic public response cannot establish a model issue time')
    elif start.astimezone(PERTH).date()!=requested.astimezone(PERTH).date():
        # The existing writer starts today. A future extended adapter must name
        # its archived-forecast warm-up explicitly, rather than call it observed.
        raise WeatherError('Cache start does not match its request day')
    for sample in samples:
        sample['kind']='archived_model_forecast' if instant(sample['valid_at']).date()<requested.astimezone(PERTH).date() else 'model_forecast'
        sample['available_to_app_at']=utc(retrieved)
    return {'schema_version':'q1-public-weather/v1','source_contract':PUBLIC_CONTRACT if extended else 'existing-public-cache/v1','provider':'Open-Meteo','classification':'public_weather_forecast','postcode':'6765','locality':'Fitzroy Crossing','town_coordinates':[LAT,LON],'provider_grid':coordinates,'provider_elevation_m':forecast.get('elevation'),'requested_at':utc(requested),'retrieved_at':utc(retrieved),'model_issued_at':None if issue is None else utc(instant(issue)),'model_issue_note':'Not exposed by the generic response; retrieval is not model issue time.','valid_from':start.isoformat(),'valid_until_exclusive':end.isoformat(),'timezone':'Australia/Perth','hourly':samples,'warmup_kind':'archived_model_forecast' if extended else 'not_supplied','observed_warmup_available':False,'calibration_compatible':False,'daily_aggregation':'max/min of 24 hourly samples in each Perth calendar day; approximate extrema, not EHF windows','attribution':'Weather data by Open-Meteo; town location from GeoNames via Open-Meteo','attribution_url':'https://open-meteo.com/','licence_url':'https://open-meteo.com/en/licence','source_url':raw.get('source_url'),'heat_classification':{'status':'unavailable','reason':'forecast_grid_and_warmup_not_calibrated','official_bom_category':None}}

def window(snapshot,now,last_error=None):
    if now.tzinfo is None:raise WeatherError('Review time needs a UTC offset')
    review=now.astimezone(PERTH).date();first=review+timedelta(days=1);last=review+timedelta(days=7)
    indexed={r['valid_at']:r['temperature_c'] for r in snapshot['hourly']} if snapshot else {}
    days=[]
    for offset in range(7):
        day=first+timedelta(days=offset);start=datetime.combine(day,time(),PERTH)
        values=[indexed.get((start+timedelta(hours=h)).isoformat()) for h in range(24)]
        complete=all(v is not None for v in values)
        days.append({'date':day.isoformat(),'max_temp':max(values) if complete else None,'min_temp':min(values) if complete else None,'status':'available' if complete else 'unavailable','reason':None if complete else 'missing_or_null_forecast_hour'})
    reason='no_valid_snapshot';age=None
    if snapshot:
        age=(now-instant(snapshot['retrieved_at'])).total_seconds()/3600
        reason='fresh' if 0<=age<FRESH_HOURS else 'clock_before_retrieval' if age<0 else 'older_than_24_hours'
        if instant(snapshot['valid_until_exclusive'])<=now:reason='coverage_expired'
        if last_error:reason='refresh_failed'
    warmup=0
    for offset in range(1,PAST_DAYS+1):
        start=datetime.combine(review-timedelta(days=offset),time(),PERTH)
        if all(indexed.get((start+timedelta(hours=h)).isoformat()) is not None for h in range(24)):warmup+=1
    def complete_windows(offsets):
        return sum(all(indexed.get((datetime.combine(review+timedelta(days=offset),time(9),PERTH)+timedelta(hours=h)).isoformat()) is not None for h in range(24)) for offset in offsets)
    context={'complete_prior_calendar_days':warmup,'requested_prior_days':PAST_DAYS,'prior_data_kind':snapshot.get('warmup_kind','not_supplied') if snapshot else 'not_supplied','observed_warmup_available':False,'heat_classification_available':False,'nine_am_window_coverage':{'definition':'[09:00 D,09:00 D+1) hourly extrema coverage only; not a calibrated heat result','prior_required':32,'prior_complete':complete_windows(range(-32,0)),'target_required':7,'target_complete':complete_windows(range(1,8)),'boundary_tail_required':3,'boundary_tail_complete':complete_windows(range(8,11))}}
    return {'review_date':review.isoformat(),'horizon_start':first.isoformat(),'horizon_end':last.isoformat(),'days':days,'status':{'state':'fresh' if reason=='fresh' else 'unavailable' if snapshot is None else 'stale','reason':reason,'age_hours':age,'complete_target_days':sum(d['status']=='available' for d in days),'last_error':last_error},'context_coverage':context,'source':{k:v for k,v in snapshot.items() if k!='hourly'} if snapshot else None,'current_customer_estimates_available':False}

class PublicWeatherStore:
    def __init__(self,root,source_cache=SHARED_CACHE,*,clock=None):
        self.context_clock=clock or (lambda:datetime.now(timezone.utc));self.snapshot_loaded_at=None;self.snapshot_sha256=None
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.source_cache=Path(source_cache);self.lock=threading.RLock();self.last_error=None;self.snapshot=None
        try:
            state=json.loads((self.root/'latest.json').read_text())
            if not re.fullmatch('[a-f0-9]{64}',state['sha256']):raise WeatherError('Invalid saved snapshot identity')
            raw=(self.root/'snapshots'/state['sha256']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=state['sha256']:raise WeatherError('Stored public snapshot hash mismatch')
            snapshot=normalise(json.loads(raw));loaded_at=self._loaded_at()
            self.snapshot=snapshot;self.snapshot_loaded_at=loaded_at;self.snapshot_sha256=state['sha256']
        except (OSError,ValueError,KeyError,TypeError):pass
        try:self.last_error=json.loads((self.root/'attempt.json').read_text()).get('error')
        except (OSError,ValueError,AttributeError):pass
    def refresh(self):
        return self.ingest(self.source_cache)
    def ingest(self,source_cache,*,upstream_status=True):
        source_cache=Path(source_cache)
        with self.lock:
            try:
                if source_cache.stat().st_size>MAX_BYTES:raise WeatherError('Public cache exceeds 4 MiB')
                raw=source_cache.read_bytes()
                if len(raw)>MAX_BYTES:raise WeatherError('Public cache exceeds 4 MiB')
                snapshot=normalise(json.loads(raw));loaded_at=self._loaded_at();sha=hashlib.sha256(raw).hexdigest()
                (self.root/'snapshots').mkdir(exist_ok=True);target=self.root/'snapshots'/sha
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=sha:raise WeatherError('Saved snapshot integrity check failed')
                if not target.exists():
                    tmp=target.with_name('.'+uuid.uuid4().hex+'.tmp')
                    try:
                        with tmp.open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
                        os.replace(tmp,target)
                        fd=os.open(target.parent,os.O_DIRECTORY)
                        try:os.fsync(fd)
                        finally:os.close(fd)
                    finally:tmp.unlink(missing_ok=True)
                upstream_error='upstream_status_unavailable' if upstream_status else None
                try:
                    status_path=source_cache.with_name('status.json')
                    if status_path.stat().st_size>65536:raise WeatherError('Invalid upstream status size')
                    status=json.loads(status_path.read_text())
                    if upstream_status:
                        if status.get('last_attempt_succeeded') is True:upstream_error=None
                        elif status.get('last_attempt_succeeded') is False:upstream_error='upstream_refresh_failed'
                except (OSError,ValueError,AttributeError):pass
                write_json(self.root/'latest.json',{'sha256':sha})
                write_json(self.root/'attempt.json',{'succeeded':True,'error':upstream_error})
                self.snapshot=snapshot;self.last_error=upstream_error;self.snapshot_loaded_at=loaded_at;self.snapshot_sha256=sha
                return {'succeeded':True,'sha256':sha,'retrieved_at':snapshot['retrieved_at']}
            except (OSError,ValueError,KeyError,TypeError):
                self.last_error='public_cache_missing_or_invalid'
                try:write_json(self.root/'attempt.json',{'succeeded':False,'error':self.last_error})
                except OSError:pass
                return {'succeeded':False,'error':self.last_error}
    def view(self,now=None):
        with self.lock:return window(self.snapshot,now or datetime.now(timezone.utc),self.last_error)

    def _loaded_at(self):
        now=self.context_clock()
        if now.tzinfo is None:raise WeatherError('Adapter load clock needs a UTC offset')
        return utc(now)
    def context_source(self):
        with self.lock:return {'snapshot':copy.deepcopy(self.snapshot),'adapter_loaded_at':self.snapshot_loaded_at,'last_error':self.last_error,'snapshot_sha256':self.snapshot_sha256}
