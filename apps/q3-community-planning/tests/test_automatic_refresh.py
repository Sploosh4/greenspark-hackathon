import json,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from automatic_refresh import once,plan,request,atomic_json,timer_text
from source_adapter import digest,SourceError

CONFIG={'schemaVersion':1,'enabled':True,'releaseDayUTC':6,'releaseLagDays':3,'checkIntervalHours':24}
NOW=datetime(2026,11,9,12,tzinfo=timezone.utc)
RAW=b'GRIBbounded fixture7777'

class Store:
 def __init__(self,issue='2026-10'):self.issue=issue;self.notices=[];self.generation='original';self.business=46500
 def read(self):return {'data':{'mean':{'issueDate':self.issue+'-01'}},'generation':self.generation}
 def record_climate_failure(self,issue,code):self.notices.append((issue,code))
class Remote:
 def __init__(self,status='successful',fail=False):self.request_id='bounded-job';self.json={'status':status};self.fail=fail
 def download(self,path):
  if self.fail:raise RuntimeError('secret signed-url must never be printed')
  Path(path).write_bytes(RAW)
class Client:
 def __init__(self,status='successful',fail=None):self.status=status;self.fail=fail;self.submitted=[];self.resumed=[]
 def apply_constraints(self,dataset,spec):
  if self.fail=='constraints':raise RuntimeError('secret token')
 def submit(self,dataset,spec):
  self.submitted.append(dataset)
  if self.fail=='submit':raise RuntimeError('secret token')
  return Remote(self.status,self.fail=='download')
 def get_remote(self,key):self.resumed.append(key);return Remote(self.status)

class AutomaticRefresh(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'state';self.store=Store();self.client=Client();self.promotions=[]
 def local(self,path,store,**kw):
  manifest=json.loads(Path(path).read_text());self.promotions.append((manifest,kw));store.issue=manifest['issueMonth'];store.generation='new';return {'action':'promoted_local_pair','promoted':True,'generation':'new'}
 def run_once(self,now=NOW,config=CONFIG):return once(self.store,config,self.root,now=now,client_factory=lambda:self.client,local_check=self.local)
 def test_latest_skips_before_state_or_credentials(self):
  self.store.issue='2026-11';result=self.run_once();self.assertFalse(result['networkRequest']);self.assertFalse(self.root.exists());self.assertEqual(self.client.submitted,[])
 def test_disabled_and_three_day_lag(self):
  self.assertEqual(self.run_once(config={**CONFIG,'enabled':False})['action'],'disabled')
  self.assertEqual(self.run_once(NOW.replace(day=8,hour=23))['action'],'wait_for_release_plus_lag');self.assertFalse(self.root.exists())
  self.assertEqual(plan(NOW,'2026-11',CONFIG)['nextEligibleCheckAt'],'2026-12-09T12:00:00+00:00')
 def test_configuration_fails_closed(self):
  for change in [{'releaseLagDays':-1},{'releaseDayUTC':10},{'checkIntervalHours':0},{'enabled':1}]:
   with self.subTest(change=change),self.assertRaises(SourceError):self.run_once(config={**CONFIG,**change})
 def test_exact_request_and_pair_promotion(self):
  result=self.run_once();self.assertTrue(result['promoted']);self.assertEqual(len(self.client.submitted),2);self.assertEqual(self.store.business,46500)
  self.assertEqual(result['activeIssue'],'2026-11');self.assertEqual(result['nextEligibleCheckAt'],'2026-12-09T12:00:00+00:00')
  saved=json.loads((self.root/'last-check.json').read_text());self.assertEqual(saved['activeIssue'],result['activeIssue'])
  manifest,kw=self.promotions[0];self.assertEqual(manifest['files']['mean']['sha256'],digest(RAW));self.assertEqual(kw['expected_generation'],'original')
  self.assertEqual(request('anomaly','2026-11')['area'],[-13,112,-36,130]);self.assertEqual(request('mean','2026-11')['leadtime_month'],list('123456'))
  self.assertFalse(self.run_once()['networkRequest']);self.assertEqual(len(self.client.submitted),2)
 def test_pending_job_resumes_and_obeys_interval(self):
  self.client.status='accepted';self.assertEqual(self.run_once()['action'],'waiting_for_existing_job');self.assertEqual(len(self.client.submitted),1)
  self.assertEqual(self.run_once(NOW+timedelta(hours=1))['action'],'wait_for_check_interval')
  self.client.status='successful';self.assertTrue(self.run_once(NOW+timedelta(days=1))['promoted']);self.assertEqual(len(self.client.submitted),2);self.assertEqual(self.client.resumed,['bounded-job'])
 def test_uncertain_submission_does_not_resubmit(self):
  self.client.fail='submit';first=self.run_once();self.assertEqual(first['action'],'failed_last_good_retained');self.assertNotIn('secret',json.dumps(first))
  self.client.fail=None;second=self.run_once(NOW+timedelta(days=1));self.assertEqual(second['error'],'submission_outcome_requires_reconciliation');self.assertEqual(len(self.client.submitted),1);self.assertFalse(self.promotions)
 def test_unavailable_constraints_create_no_job(self):
  self.client.fail='constraints';self.assertEqual(self.run_once()['action'],'failed_last_good_retained');self.assertEqual(self.client.submitted,[]);self.assertEqual(self.store.generation,'original')
 def test_failed_remote_is_quarantined(self):
  self.client.status='failed';self.run_once();self.client.status='successful';self.run_once(NOW+timedelta(days=1));self.assertEqual(len(self.client.submitted),1);self.assertFalse(self.promotions)
 def test_partial_download_fails_without_promotion(self):
  self.client.fail='download';self.assertEqual(self.run_once()['action'],'failed_last_good_retained');self.assertEqual(self.store.generation,'original');self.assertFalse(self.promotions)
 def test_fully_cached_pair_uses_no_client_and_still_validates(self):
  folder=self.root/'2026-11';folder.mkdir(parents=True)
  jobs={}
  for kind in ['mean','anomaly']:
   (folder/(kind+'.grib')).write_bytes(RAW);jobs[kind]={'phase':'downloaded','sha256':digest(RAW),'requestSha256':digest(json.dumps(request(kind,'2026-11'),sort_keys=True).encode())}
  atomic_json(folder/'jobs.json',{'issueMonth':'2026-11','jobs':jobs});self.assertTrue(self.run_once()['promoted']);self.assertEqual(self.client.submitted,[])
 def test_invalid_cached_hash_retains_last_good(self):
  self.client.status='accepted';self.run_once();path=self.root/'2026-11/jobs.json';state=json.loads(path.read_text());state['jobs']['mean'].update(phase='downloaded',sha256='0'*64);atomic_json(path,state);(path.parent/'mean.grib').write_bytes(RAW)
  self.assertEqual(self.run_once(NOW+timedelta(days=1))['error'],'cached_download_invalid');self.assertEqual(self.store.generation,'original')
 def test_validation_failure_is_not_promotion(self):
  def invalid(*a,**kw):return {'action':'failed_last_good_retained','promoted':False,'error':'grib_model_units_dates_or_grid_mismatch'}
  result=once(self.store,CONFIG,self.root,now=NOW,client_factory=lambda:self.client,local_check=invalid)
  self.assertFalse(result['promoted']);self.assertEqual(self.store.generation,'original');self.assertEqual(self.store.business,46500)
 def test_rendered_timer_and_reported_slots_use_the_same_configuration(self):
  for interval in [1,2,3,4,6,8,12,24]:
   config={**CONFIG,'checkIntervalHours':interval,'checkHourUTC':7}
   hours=','.join(f'{h:02d}' for h in range(24) if (h-7)%interval==0)
   self.assertIn('OnCalendar=*-*-* '+hours+':00:00 UTC',timer_text(config))
   next_run=datetime.fromisoformat(plan(NOW,'2026-11',config)['nextEligibleCheckAt'])
   self.assertEqual((next_run.hour-7)%interval,0);self.assertEqual(next_run.day,9);self.assertEqual(next_run.month,12)
  with self.assertRaises(SourceError):timer_text({**CONFIG,'checkIntervalHours':5})
