"""One in-process daily public-weather owner; no OS timer or credentials."""
from datetime import datetime,time,timedelta,timezone
from pathlib import Path
import argparse,json,threading,uuid
import re
from .public_weather import PublicWeatherStore,PERTH,instant,utc
from .uploads import write_json

def next_daily(now,local_time):
    if now.tzinfo is None:raise ValueError('Job time needs UTC offset')
    if not isinstance(local_time,str) or not re.fullmatch(r'\d{2}:\d{2}',local_time):raise ValueError('Daily time must be HH:MM')
    try:hour,minute=map(int,local_time.split(':'));chosen=time(hour,minute)
    except (ValueError,AttributeError):raise ValueError('Daily time must be HH:MM')
    local=now.astimezone(PERTH);result=datetime.combine(local.date(),chosen,PERTH)
    return result if result>now else result+timedelta(days=1)

class DailyCacheJob:
    def __init__(self,store,local_time='06:00',*,clock=None,poll_seconds=30,configured_state=None):
        self.store=store;self.local_time=local_time;self.clock=clock or (lambda:datetime.now(timezone.utc));next_daily(self.clock(),local_time)
        if not 0<poll_seconds<=30:raise ValueError('Weather polling interval outside bound')
        self.poll_seconds=poll_seconds;self.lock=threading.RLock();self.tick_lock=threading.Lock();self.lifecycle_lock=threading.Lock();self.state={};self.worker=None;self.stop_event=None;self.refresh_running=False;self.persistence_error=None;self.configuration_sync_warning=False
        try:
            path=store.root/'job.json'
            if path.stat().st_size>65536:raise ValueError('Weather schedule state exceeds bound')
            state=json.loads(path.read_text())
            if isinstance(state,dict):self.state=state
        except (OSError,ValueError):pass
        # The atomic settings record is authoritative if a process stopped
        # between committing configuration and writing advisory job status.
        if isinstance(configured_state,dict) and configured_state.get('daily_time')==local_time and re.fullmatch('[a-f0-9]{32}',str(configured_state.get('configuration_id',''))):
            try:
                instant(configured_state['next_run_at'])
                if self.state.get('configuration_id')!=configured_state['configuration_id']:self.state=dict(configured_state)
            except (KeyError,ValueError):pass
        if self.state.get('daily_time')!=local_time:self.state={}
    def status(self):
        with self.lock:
            return {**self.state,'daily_time':self.local_time,'timezone':'Australia/Perth','next_run_at':self.state.get('next_run_at') or utc(next_daily(self.clock(),self.local_time)),
                    'enabled':bool(self.worker and self.worker.is_alive()),'running':self.refresh_running,
                    'operation':getattr(self.store,'operation','ingest_existing_public_cache'),'source_mode':'public' if getattr(self.store,'network_fetch',False) else 'cache',
                    'retry_minutes':15,'runs_while_app_is_running':True,'state_persisted':self.persistence_error is None,'persistence_error':self.persistence_error,'configuration_sync_warning':self.configuration_sync_warning}
    def configure(self,local_time,now=None,*,commit=None):
        now=now or self.clock();due=next_daily(now,local_time)
        with self.lock:
            candidate={**self.state,'daily_time':local_time,'timezone':'Australia/Perth','next_run_at':utc(due),'configuration_id':uuid.uuid4().hex}
            commit_result=None
            if commit is None:
                # Direct local configuration has one durable record.
                target=self.store.root/'job.json'
                try:write_json(target,candidate)
                except OSError:
                    if target.stat().st_size>65536 or json.loads(target.read_text())!=candidate:raise
                    commit_result={'sync_warning':True}
            else:
                # The caller atomically saves settings and this exact schedule
                # together. If it fails, no scheduler state has changed.
                commit_result=commit(candidate)
            self.configuration_sync_warning=bool(commit_result and commit_result.get('sync_warning'))
            self.local_time=local_time;self.state=candidate;self.persistence_error=None
            if commit is not None:
                try:write_json(self.store.root/'job.json',candidate)
                except OSError:self.persistence_error='weather_schedule_status_not_persisted'
        return self.status()
    def tick(self,now=None,force=False):
        explicit_now=now is not None;now=now or self.clock()
        if now.tzinfo is None:raise ValueError('Job time needs UTC offset')
        if not self.tick_lock.acquire(blocking=False):return {**self.status(),'ran':False}
        try:
            with self.lock:
                due=self.state.get('next_run_at')
                try:due_at=instant(due) if due else None
                except ValueError:due_at=None
                if not force and due_at and now<due_at:return {**self.state,'ran':False}
                self.refresh_running=True;configuration_id=self.state.get('configuration_id')
            try:result=self.store.refresh()
            except (OSError,ValueError,KeyError,TypeError):result={'succeeded':False,'error':'weather_refresh_failed'}
            with self.lock:
                completed=now if explicit_now else self.clock()
                changed=self.state.get('configuration_id')!=configuration_id
                next_run=instant(self.state['next_run_at']) if changed else next_daily(completed,self.local_time) if result['succeeded'] else completed+timedelta(minutes=15)
                candidate={**({'configuration_id':self.state['configuration_id']} if self.state.get('configuration_id') else {}),'last_attempt_at':utc(now),'last_attempt_succeeded':result['succeeded'],'last_error':result.get('error'),'next_run_at':utc(next_run),'daily_time':self.local_time,'timezone':'Australia/Perth','operation':getattr(self.store,'operation','ingest_existing_public_cache'),'network_fetch':getattr(self.store,'network_fetch',False) and not result.get('cache_reused',False),'cache_reused':result.get('cache_reused',False)}
                self.state=candidate;self.persistence_error=None
                try:write_json(self.store.root/'job.json',candidate)
                except OSError:self.persistence_error='weather_schedule_status_not_persisted'
                return {**self.state,'ran':True}
        finally:
            with self.lock:self.refresh_running=False
            self.tick_lock.release()
    def start(self,stop=None,*,force_initial=False):
        with self.lifecycle_lock:
            if self.worker and self.worker.is_alive():return self.worker
            self.stop_event=stop or threading.Event()
            if self.stop_event.is_set():raise ValueError('Weather worker stop event is already set')
            self.worker=threading.Thread(target=self.run,args=(self.stop_event,),kwargs={'force_initial':force_initial},name='q1-public-weather',daemon=True)
            self.worker.start();return self.worker
    def stop(self,timeout=25):
        with self.lifecycle_lock:
            if self.stop_event:self.stop_event.set()
            worker=self.worker
        if worker and worker is not threading.current_thread():worker.join(timeout)
        return not worker or not worker.is_alive()
    def run(self,stop,*,force_initial=False):
        # A missing persisted source needs recovery; a valid source preserves its
        # due/retry time across restarts instead of forcing a second request.
        force_initial=force_initial or (hasattr(self.store,'snapshot') and self.store.snapshot is None and self.state.get('last_attempt_succeeded') is True)
        while not stop.is_set():
            try:self.tick(force=force_initial)
            except (OSError,ValueError):pass
            force_initial=False
            stop.wait(self.poll_seconds)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'runtime/public-weather');parser.add_argument('--daily-time',default='06:00');parser.add_argument('--source-cache',type=Path);parser.add_argument('--once',action='store_true');args=parser.parse_args()
    store=PublicWeatherStore(args.root,**({'source_cache':args.source_cache} if args.source_cache else {}));job=DailyCacheJob(store,args.daily_time)
    if args.once:print(json.dumps(job.tick(force=True)))
    else:job.run(threading.Event())
