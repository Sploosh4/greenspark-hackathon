"""Bounded asynchronous upload validation. Activation remains explicit."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import copy,threading
from .uploads import safe_id,digest,encoded,UploadError

class UploadJobs:
    def __init__(self,store):
        self.store=store;self.lock=threading.RLock();self.jobs=OrderedDict();self.inflight=set();self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='q1-upload')
    def status(self,operation):
        safe_id(operation)
        with self.lock:
            job=self.jobs.get(operation)
            if job is None:raise UploadError('Upload job is no longer available. Reload the current data before retrying.',404)
            if job['state']=='ready' and not self.store.stage_available(operation):
                job.update(state='expired',error='The checked upload expired. Current data was kept; select the files again.');job.pop('receipt',None)
            return copy.deepcopy({k:v for k,v in job.items() if k!='fingerprint'})
    def submit(self,parts,operation,expected_revision):
        safe_id(operation);fingerprint=digest(encoded([(name,digest(raw)) for name,raw in parts]))
        with self.lock:
            if operation in self.jobs:
                job=self.jobs[operation]
                if job['fingerprint']!=fingerprint or job['expected_revision']!=expected_revision:raise UploadError('Operation identifier reused with different input/version',409)
                return self.status(operation)
            if len(self.inflight)>=2:raise UploadError('Two uploads are still finishing. Wait before checking another batch.',429)
            if expected_revision!=self.store.status()['revision']:raise UploadError('Uploaded data changed. Reload before checking another batch.',409)
            self.jobs[operation]={'request_id':operation,'expected_revision':expected_revision,'state':'queued','fingerprint':fingerprint}
            while len(self.jobs)>128:
                expired=next((key for key,value in self.jobs.items() if key not in self.inflight and value['state'] not in ('queued','running') and self.store.retire(key)),None)
                if expired is None:break
                del self.jobs[expired]
            self.inflight.add(operation)
            try:self.executor.submit(self._run,parts,operation,expected_revision).add_done_callback(lambda future:self._finished(operation))
            except RuntimeError:
                self.inflight.discard(operation);self.jobs.pop(operation,None);raise UploadError('Upload worker is stopping',503)
            return self.status(operation)
    def _finished(self,operation):
        with self.lock:self.inflight.discard(operation)
    def _run(self,parts,operation,revision):
        with self.lock:
            if self.jobs[operation]['state']=='cancelled':return
            self.jobs[operation]['state']='running'
        try:
            receipt=self.store.stage(parts,operation,revision)
            with self.lock:
                if self.jobs[operation]['state']!='cancelled':self.jobs[operation].update(state='ready',receipt=receipt)
        except Exception as error:
            with self.lock:
                if self.jobs[operation]['state']!='cancelled':self.jobs[operation].update(state='failed',error=str(error) if isinstance(error,UploadError) else 'Validation or calculation could not finish. Current data was kept.')
    def cancel(self,operation):
        result=self.store.cancel(operation)
        with self.lock:
            if operation in self.jobs:self.jobs[operation].update(state='cancelled')
        return result
    def close(self):self.executor.shutdown(wait=True,cancel_futures=True)
