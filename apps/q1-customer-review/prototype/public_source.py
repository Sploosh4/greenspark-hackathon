"""Bounded, credential-free Open-Meteo source for the private local prototype.

Only the fixed public town coordinate is sent. Past days are archived model
forecasts, never observations. No predictor or heat calibration runs here.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
import hashlib,json,os,uuid,threading
from .public_weather import PublicWeatherStore,WeatherError,normalise,instant,utc,PERTH,LAT,LON,MAX_BYTES,PUBLIC_CONTRACT,PAST_DAYS,FORECAST_DAYS
from .uploads import write_json

API='https://api.open-meteo.com/v1/forecast'
TIMEOUT_SECONDS=20

def request_url():
    return API+'?'+urlencode({'latitude':LAT,'longitude':LON,'hourly':'temperature_2m','timezone':'Australia/Perth','timeformat':'iso8601','temperature_unit':'celsius','past_days':PAST_DAYS,'forecast_days':FORECAST_DAYS})

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise WeatherError('public_source_redirect_rejected')

def download(url):
    if url!=request_url():raise WeatherError('public_source_url_not_allowed')
    request=Request(url,headers={'User-Agent':'greenspark-q1-private-prototype/1.0','Accept':'application/json','Accept-Encoding':'identity'})
    try:
        with build_opener(NoRedirect).open(request,timeout=TIMEOUT_SECONDS) as response:
            if response.status!=200:raise WeatherError('public_source_http_status')
            if response.headers.get_content_type()!='application/json':raise WeatherError('public_source_not_json')
            if response.headers.get('Content-Encoding','identity')!='identity':raise WeatherError('public_source_encoding_not_allowed')
            content_length=response.headers.get('Content-Length')
            if content_length is not None and (not content_length.isdecimal() or int(content_length)>MAX_BYTES):raise WeatherError('public_source_oversize')
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise WeatherError('public_source_oversize')
            return raw,{'http_date':response.headers.get('Date'),'etag':response.headers.get('ETag'),'last_modified':response.headers.get('Last-Modified')}
    except HTTPError as e:raise WeatherError('public_source_http_'+str(e.code)) from e
    except (URLError,TimeoutError,OSError) as e:raise WeatherError('public_source_transport_failed') from e

def durable_bytes(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=raw:raise WeatherError('public_source_snapshot_integrity_failed')
        return
    temp=path.with_name('.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
        fd=os.open(path.parent,os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temp.unlink(missing_ok=True)

def wrap(payload,requested,retrieved,url,raw_sha,headers):
    if not isinstance(payload,dict) or payload.get('error'):raise WeatherError('public_source_invalid_response')
    if requested.tzinfo is None or retrieved.tzinfo is None or retrieved<requested:raise WeatherError('public_source_invalid_retrieval_time')
    day=requested.astimezone(PERTH).date()
    start=datetime.combine(day-timedelta(days=PAST_DAYS),datetime.min.time(),PERTH)
    end=datetime.combine(day+timedelta(days=FORECAST_DAYS),datetime.min.time(),PERTH)
    return {'schema_version':1,'dataset_kind':'live_forecast','q1_source_contract':PUBLIC_CONTRACT,'provider':'Open-Meteo','source_url':url,'requested_at':utc(requested),'retrieved_at':utc(retrieved),'model_issued_at':None,'model_issue_note':'Generic API does not expose model issuance. HTTP Date and generationtime_ms are not issuance.','raw_response_sha256':raw_sha,'response_metadata':headers,'use_profile':'private_noncommercial_prototype','licence_url':'https://open-meteo.com/en/licence','terms_url':'https://open-meteo.com/en/terms','localities':[{'location':{'name':'Fitzroy Crossing','postcode':'6765','latitude':LAT,'longitude':LON},'valid_from':start.isoformat(),'valid_until_exclusive':end.isoformat(),'forecast':payload}]}

class PublicSourceStore(PublicWeatherStore):
    network_fetch=True
    operation='refresh_bounded_public_model_context'
    def __init__(self,root,*,fetch=download,clock=None,**kwargs):
        super().__init__(root,**kwargs);self.refresh_lock=threading.Lock();self.fetch=fetch;self.clock=clock or (lambda:datetime.now(timezone.utc))
        if self.snapshot is None:super().refresh() # Existing authorised cache is the first fallback.
    def refresh(self):
        # Network latency must never hold the lock used by read-only views.
        if not self.refresh_lock.acquire(blocking=False):
            return {'succeeded':False,'error':'public_source_refresh_in_progress'}
        try:
            now=self.clock()
            if now.tzinfo is None:raise WeatherError('Public source clock needs UTC offset')
            with self.lock:
                current=self.view(now)
                if self.snapshot and self.last_error is None and self.snapshot.get('source_contract')==PUBLIC_CONTRACT and instant(self.snapshot['retrieved_at']).astimezone(PERTH).date()==now.astimezone(PERTH).date() and current['status']['state']=='fresh' and current['status']['complete_target_days']==7:
                    return {'succeeded':True,'cache_reused':True,'retrieved_at':self.snapshot['retrieved_at']}
            try:
                url=request_url();raw,headers=self.fetch(url);retrieved=self.clock()
                if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:raise WeatherError('public_source_oversize')
                try:payload=json.loads(raw)
                except (ValueError,UnicodeError) as e:raise WeatherError('public_source_invalid_json') from e
                sha=hashlib.sha256(raw).hexdigest();candidate=wrap(payload,now,retrieved,url,sha,headers)
                checked=normalise(candidate)
                # Nulls remain unavailable. Truncated/wrong-date sequences fail.
                durable_bytes(self.root/'downloads'/(sha+'.json'),raw)
                write_json(self.root/'network-latest.json',candidate)
                result=self.ingest(self.root/'network-latest.json',upstream_status=False)
                if not result['succeeded']:raise WeatherError('public_source_snapshot_activation_failed')
                with self.lock:
                    write_json(self.root/'source-attempt.json',{'requested_at':utc(now),'retrieved_at':utc(retrieved),'succeeded':True,'raw_response_sha256':sha,'source_contract':PUBLIC_CONTRACT,'source_url':url,'response_metadata':headers,'prior_data_kind':checked['warmup_kind']})
                return {**result,'cache_reused':False}
            except (OSError,ValueError,KeyError,TypeError) as e:
                with self.lock:
                    self.last_error=str(e) if isinstance(e,WeatherError) else 'public_source_local_or_validation_failure'
                    write_json(self.root/'attempt.json',{'succeeded':False,'error':self.last_error})
                    write_json(self.root/'source-attempt.json',{'requested_at':utc(now),'succeeded':False,'error':self.last_error,'source_url':request_url(),'last_good_preserved':self.snapshot is not None})
                    return {'succeeded':False,'error':self.last_error}
        finally:self.refresh_lock.release()
