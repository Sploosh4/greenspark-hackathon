"""Current synthetic application calculations; fixed model, bounded local work."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryFile
import hashlib,json,re,subprocess,sys,threading,time
from .uploads import UploadError,write_json,encoded,digest
from .public_weather import instant,PERTH,window
from .work import checkpoint

APP=Path(__file__).resolve().parents[1]
PYTHON=Path(sys.executable)
MAX_OUTPUT=64*1024*1024
CONTRACT='current-synthetic-demo/v1.0.1'

def fingerprint(review):return digest(encoded([(r['file'],r['sha256']) for r in review['input_validation']['files']]))

def run_frozen(payload,*,python=PYTHON,timeout=40):
    """A child reads only validated local files; cancellation releases its slot."""
    raw=encoded(payload)
    with TemporaryFile() as incoming,TemporaryFile() as output,TemporaryFile() as errors:
        incoming.write(raw);incoming.seek(0)
        child=subprocess.Popen([str(python),'-I',str(APP/'tools/current_inference.py')],stdin=incoming,stdout=output,stderr=errors,env={'PATH':'/usr/bin:/bin','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
        started=time.monotonic()
        try:
            while child.poll() is None:
                checkpoint()
                if time.monotonic()-started>timeout:raise UploadError('Current calculation timed out; previous data was kept.',503)
                if output.tell()>MAX_OUTPUT:raise UploadError('Current calculation exceeds its output limit.',413)
                time.sleep(.05)
            checkpoint()
            if child.returncode!=0:raise UploadError('The frozen current calculation could not finish. Existing data was kept.',503)
            output.seek(0);result=output.read(MAX_OUTPUT+1)
            if len(result)>MAX_OUTPUT:raise UploadError('Current calculation exceeds its output limit.',413)
            return json.loads(result)
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=2)

class CurrentCalculations:
    def __init__(self,root,weather,*,clock=None,runner=None,model_python=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        if self.root.is_symlink():raise ValueError('Unsafe current calculation directory')
        self.weather=weather;self.clock=clock or (lambda:datetime.now(timezone.utc));self.runner=runner or (lambda payload:run_frozen(payload,python=model_python or PYTHON));self.retry_after={};self.attempts={}
        self.lock=threading.RLock();self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='q1-current');self.pending=None;self.next_request=None;self.errors=OrderedDict();self.empty=OrderedDict();self.keys=[];self.last_good=None
        self.code=digest(encoded({name:hashlib.sha256((APP/name).read_bytes()).hexdigest() for name in ('tools/current_inference.py','prototype/current_calculation.py','prototype/public_weather.py','prototype/current_inputs.py','prototype/inputs.py','prototype/review.py')}))
        try:
            state=json.loads((self.root/'index.json').read_text());self.keys=[k for k in state['keys'] if re.fullmatch('[a-f0-9]{64}',k)][:4];self.last_good=state.get('last_good')
        except (OSError,ValueError,KeyError,TypeError):pass
    def key(self,base,context,now):
        return digest(encoded([CONTRACT,self.code,fingerprint(base),base['current_demo']['business_received_at'],context['snapshot_sha256'],str(now.astimezone(PERTH).date())]))
    def calculate(self,source,received_at,context,now):
        result=self.runner({'source_root':str(source),'received_at':received_at,'as_of':now.isoformat(),'weather':context})
        result['current_demo']['calculation_key']=self.key(result,context,now)
        result['current_demo']['business_fingerprint']=fingerprint(result)
        result['snapshot_id']='current-'+result['current_demo']['calculation_key']
        return result
    def build_with_context(self,source,*,received_at):
        now=self.clock();received=datetime.fromtimestamp(received_at,timezone.utc).isoformat()
        return self.calculate(source,received,self.weather.context_source(),now)
    def __call__(self,source):return self.build_with_context(source,received_at=self.clock().timestamp())
    def _read(self,key):
        if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{64}',key):return None
        path=self.root/(key+'.json')
        try:
            if path.is_symlink() or path.stat().st_size>MAX_OUTPUT:return None
            envelope=json.loads(path.read_text());review=envelope['review']
            if digest(encoded(review))!=envelope['sha256'] or review['current_demo']['calculation_key']!=key:return None
            return review
        except (OSError,ValueError,KeyError,TypeError):return None
    def _save(self,key,review):
        raw=encoded(review)
        if len(raw)>MAX_OUTPUT-1024:raise UploadError('Current snapshot exceeds64MiB',413)
        with self.lock:
            existing=[p for p in self.root.glob('*.json') if re.fullmatch('[a-f0-9]{64}',p.stem)]
            if any(p.is_symlink() or p.stat().st_size>MAX_OUTPUT for p in existing):raise UploadError('Unsafe current-cache entry; existing data was kept',503)
            # Count interrupted index writes too. Unknown material is preserved;
            # only valid app-generated derivatives may be evicted for quota.
            protected={self.last_good,self.keys[0] if self.keys else None,key}
            while len([p for p in existing if p.stem!=key])>=4:
                victim=next((p for p in existing if p.stem not in protected and self._read(p.stem) is not None),None)
                if victim is None:raise UploadError('Current result cache is full; existing data was kept',413)
                victim.unlink();existing.remove(victim);self.keys=[k for k in self.keys if k!=victim.stem]
            write_json(self.root/(key+'.json'),{'review':review,'sha256':digest(raw)})
            previous=list(self.keys)
            if review['current_demo']['available_customers']:self.last_good=key
            self.keys=list(dict.fromkeys([key]+([self.last_good] if self.last_good else [])+self.keys))[:4]
            write_json(self.root/'index.json',{'keys':self.keys,'last_good':self.last_good})
            # Only this cache's indexed, regenerable derivatives are evicted.
            # Original uploads, stored upload reviews and recovery never enter it.
            for old in previous:
                if old not in self.keys:(self.root/(old+'.json')).unlink(missing_ok=True)
    def _future(self,base,key,context,now):
        try:
            result=self.calculate(base['input_validation']['source_root'],base['current_demo']['business_received_at'],context,now)
            if result['current_demo']['calculation_key']!=key:raise ValueError('Calculation context changed')
            self._save(key,result)
            with self.lock:self.errors.pop(key,None);self.attempts.pop(key,None);self.retry_after.pop(key,None)
        except Exception:
            with self.lock:
                self.errors[key]='current_calculation_failed';self.errors.move_to_end(key)
                self.attempts[key]=self.attempts.get(key,0)+1;self.retry_after[key]=time.monotonic()+1
                while len(self.errors)>4:
                    old,_=self.errors.popitem(last=False);self.retry_after.pop(old,None);self.attempts.pop(old,None)
        finally:
            with self.lock:
                self.pending=None;next_request=self.next_request;self.next_request=None
            if next_request:self.schedule(*next_request)
    def schedule(self,base,context,now,key):
        with self.lock:
            if self.pending is not None:
                if self.pending!=key:self.next_request=(deepcopy(base),context,now,key)
                return
            if key in self.errors and (self.attempts.get(key,0)>=2 or time.monotonic()<self.retry_after.get(key,0)):return
            self.errors.pop(key,None)
            self.pending=key
            try:self.worker.submit(self._future,deepcopy(base),key,context,now)
            except RuntimeError:self.pending=None
    def _unavailable(self,base,context,now,key,reason):
        with self.lock:
            if (key,reason) in self.empty:return deepcopy(self.empty[key,reason])
        result=deepcopy(base);d=now.astimezone(PERTH).date();event={'id':'CURRENT-'+str(d),'label':'7-day usage scenario','start':str(d),'end':str(d+timedelta(days=6)),'duration':7,'category':'Fixed current-date synthetic scenario'}
        result.update(review_date=str(d),history_cutoff=str(d-timedelta(days=1)),horizon_start=event['start'],horizon_end=event['end'],events=[event],weather=[])
        snapshot=context['snapshot'];available=snapshot is not None and instant(context['adapter_loaded_at'])<=now
        if available:
            hours={r['valid_at']:r['temperature_c'] for r in snapshot['hourly']}
            labels=sorted({instant(r['valid_at']).astimezone(PERTH).date() for r in snapshot['hourly']})
            for label in labels:
                begin=datetime.combine(label,datetime.min.time(),PERTH);values=[hours.get((begin+timedelta(hours=i)).isoformat()) for i in range(24)]
                if all(v is not None for v in values) and str(label)<=event['end']:result['weather'].append({'date':str(label),'postcode':'6765','max_temp':max(values),'min_temp':min(values)})
        for row in result['customers']:
            if row.get('latest_reported_usage_date'):row['reporting_lag_days']=(d-instant(row['latest_reported_usage_date']+'T00:00:00+08:00').date()).days
            row['predictions']=[{'event_id':event['id'],'duration':7,'baseline':None,'predicted':None,'increase':None,'event_total':None,'reason':reason,'method_id':'frozen-v3-M5-current-synthetic/v1','comparison':{'provider':'S1','predicted':None,'increase':None,'event_total':None}}]
        result['current_demo'].update(calculation_key=key,available_customers=0,current_reason=reason,weather_snapshot_sha256=context['snapshot_sha256'],inference_as_of=now.isoformat(),weather_requested_at=snapshot.get('requested_at') if snapshot else None,weather_retrieved_at=snapshot.get('retrieved_at') if snapshot else None,weather_adapter_loaded_at=context['adapter_loaded_at'],provider_grid=snapshot.get('provider_grid') if snapshot else None,provider_issue_at=None)
        result['current_demo']['reporting_lag_days']=sorted({r['reporting_lag_days'] for r in result['customers'] if r.get('reporting_lag_days') is not None})
        result['snapshot_id']='current-'+key
        with self.lock:
            self.empty[key,reason]=deepcopy(result)
            while len(self.empty)>4:self.empty.popitem(last=False)
        return result
    def _decorate(self,review,base):
        result=deepcopy(review);revision='current-'+digest(encoded([base['batch_revision'],review['current_demo']['calculation_key'],digest(encoded(review))]))
        result.update(data_mode='upload',batch_id=base['batch_id'],business_revision=base['batch_revision'],batch_revision=revision,snapshot_id=revision)
        return result
    def view(self,base):
        if not base.get('current_demo'):return base
        now=self.clock();context=self.weather.context_source();key=self.key(base,context,now)
        status=window(context['snapshot'],now,context['last_error'])['status']
        if status['state']!='fresh':return self._decorate(self._unavailable(base,context,now,key,'forecast_stale_missing_or_refresh_failed'),base)
        if instant(context['adapter_loaded_at'])>now:return self._decorate(self._unavailable(base,context,now,key,'forecast_loaded_after_review'),base)
        with self.lock:cached=self._read(key)
        if cached is None and base['current_demo']['calculation_key']==key:cached=base
        if cached is None:
            self.schedule(base,context,now,key)
            cached=self._unavailable(base,context,now,key,self.errors.get(key,'recalculating_current_scenario'))
        return self._decorate(cached,base)
    def refresh_active(self,store):
        try:
            base=store.view()
            if base.get('current_demo'):self.view(base)
        except UploadError:pass
    def retry(self,base):
        context=self.weather.context_source();now=self.clock();key=self.key(base,context,now)
        with self.lock:
            if time.monotonic()<self.retry_after.get(key,0):return self.status()
            self.errors.pop(key,None);self.attempts.pop(key,None)
        self.schedule(base,context,now,key);return self.status()
    def status(self):
        with self.lock:return {'running':self.pending is not None,'pending_key':self.pending,'last_error':next(reversed(self.errors.values()),None) if self.errors else None}
    def close(self):self.worker.shutdown(wait=True,cancel_futures=True)
