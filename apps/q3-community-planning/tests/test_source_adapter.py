import copy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from source_adapter import SnapshotStore,SourceError,validate_bundle,records,FILES
NOW=datetime(2026,10,28,16,tzinfo=timezone.utc)

class Sources(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.inputs=self.root/'inputs';shutil.copytree(ROOT/'data/inputs',self.inputs)
  self.runtime=self.root/'runtime';self.store=SnapshotStore(self.inputs,self.runtime,lambda:NOW)
 def tearDown(self):self.temp.cleanup()
 def alter(self,key,change):
  name=FILES[key];p=self.inputs/name;d=json.loads(p.read_text());change(d);p.write_text(json.dumps(d))
  mp=self.inputs/'manifest.json';m=json.loads(mp.read_text());m['files'][key]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();mp.write_text(json.dumps(m))
 def test_ready_whole_bundle_and_no_credentials(self):
  p=self.store.read();self.assertEqual(p['status']['state'],'ready');self.assertEqual(set(p['data']),set(FILES));self.assertEqual(p['data']['business']['totalAccounts'],393);self.assertNotIn('MAPTILER_API_KEY',json.dumps(p));self.assertTrue((self.runtime/'last-good.json').is_file())
 def test_failed_replacement_retains_exact_good_bundle(self):
  first=self.store.read();cache=(self.runtime/'last-good.json').read_bytes();self.alter('mean',lambda d:d.update(units='K'));second=self.store.read()
  self.assertEqual(second['generation'],first['generation']);self.assertEqual(second['data'],first['data']);self.assertTrue(second['status']['last_good_retained']);self.assertEqual(second['status']['state'],'stale');self.assertEqual((self.runtime/'last-good.json').read_bytes(),cache)
 def test_retention_survives_restart(self):
  first=self.store.read();(self.inputs/'seasonal-data.json').unlink();other=SnapshotStore(self.inputs,self.runtime,lambda:NOW).read();self.assertEqual(other['data'],first['data']);self.assertEqual(other['status']['state'],'stale')
 def test_cold_missing_input_is_unavailable(self):
  (self.inputs/'q3-area-context.json').unlink();p=self.store.read();self.assertIsNone(p['data']);self.assertEqual(p['status']['state'],'unavailable');self.assertFalse(self.runtime.exists())
 def test_bad_hash_does_not_activate_even_valid_json(self):
  self.store.read();p=self.inputs/'seasonal-data.json';p.write_text(p.read_text()+' ');r=self.store.read();self.assertEqual(r['status']['last_refresh_error'],'source_hash_mismatch_mean');self.assertTrue(r['status']['last_good_retained'])
 def test_grid_and_issue_must_match(self):
  for mutate in [lambda d:d['latitudes'].__setitem__(0,-13.4),lambda d:d['fields'][0].update(validMonth='2026-11'),lambda d:d['source'].update(issueMonth='2026-09')]:
   with self.subTest(mutate=mutate):
    shutil.copytree(ROOT/'data/inputs',self.inputs,dirs_exist_ok=True);self.alter('anomaly',mutate);self.assertIsNone(self.store.read()['data'])
 def test_wrong_mean_variable_is_rejected(self):
  self.alter('mean',lambda d:d.update(variable='daily maximum'));self.assertIsNone(self.store.read()['data'])
 def test_baseline_and_decode_provenance_required(self):
  self.alter('anomaly',lambda d:d['source'].update(referencePeriod='1991-2020'));self.assertIsNone(self.store.read()['data'])
 def test_anomaly_values_are_not_kelvin_offset(self):
  p=self.store.read();a=p['data']['anomaly'];y=a['latitudes'].index(-18.5);x=a['longitudes'].index(125.5);self.assertEqual(a['fields'][0]['valuesAnomalyC'][y][x],.153564453125)
 def test_explicit_nulls_accepted_for_fail_closed_counting(self):
  self.alter('anomaly',lambda d:d['fields'][0]['valuesAnomalyC'][5].__setitem__(13,None));p=self.store.read();self.assertIsNone(p['data']['anomaly']['fields'][0]['valuesAnomalyC'][5][13])
 def test_boolean_or_nan_values_rejected(self):
  self.alter('anomaly',lambda d:d['fields'][0]['valuesAnomalyC'][0].__setitem__(0,True));self.assertIsNone(self.store.read()['data'])
 def test_silo_high_low_mismatch_rejected(self):
  self.alter('history',lambda d:d['points'][0]['months'][0].update(meanDailyLowC=100));self.assertIsNone(self.store.read()['data'])
 def test_account_splits_and_snapshot_evidence_required(self):
  self.alter('business',lambda d:d['areas'][0].update(prepaidAccounts=99));self.assertIsNone(self.store.read()['data'])
 def test_future_account_snapshot_not_substituted(self):
  self.alter('business',lambda d:d.update(snapshotDate='2026-11-01'));self.assertIsNone(self.store.read()['data'])
 def test_income_must_match_postal_area_and_year(self):
  self.alter('business',lambda d:d['areas'][0]['financialContext'].update(geography='SAL1234'));self.assertIsNone(self.store.read()['data'])
 def test_manifest_paths_cannot_escape_inputs(self):
  mp=self.inputs/'manifest.json';m=json.loads(mp.read_text());m['files']['mean']['file']='../../secret';mp.write_text(json.dumps(m));self.assertIsNone(self.store.read()['data'])
 def test_corrupt_cache_never_becomes_a_fallback(self):
  self.store.read();cache=self.runtime/'last-good.json';c=json.loads(cache.read_text());c['inputs']['mean']='{}';cache.write_text(json.dumps(c));(self.inputs/'manifest.json').unlink();self.assertIsNone(SnapshotStore(self.inputs,self.runtime,lambda:NOW).read()['data'])
 def test_replacement_persistence_failure_retains_last_good(self):
  first=self.store.read();m=self.inputs/'manifest.json';d=json.loads(m.read_text());d['preparation_note']='New validation candidate';m.write_text(json.dumps(d))
  with patch.object(self.store,'_persist',side_effect=OSError('storage failed')):p=self.store.read()
  self.assertEqual(p['generation'],first['generation']);self.assertEqual(p['status']['state'],'stale')
 def test_manifest_race_rejected_without_retries(self):
  self.store.read();original=self.store._read_text;calls=0
  def read(path):
   nonlocal calls
   if path.name=='manifest.json':
    calls+=1
    if calls==2:return original(path)+' '
   return original(path)
  with patch.object(self.store,'_read_text',side_effect=read):p=self.store.read()
  self.assertEqual(p['status']['last_refresh_error'],'inputs_changed_during_read');self.assertEqual(calls,2)
 def test_source_age_recomputed_without_aging_historical_accounts(self):
  self.store.read();self.store.clock=lambda:datetime(2026,11,1,tzinfo=timezone.utc);p=self.store.read();self.assertEqual(p['status']['state'],'stale');self.assertTrue(p['status']['earlier_forecast_issue']);self.assertIsNone(p['status']['last_refresh_error']);self.assertEqual(p['data']['business']['snapshotDate'],'2025-06-30')
 def test_restored_inputs_clear_failure(self):
  self.store.read();raw=(self.inputs/'seasonal-data.json').read_text();(self.inputs/'seasonal-data.json').write_text('{}');self.assertEqual(self.store.read()['status']['state'],'stale');(self.inputs/'seasonal-data.json').write_text(raw);self.assertEqual(self.store.read()['status']['state'],'ready')
if __name__=='__main__':unittest.main()
