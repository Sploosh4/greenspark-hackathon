"""Actual handlers, in-process transport, ephemeral managers only; no listener."""
import io,json,secrets,threading,unittest
from dataclasses import replace
from email.message import Message
from types import SimpleNamespace
import test_financial_intake as fixture
import test_auth_integration as auth_fixture
import test_upload_http as http_fixture
from test_upload_jobs import DeferredExecutor
from business_upload import UploadStages,UploadJobs
from financial_intake import FinancialJobs,PART_FILES,MAX_FINANCIAL_UPLOAD
from local_auth import Account,AuthService,hash_password
from source_adapter import canonical

class FinancialHTTP(fixture.FinancialCase):
 @classmethod
 def setUpClass(cls):cls.password=secrets.token_urlsafe(24);cls.record=hash_password(cls.password)
 def setUp(self):
  super().setUp();self.accounts={'manager':Account('ephemeral-q3-financial','manager','manager',self.record)};self.auth=AuthService('q3',self.accounts.get);self.executor=DeferredExecutor();gate=threading.Lock()
  uploads=UploadStages(self.store,self.trusted,lambda:self.now)
  self.server=SimpleNamespace(auth=self.auth,server_port=8797,snapshots=self.store,uploads=uploads,financial_uploads=self.stages,upload_jobs=UploadJobs(uploads,self.executor,gate),financial_jobs=FinancialJobs(self.stages,self.executor,gate),upload_slot=threading.BoundedSemaphore(1),validation_gate=gate)
 call=auth_fixture.ActualQ3Auth.call
 login=auth_fixture.ActualQ3Auth.login
 def multipart(self,extra=None,omit=None):
  boundary='q3-financial-handler-fixture';chunks=[]
  for key,name in PART_FILES.items():
   if key!=omit:chunks.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"; filename="'+name+'"\r\n\r\n').encode()+self.files[key]+b'\r\n')
  for key,raw in [('synthetic',b'true'),('baseGeneration',self.base['generation'].encode())]+(extra or []):chunks.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n').encode()+raw+b'\r\n')
  return b''.join(chunks)+('--'+boundary+'--\r\n').encode(),'multipart/form-data; boundary='+boundary
 def submit(self):
  headers=self.login();body,kind=self.multipart();r,_=self.call('POST','/api/q3/financial/stage',body,{**headers,'Content-Type':kind});return r,headers
 def test_manager_accepted_status_review_explicit_replace_and_read(self):
  r,headers=self.submit();self.assertEqual(r['status'],202);receipt=r['body'];self.assertEqual(self.store.read()['generation'],self.base['generation']);pending,_=self.call('GET','/api/q3/financial/stage-status?id='+receipt['jobId'],headers=headers);self.assertEqual(pending['body']['state'],'accepted');self.executor.run();ready,_=self.call('GET','/api/q3/financial/stage-status?id='+receipt['jobId'],headers=headers);self.assertEqual(ready['body']['state'],'ready');stage=ready['body']['result']
  r,_=self.call('POST','/api/q3/financial/replace',canonical({'stageId':stage['stageId'],'baseGeneration':stage['baseGeneration']}),headers);self.assertEqual(r['status'],200);self.assertEqual(r['body']['data']['business']['financialSupport']['areas'][0]['activeAccountsInEitherSupport'],1)
  r,_=self.call('GET','/api/q3/snapshot',headers=headers);self.assertIn('financialSupport',r['body']['data']['business'])
 def test_no_session_or_forged_role_denied_before_body_or_status_read(self):
  for path in ['/api/q3/financial/stage','/api/q3/financial/replace','/api/q3/financial/discard']:
   r,_=self.call('POST',path,headers={'Content-Length':'32000000','Origin':'http://127.0.0.1:8797','X-Role':'manager'},deny_read=True);self.assertEqual(r['status'],401)
  r,_=self.call('GET','/api/q3/financial/stage-status?id='+('a'*32),headers={'X-Role':'manager'});self.assertEqual(r['status'],401)
 def test_csrf_origin_changed_role_and_q1_cookie_cannot_mutate(self):
  headers=self.login()
  for edit in [{'X-Team-Connect-CSRF':'wrong'},{'Origin':'http://localhost:8797'},{'Origin':'https://other.example'}]:
   r,_=self.call('POST','/api/q3/financial/stage',headers={**headers,**edit},deny_read=True);self.assertEqual(r['status'],403)
  q1={**headers,'Cookie':headers['Cookie'].replace('tc_q3_session=','tc_q1_session=')};self.assertEqual(self.call('POST','/api/q3/financial/stage',headers=q1,deny_read=True)[0]['status'],401)
  self.accounts['manager']=replace(self.accounts['manager'],role='officer');self.assertEqual(self.call('POST','/api/q3/financial/stage',headers=headers,deny_read=True)[0]['status'],401)
 def test_partial_duplicate_parts_and_wrong_filenames_rejected_before_job(self):
  headers=self.login()
  for body,kind in [self.multipart(omit='support'),self.multipart(extra=[('synthetic',b'true')]),self.multipart()]:
   if body==self.multipart()[0]:body=body.replace(b'filename="customers.csv"',b'filename="other.csv"',1)
   r,_=self.call('POST','/api/q3/financial/stage',body,{**headers,'Content-Type':kind});self.assertEqual(r['status'],422)
  self.assertFalse(self.server.financial_jobs.jobs);self.assertEqual(self.store.read()['generation'],self.base['generation'])
 def test_request_limit_and_ambiguous_framing_before_read(self):
  headers=self.login()
  for edits,status in [({'Content-Length':str(MAX_FINANCIAL_UPLOAD+1)},413),({'Content-Length':'not-a-number'},422),({'Transfer-Encoding':'chunked','Content-Length':'32'},413)]:
   r,_=self.call('POST','/api/q3/financial/stage',headers={**headers,**edits},deny_read=True);self.assertEqual(r['status'],status)
 def test_invalid_csv_returns_failed_status_and_no_proposal(self):
  self.files['support']=b'bad';r,headers=self.submit();self.assertEqual(r['status'],202);self.executor.run();p,_=self.call('GET','/api/q3/financial/stage-status?id='+r['body']['jobId'],headers=headers);self.assertEqual(p['body']['state'],'failed');self.assertNotIn('result',p['body']);self.assertEqual(self.store.read()['generation'],self.base['generation'])
 def test_discard_and_stale_generation_keep_last_good(self):
  r,headers=self.submit();self.executor.run();p,_=self.call('GET','/api/q3/financial/stage-status?id='+r['body']['jobId'],headers=headers);stage=p['body']['result']
  r,_=self.call('POST','/api/q3/financial/replace',canonical({'stageId':stage['stageId'],'baseGeneration':'f'*64}),headers);self.assertEqual(r['status'],409)
  r,_=self.call('POST','/api/q3/financial/discard',canonical({'stageId':stage['stageId']}),headers);self.assertEqual(r['status'],200);self.assertFalse(self.server.financial_jobs.jobs);self.assertEqual(self.store.read()['generation'],self.base['generation'])
 def test_shared_backpressure_rejects_second_upload_before_body_read(self):
  r,headers=self.submit();self.assertEqual(r['status'],202)
  for path in ['/api/q3/financial/stage','/api/q3/business/stage']:
   p,_=self.call('POST',path,headers={**headers,'Content-Length':'1000'},deny_read=True);self.assertEqual(p['status'],409)
  self.executor.run()
