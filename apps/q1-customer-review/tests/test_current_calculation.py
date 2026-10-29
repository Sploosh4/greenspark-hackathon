from copy import deepcopy
from datetime import datetime,timedelta
import importlib.util,json,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from prototype.current_calculation import CurrentCalculations,run_frozen
from prototype.public_weather import normalise
from prototype.uploads import write_json,encoded,digest
from prototype.work import work_scope,WorkControl,WorkCancelled

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('current_runner_test',ROOT/'tools/current_inference.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class CurrentCalculationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.base=json.loads((ROOT/'tests/fixtures/current-model-example.json').read_text());self.now=datetime.fromisoformat(self.base['current_demo']['inference_as_of'])
        raw=json.loads((ROOT/'tests/fixtures/retained-public-wrapper.json').read_text())
        self.context={'snapshot':normalise(raw),'adapter_loaded_at':self.now.isoformat(),'last_error':None,'snapshot_sha256':self.base['current_demo']['weather_snapshot_sha256']}
        self.weather=SimpleNamespace(context_source=lambda:deepcopy(self.context));self.calls=0
        def calculate(payload):
            self.calls+=1;result=deepcopy(self.base);result['current_demo']['inference_as_of']=payload['as_of'];return result
        self.service=CurrentCalculations(self.tmp.name,self.weather,clock=lambda:self.now,runner=calculate)
        self.base['current_demo']['calculation_key']=self.service.key(self.base,self.context,self.now)
    def tearDown(self):self.service.close();self.tmp.cleanup()
    def wait(self):
        deadline=time.monotonic()+3
        while self.service.status()['running'] and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(self.service.status()['running'])
    def test_initial_current_result_reuses_upload_calculation_with_stable_version(self):
        first=self.service.view(self.base);second=self.service.view(self.base)
        self.assertEqual(first,second);self.assertEqual(self.calls,0)
        self.assertEqual(first['batch_revision'],first['snapshot_id']);self.assertNotEqual(first['batch_revision'],self.base['business_revision'])
    def test_unavailable_weather_matches_new_context_not_old_vintage(self):
        raw=json.loads((ROOT/'tests/fixtures/retained-public-wrapper.json').read_text());raw['retrieved_at']=self.now.isoformat()
        values=raw['localities'][0]['forecast']['hourly']['temperature_2m'];raw['localities'][0]['forecast']['hourly']['temperature_2m']=[v+2 if v is not None else None for v in values]
        self.context.update(snapshot=normalise(raw),snapshot_sha256='b'*64)
        key=self.service.key(self.base,self.context,self.now);view=self.service._unavailable(self.base,self.context,self.now,key,'recalculating_current_scenario')
        self.assertEqual(view['current_demo']['weather_snapshot_sha256'],'b'*64)
        self.assertEqual(view['current_demo']['weather_retrieved_at'],self.context['snapshot']['retrieved_at'])
        date=view['horizon_start'];new=next(r for r in view['weather'] if r['date']==date);old=next(r for r in self.base['weather'] if r['date']==date)
        self.assertAlmostEqual(new['max_temp'],old['max_temp']+2)
        self.assertTrue(all(r['predictions'][0]['predicted'] is None for r in view['customers']))
    def test_unavailable_snapshot_loaded_after_cutoff_exposes_no_weather_values(self):
        self.context['adapter_loaded_at']=(self.now+timedelta(hours=1)).isoformat()
        view=self.service._unavailable(self.base,self.context,self.now,'c'*64,'forecast_loaded_after_review');self.assertEqual(view['weather'],[])
    def test_transient_failure_has_bounded_retry_and_then_success(self):
        self.base['current_demo']['calculation_key']='old'
        good=self.service.runner;attempts=[]
        def transient(payload):
            attempts.append(1)
            if len(attempts)==1:raise OSError('unit transient')
            return good(payload)
        self.service.runner=transient;self.service.view(self.base);self.wait()
        key=self.service.key(self.base,self.context,self.now);self.assertEqual(self.service.errors[key],'current_calculation_failed')
        self.service.view(self.base);self.assertEqual(len(attempts),1)
        self.service.retry_after[key]=0;self.service.view(self.base);self.wait()
        self.assertEqual(len(attempts),2);self.assertIsNone(self.service.status()['last_error'])
        self.assertIsNotNone(self.service.view(self.base)['customers'][0]['predictions'][0]['predicted'])
    def test_two_failures_stop_auto_retry_but_explicit_retry_can_recover(self):
        self.base['current_demo']['calculation_key']='old';good=self.service.runner
        self.service.runner=lambda payload:(_ for _ in ()).throw(OSError('unit failure'))
        key=self.service.key(self.base,self.context,self.now)
        for _ in range(2):self.service.retry_after[key]=0;self.service.view(self.base);self.wait()
        self.service.retry_after[key]=0;self.service.view(self.base);self.assertFalse(self.service.status()['running'])
        self.service.runner=good;self.service.retry(self.base);self.wait();self.assertIsNone(self.service.status()['last_error'])
    def test_pending_view_revision_is_stable_and_does_not_claim_new_inference(self):
        key=self.service.key(self.base,self.context,self.now)
        first=self.service._unavailable(self.base,self.context,self.now,key,'recalculating_current_scenario')
        later=self.service._unavailable(self.base,self.context,self.now+timedelta(minutes=1),key,'recalculating_current_scenario')
        self.assertEqual(first,later)
    def test_derivative_cache_quota_counts_orphaned_index_writes(self):
        for i in range(8):
            review=deepcopy(self.base);key=f'{i:064x}';review['current_demo']['calculation_key']=key
            if i==3:write_json(Path(self.tmp.name)/(key+'.json'),{'review':review,'sha256':digest(encoded(review))})
            else:self.service._save(key,review)
        files=[p for p in Path(self.tmp.name).glob('*.json') if p.name!='index.json']
        self.assertLessEqual(len(files),4);self.assertTrue((Path(self.tmp.name)/(self.service.last_good+'.json')).exists())
    def test_reported_invalid_yesterday_does_not_silently_turn_into_lag2(self):
        day=datetime.fromisoformat('2026-10-29T03:00:00+08:00').date();usage=[{'date':'2026-10-'+str(i)} for i in range(21,28)];eligible={r['date'] for r in usage}
        self.assertEqual(runner.reported_week(usage,eligible,day)[1:],(2,None))
        for state in ('outage','disconnected'):
            invalid=usage+[{'date':'2026-10-28','state':state}]
            self.assertEqual(runner.reported_week(invalid,eligible,day)[1:],(1,'incomplete_reported_week'))
    def test_cooperative_cancel_terminates_only_the_owned_inference_child(self):
        class Child:
            returncode=None;terminated=False
            def poll(self):return self.returncode
            def terminate(self):self.terminated=True;self.returncode=-15
            def wait(self,timeout=None):return self.returncode
        child=Child();calls=[]
        def cancelled():calls.append(1);return len(calls)>2
        with patch('prototype.current_calculation.subprocess.Popen',return_value=child),work_scope(WorkControl(cancelled)):
            with self.assertRaises(WorkCancelled):run_frozen({})
        self.assertTrue(child.terminated)

if __name__=='__main__':unittest.main()
