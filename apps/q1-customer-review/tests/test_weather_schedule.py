"""Real worker loops and durable schedule state; no listeners or public requests."""
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import json,threading,time,unittest
from unittest.mock import patch
from prototype.public_weather import PERTH,WeatherError
from prototype.public_source import PublicSourceStore
from prototype.weather_job import DailyCacheJob
from tests.test_public_source import payload,NOW

class Clock:
 def __init__(self):self.now=NOW
 def __call__(self):return self.now

class WeatherScheduleTests(unittest.TestCase):
 def wait_for(self,predicate):
  deadline=time.monotonic()+2
  while not predicate() and time.monotonic()<deadline:time.sleep(.005)
  self.assertTrue(predicate())
 def store(self,root,clock,calls,fail):
  def fetch(url):
   calls.append(clock.now)
   if fail[0]:raise WeatherError('public_source_http_503')
   # Explicit fixture generation for each test's clock day, never date-shift real weather.
   with patch('tests.test_public_source.NOW',clock.now.replace(hour=3,minute=0,second=0,microsecond=0)):body=json.dumps(payload()).encode()
   return body,{}
  return PublicSourceStore(root,fetch=fetch,clock=clock,source_cache=Path(root)/'absent')
 def test_real_loop_daily_due_failure_retry_last_good_and_restart_without_duplicate(self):
  with TemporaryDirectory() as root:
   clock=Clock();calls=[];fail=[False];store=self.store(root,clock,calls,fail)
   job=DailyCacheJob(store,clock=clock,poll_seconds=.01);worker=job.start()
   try:
    self.wait_for(lambda:job.state.get('last_attempt_succeeded') is True)
    self.assertEqual(len(calls),1);self.assertTrue(job.status()['enabled'])
    self.assertIs(job.start(),worker) # No second thread, no extra request.
    self.assertTrue(job.stop(2));pointer=(Path(root)/'latest.json').read_bytes()
    job=DailyCacheJob(store,clock=clock,poll_seconds=.01);job.start()
    self.wait_for(lambda:job.status()['enabled']);time.sleep(.04);self.assertEqual(len(calls),1)
    clock.now=datetime(2026,10,30,6,tzinfo=PERTH);fail[0]=True
    self.wait_for(lambda:len(calls)==2 and job.state.get('last_attempt_succeeded') is False)
    self.assertEqual((Path(root)/'latest.json').read_bytes(),pointer)
    self.assertEqual(job.state['next_run_at'],'2026-10-29T22:15:00Z')
    self.assertTrue(job.stop(2));clock.now+=timedelta(minutes=1)
    job=DailyCacheJob(store,clock=clock,poll_seconds=.01);job.start();time.sleep(.04)
    self.assertEqual(len(calls),2) # Restart respects saved backoff.
    fail[0]=False;clock.now+=timedelta(minutes=14)
    self.wait_for(lambda:len(calls)==3 and job.state.get('last_attempt_succeeded') is True)
    self.assertNotEqual((Path(root)/'latest.json').read_bytes(),pointer)
    self.assertEqual(job.state['next_run_at'],'2026-10-30T22:00:00Z')
    self.assertFalse(store.view(clock.now)['current_customer_estimates_available'])
   finally:self.assertTrue(job.stop(2))
 def test_configured_time_persists_and_worker_fires_at_new_time(self):
  with TemporaryDirectory() as root:
   clock=Clock();calls=[];store=self.store(root,clock,calls,[False]);job=DailyCacheJob(store,clock=clock,poll_seconds=.01)
   configured=job.configure('07:45',clock.now);self.assertEqual(configured['next_run_at'],'2026-10-28T23:45:00Z')
   self.assertFalse(job.tick(clock.now)['ran']);self.assertEqual(calls,[])
   reloaded=DailyCacheJob(store,'07:45',clock=clock,poll_seconds=.01)
   self.assertFalse(reloaded.tick(clock.now)['ran']);clock.now=clock.now.replace(hour=7,minute=45)
   reloaded.start()
   try:self.wait_for(lambda:len(calls)==1 and reloaded.state.get('last_attempt_succeeded') is True)
   finally:self.assertTrue(reloaded.stop(2))
 def test_slow_refresh_status_configuration_and_duplicate_tick_do_not_block(self):
  with TemporaryDirectory() as root:
   clock=Clock();calls=[];store=self.store(root,clock,calls,[False]);entered=threading.Event();release=threading.Event()
   def slow():entered.set();release.wait(2);return {'succeeded':True}
   with patch.object(store,'refresh',side_effect=slow):
    job=DailyCacheJob(store,clock=clock,poll_seconds=.01);job.start()
    try:
     self.assertTrue(entered.wait(1));start=time.monotonic()
     self.assertTrue(job.status()['running']);self.assertFalse(job.tick()['ran']);job.configure('08:00')
     self.assertLess(time.monotonic()-start,.2)
    finally:release.set();self.assertTrue(job.stop(2))
   self.assertEqual(job.state['daily_time'],'08:00');self.assertEqual(job.state['next_run_at'],'2026-10-29T00:00:00Z')
 def test_missing_saved_snapshot_recovers_once_at_startup(self):
  with TemporaryDirectory() as root:
   clock=Clock();calls=[];store=self.store(root,clock,calls,[False]);job=DailyCacheJob(store,clock=clock);job.tick()
   self.assertEqual(len(calls),1)
   (Path(root)/'latest.json').write_text('{}')
   restored=self.store(root,clock,calls,[False]);new=DailyCacheJob(restored,clock=clock,poll_seconds=.01);new.start()
   try:self.wait_for(lambda:len(calls)==2 and new.state.get('last_attempt_succeeded') is True)
   finally:self.assertTrue(new.stop(2))
 def test_preview_settings_remain_manager_only_and_lifecycle_hooks_are_exposed(self):
  from tests.test_auth_handler import AuthHandlerTests
  case=AuthHandlerTests('test_manager_settings_read_write_and_session_bound_csrf');case.setUpClass();case.setUp()
  try:
   officer=case.login('officer');self.assertEqual(case.request('/api/settings','POST',{'opening_mode':'demo','weather_time':'07:00'},officer)['status'],403)
   manager=case.login('manager');r=case.request('/api/settings','POST',{'opening_mode':'demo','weather_time':'07:00'},manager)
   self.assertEqual(r['status'],200);self.assertEqual(r['body']['schedule']['daily_time'],'07:00')
   self.assertEqual(json.loads((case.server.weather_job.store.root/'job.json').read_text())['daily_time'],'07:00')
   restarted=DailyCacheJob(case.server.weather_job.store,'07:00');self.assertEqual(restarted.state['next_run_at'],r['body']['schedule']['next_run_at'])
   case.server.auth=None;self.assertEqual(case.request('/api/settings')['status'],403)
  finally:case.tearDown()

if __name__=='__main__':unittest.main()

class ScheduleFailureRegressionTests(unittest.TestCase):
 def test_status_write_failure_keeps_memory_backoff_and_reports_persistence_error(self):
  with TemporaryDirectory() as root:
   from types import SimpleNamespace
   calls=[];store=SimpleNamespace(root=Path(root),refresh=lambda:(calls.append(1) or {'succeeded':False,'error':'offline'}))
   job=DailyCacheJob(store,clock=lambda:NOW)
   with patch('prototype.weather_job.write_json',side_effect=OSError('fixture disk failure')):
    self.assertTrue(job.tick()['ran']);self.assertFalse(job.tick()['ran'])
   self.assertEqual(calls,[1]);self.assertEqual(job.state['next_run_at'],'2026-10-28T19:15:00Z')
   self.assertFalse(job.status()['state_persisted']);self.assertEqual(job.status()['persistence_error'],'weather_schedule_status_not_persisted')
 def test_failed_manager_settings_commit_preserves_memory_and_durable_schedule(self):
  from tests.test_auth_handler import AuthHandlerTests
  case=AuthHandlerTests('test_manager_settings_read_write_and_session_bound_csrf');case.setUpClass();case.setUp()
  try:
   headers=case.login('manager');case.server.weather_job.configure('06:00');before=dict(case.server.weather_job.state)
   raw=(case.server.weather_job.store.root/'job.json').read_bytes()
   with patch('serve.write_json',side_effect=OSError('fixture settings save failure')):
    result=case.request('/api/settings','POST',{'opening_mode':'upload','weather_time':'07:45'},headers)
   self.assertEqual(result['status'],503);self.assertEqual(case.server.settings,{'opening_mode':'demo','weather_time':'06:00'})
   self.assertEqual(case.server.weather_job.state,before);self.assertEqual(case.server.weather_job.local_time,'06:00')
   self.assertEqual((case.server.weather_job.store.root/'job.json').read_bytes(),raw);self.assertFalse(case.server.settings_path.exists())
  finally:case.tearDown()
 def test_interruption_after_authoritative_config_commit_recovers_selected_due(self):
  with TemporaryDirectory() as root:
   from types import SimpleNamespace
   store=SimpleNamespace(root=Path(root));job=DailyCacheJob(store,clock=lambda:NOW);job.configure('06:00');old=(Path(root)/'job.json').read_bytes();saved=[]
   with patch('prototype.weather_job.write_json',side_effect=OSError('advisory status save failure')):
    expected=job.configure('07:45',commit=lambda state:saved.append(dict(state)))
   self.assertEqual((Path(root)/'job.json').read_bytes(),old);self.assertTrue(saved)
   restored=DailyCacheJob(store,'07:45',clock=lambda:NOW,configured_state=saved[0])
   self.assertEqual(restored.state['next_run_at'],expected['next_run_at']);self.assertEqual(restored.state['configuration_id'],saved[0]['configuration_id'])
 def test_refresh_finishing_after_time_change_preserves_tomorrows_due(self):
  with TemporaryDirectory() as root:
   from types import SimpleNamespace
   clock=Clock();clock.now=clock.now.replace(hour=6);entered=threading.Event();release=threading.Event()
   def refresh():entered.set();release.wait(2);return {'succeeded':True}
   job=DailyCacheJob(SimpleNamespace(root=Path(root),refresh=refresh),clock=clock,poll_seconds=.01);job.start()
   try:
    self.assertTrue(entered.wait(1));clock.now=clock.now.replace(minute=2);configured=job.configure('06:01');release.set()
    deadline=time.monotonic()+2
    while job.status()['running'] and time.monotonic()<deadline:time.sleep(.005)
    self.assertEqual(job.state['next_run_at'],configured['next_run_at']);self.assertEqual(job.state['next_run_at'],'2026-10-29T22:01:00Z')
   finally:release.set();self.assertTrue(job.stop(2))

class ServerScheduleRecoveryTests(unittest.TestCase):
 def test_make_server_restores_atomic_configuration_and_exposes_worker_hooks_without_socket(self):
  from types import SimpleNamespace
  from serve import make_server
  with TemporaryDirectory() as root:
   root=Path(root);due='2026-10-31T23:45:00Z';config={'daily_time':'07:45','timezone':'Australia/Perth','next_run_at':due,'configuration_id':'a'*32}
   (root/'instance-settings.json').write_text(json.dumps({'opening_mode':'upload','weather_time':'07:45','weather_schedule':config}))
   weather=root/'public-weather';weather.mkdir();(weather/'job.json').write_text(json.dumps({'daily_time':'06:00','next_run_at':'2026-10-28T22:00:00Z','configuration_id':'b'*32}))
   with patch('serve.ThreadingHTTPServer',return_value=SimpleNamespace(server_port=8891)):
    server=make_server(store_root=root,review={'build':{'id':'fixture'},'customers':[]})
   try:
    self.assertEqual(server.settings,{'opening_mode':'upload','weather_time':'07:45'})
    self.assertEqual(server.weather_job.state['next_run_at'],due)
    self.assertEqual(server.weather_job.state['configuration_id'],'a'*32)
    self.assertTrue(callable(server.start_weather_updates));self.assertTrue(callable(server.stop_weather_updates))
    self.assertFalse(server.weather_job.status()['enabled'])
   finally:server.stop_weather_updates();server.upload_jobs.close()

class PostCommitScheduleTests(unittest.TestCase):
 def test_committed_settings_with_sync_error_align_memory_and_report_warning(self):
  from tests.test_auth_handler import AuthHandlerTests
  from prototype.uploads import write_json as real_write
  case=AuthHandlerTests('test_manager_settings_read_write_and_session_bound_csrf');case.setUpClass();case.setUp()
  try:
   headers=case.login('manager')
   def replaced_then_failed(path,value):real_write(path,value);raise OSError('fixture directory sync failure after replacement')
   with patch('serve.write_json',side_effect=replaced_then_failed):
    result=case.request('/api/settings','POST',{'opening_mode':'upload','weather_time':'07:45'},headers)
   self.assertEqual(result['status'],200);self.assertEqual(case.server.settings,{'opening_mode':'upload','weather_time':'07:45'})
   saved=json.loads(case.server.settings_path.read_text());self.assertEqual(saved['weather_schedule']['configuration_id'],case.server.weather_job.state['configuration_id'])
   self.assertEqual(case.server.weather_job.local_time,'07:45');self.assertTrue(result['body']['schedule']['configuration_sync_warning'])
   restored=DailyCacheJob(case.server.weather_job.store,'07:45',configured_state=saved['weather_schedule'])
   self.assertEqual(restored.state['next_run_at'],case.server.weather_job.state['next_run_at'])
  finally:case.tearDown()

class DirectConfigurationTests(unittest.TestCase):
 def test_direct_configuration_reconciles_post_replace_sync_failure(self):
  from types import SimpleNamespace
  from prototype.uploads import write_json as real_write
  with TemporaryDirectory() as root:
   job=DailyCacheJob(SimpleNamespace(root=Path(root)),clock=lambda:NOW)
   def replaced_then_failed(path,value):real_write(path,value);raise OSError('fixture post-replace sync failure')
   with patch('prototype.weather_job.write_json',side_effect=replaced_then_failed):result=job.configure('07:45')
   self.assertEqual(job.local_time,'07:45');self.assertTrue(result['configuration_sync_warning'])
   self.assertEqual(json.loads((Path(root)/'job.json').read_text()),job.state)
