import copy,threading,unittest
from datetime import timedelta
import test_source_adapter as fixtures
from test_business_upload import file_bytes,customer,usage,CUSTOMER_HEADERS,USAGE_HEADERS
from business_upload import UploadStages,UploadJobs
from source_adapter import SourceError

class DeferredExecutor:
 def __init__(self):self.pending=[]
 def submit(self,f,*args):self.pending.append((f,args))
 def run(self):
  f,args=self.pending.pop(0);f(*args)
 def shutdown(self,**kwargs):pass

class Jobs(unittest.TestCase):
 tearDown=fixtures.Sources.tearDown
 def setUp(self):
  fixtures.Sources.setUp(self);self.old=self.store.read();self.now=fixtures.NOW;self.stages=UploadStages(self.store,self.old['data']['business'],lambda:self.now);self.executor=DeferredExecutor();self.jobs=UploadJobs(self.stages,self.executor)
  self.customers=file_bytes(CUSTOMER_HEADERS,[customer('A')]);self.usage=file_bytes(USAGE_HEADERS,[usage('A')])
 def submit(self):return self.jobs.submit(self.customers,self.usage,False,True)
 def test_acceptance_is_fast_receipt_without_validation_or_active_change(self):
  r=self.submit();self.assertEqual(r['state'],'accepted');self.assertEqual(r['validation'],'pending');self.assertNotIn('result',r);self.assertEqual(self.jobs.status(r['jobId'])['state'],'accepted');self.assertEqual(self.store.read()['generation'],self.old['generation']);self.assertEqual(len(self.executor.pending),1)
 def test_single_worker_backpressure_and_ready_requires_explicit_replace(self):
  r=self.submit()
  with self.assertRaisesRegex(SourceError,'another_validation'):self.submit()
  self.executor.run();ready=self.jobs.status(r['jobId']);self.assertEqual(ready['state'],'ready');self.assertEqual(ready['result']['proposed']['totalAccounts'],1);self.assertEqual(self.store.read()['generation'],self.old['generation'])
  stage=ready['result'];self.stages.replace(stage['stageId'],stage['baseGeneration']);self.jobs.discard_receipt(stage['stageId']);self.assertEqual(self.store.read()['data']['business']['totalAccounts'],1)
  with self.assertRaisesRegex(SourceError,'missing_or_expired'):self.jobs.status(r['jobId'])
 def test_bad_schema_fails_asynchronously_never_creates_replaceable_stage(self):
  self.customers=b'wrong,columns\n1,2\n';r=self.submit();self.executor.run();p=self.jobs.status(r['jobId']);self.assertEqual(p['state'],'failed');self.assertEqual(p['error'],'csv_headers_must_match_reviewed_schema');self.assertNotIn('result',p);self.assertEqual(self.stages.stages,{});self.assertEqual(self.store.read()['generation'],self.old['generation'])
 def test_expiry_discards_proposals_and_restart_loses_receipts(self):
  r=self.submit();self.executor.run();self.now+=timedelta(minutes=31)
  with self.assertRaisesRegex(SourceError,'missing_or_expired'):self.jobs.status(r['jobId'])
  self.assertEqual(self.stages.stages,{})
  new=UploadJobs(self.stages,DeferredExecutor())
  with self.assertRaisesRegex(SourceError,'missing_or_expired'):new.status(r['jobId'])
 def test_four_proposals_bounded_and_discard_releases_capacity(self):
  ready=[]
  for _ in range(4):r=self.submit();self.executor.run();ready.append(self.jobs.status(r['jobId']))
  with self.assertRaisesRegex(SourceError,'too_many_validation'):self.submit()
  stage=ready[0]['result'];self.stages.discard(stage['stageId']);self.jobs.discard_receipt(stage['stageId']);self.submit()
 def test_failed_receipts_do_not_permanently_lock_new_uploads(self):
  self.customers=b'bad\n'
  for _ in range(5):self.submit();self.executor.run()
  self.assertEqual(len(self.jobs.jobs),4)
 def test_missing_declaration_bad_receipt_and_worker_start_failure(self):
  with self.assertRaises(SourceError):self.jobs.submit(self.customers,self.usage,False,False)
  with self.assertRaises(SourceError):self.jobs.status('../x')
  class Broken:
   def submit(self,*a):raise RuntimeError('test')
  self.jobs.executor=Broken()
  with self.assertRaisesRegex(SourceError,'worker_unavailable'):self.submit()
  self.assertFalse(self.jobs.running);self.assertEqual(self.jobs.jobs,{})
 def test_real_worker_completes_without_listener(self):
  real=UploadJobs(self.stages);r=real.submit(self.customers,self.usage,False,True);real.close();self.assertEqual(real.status(r['jobId'])['state'],'ready');self.assertNotIn('customer_id',str(real.jobs))
