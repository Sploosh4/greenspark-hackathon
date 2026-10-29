"""Actual generic handlers, ephemeral identity and transport; no port or live swap."""
import copy,secrets,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
from dataclasses import replace
import test_synthetic_financial as synthetic_fixture
import test_auth_integration as auth_fixture
import test_financial_http as financial_fixture
from test_upload_jobs import DeferredExecutor
from local_auth import Account,AuthService,hash_password
from business_upload import UploadStages,UploadJobs
from financial_intake import FinancialJobs
from source_adapter import canonical,SnapshotStore,SourceError

class SyntheticHTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.password=secrets.token_urlsafe(24);cls.record=hash_password(cls.password)
 def setUp(self):
  synthetic_fixture.SyntheticRecovery.setUp(self);self.accounts={'manager':Account('ephemeral-synthetic-q3','manager','manager',self.record)};self.auth=AuthService('q3',self.accounts.get);self.executor=DeferredExecutor();gate=threading.Lock();uploads=UploadStages(self.store,self.f.trusted,lambda:self.base_now)
  import test_source_adapter
  self.base_now=test_source_adapter.NOW
  self.server=SimpleNamespace(auth=self.auth,server_port=8797,snapshots=self.store,uploads=uploads,financial_uploads=self.stages,upload_jobs=UploadJobs(uploads,self.executor,gate),financial_jobs=FinancialJobs(self.stages,self.executor,gate),upload_slot=threading.BoundedSemaphore(1),validation_gate=gate)
 tearDown=synthetic_fixture.SyntheticRecovery.tearDown
 call=auth_fixture.ActualQ3Auth.call
 login=auth_fixture.ActualQ3Auth.login
 multipart=financial_fixture.FinancialHTTP.multipart
 submit=financial_fixture.FinancialHTTP.submit
 def test_manager_can_stage_review_replace_and_restart_fresh_unpinned_package(self):
  receipt,headers=self.submit();self.assertEqual(receipt['status'],202);before=self.store.read()['generation'];self.executor.run();ready=self.call('GET','/api/q3/financial/stage-status?id='+receipt['body']['jobId'],headers=headers)[0];self.assertEqual(ready['body']['state'],'ready');s=ready['body']['result'];self.assertEqual(s['proposedSupport']['schemaVersion'],3);self.assertEqual(self.store.read()['generation'],before)
  wrong=self.call('POST','/api/q3/financial/replace',canonical({'stageId':s['stageId'],'baseGeneration':'0'*64}),headers)[0];self.assertEqual(wrong['status'],409)
  applied=self.call('POST','/api/q3/financial/replace',canonical({'stageId':s['stageId'],'baseGeneration':s['baseGeneration']}),headers)[0];self.assertEqual(applied['status'],200);self.assertEqual(applied['body']['data']['business']['financialSupport']['schemaVersion'],3)
  restored=SnapshotStore(self.inputs,self.runtime,lambda:self.base_now).read();self.assertEqual(restored['data'],applied['body']['data'])
 def test_guard_precedes_generic_validator_and_never_consumes_unauthorised_body(self):
  with patch('synthetic_financial.derive_synthetic_context') as derive:
   for headers,status in [({'X-Role':'manager'},401),({**self.login(),'X-Team-Connect-CSRF':'wrong'},403)]:
    result=self.call('POST','/api/q3/financial/stage',headers={**headers,'Content-Length':'1000000'},deny_read=True)[0];self.assertEqual(result['status'],status)
   derive.assert_not_called()
  headers=self.login();self.accounts['manager']=replace(self.accounts['manager'],role='officer');self.assertEqual(self.call('POST','/api/q3/financial/stage',headers=headers,deny_read=True)[0]['status'],401)
 def test_uploaded_aggregate_cannot_replace_without_server_created_stage(self):
  headers=self.login();result=self.call('POST','/api/q3/financial/replace',canonical({'stageId':'invented','baseGeneration':self.base['generation'],'proposedSupport':{'schemaVersion':3}}),headers)[0];self.assertEqual(result['status'],409);self.assertEqual(self.store.read()['generation'],self.base['generation'])
 def test_rehashed_bad_contents_fail_job_and_retain_snapshot(self):
  metadata=__import__('json').loads(self.files['manifest']);metadata['parameters']['count']+=1;self.files['manifest']=canonical(metadata);before=(self.runtime/'last-good.json').read_bytes();receipt,headers=self.submit();self.assertEqual(receipt['status'],202);self.executor.run();failed=self.call('GET','/api/q3/financial/stage-status?id='+receipt['body']['jobId'],headers=headers)[0];self.assertEqual(failed['body']['state'],'failed');self.assertEqual((self.runtime/'last-good.json').read_bytes(),before)
