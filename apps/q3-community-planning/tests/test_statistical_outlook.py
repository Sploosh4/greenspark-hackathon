"""Frozen statistical contract, no pipeline imports, training, requests or listener."""
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from dataclasses import replace
from types import SimpleNamespace
import test_auth_integration as auth_fixture
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from statistical_outlook import *
ROOT=Path(__file__).resolve().parents[1];EXPORT=ROOT/'data/statistical/ml_outlook_layer.json';RAW=EXPORT.read_bytes();BASE=json.loads(RAW)
class StatisticalContract(unittest.TestCase):
 def alter(self,change):
  d=copy.deepcopy(BASE);change(d);return d
 def test_exact_export_hash_and_source_separation(self):
  self.assertEqual(hashlib.sha256(RAW).hexdigest(),EXPORT_SHA);self.assertEqual(decode(RAW),BASE);self.assertNotIn('ECMWF',json.dumps(PROVENANCE));self.assertEqual(PROVENANCE['baseline']['period'],'1991-2020')
 def test_hash_checked_before_json_parse(self):
  for raw in [RAW+b' ',b'{not json',b'NaN']:
   with self.assertRaisesRegex(OutlookError,'statistical_hash'):decode(raw)
 def test_size_checked_before_parse(self):
  with self.assertRaisesRegex(OutlookError,'statistical_size'):decode(b' '*(MAX_BYTES+1))
 def test_duplicate_key_parser_rejects(self):
  with self.assertRaisesRegex(OutlookError,'duplicate_json_key'):json.loads('{"x":1,"x":2}',object_pairs_hook=unique_object)
 def test_units_method_baseline_cannot_be_relabeled(self):
  for change in [lambda d:d['meta'].update(source='ECMWF'),lambda d:d['meta'].update(training_through='2026-10')]:
   with self.assertRaises(OutlookError):validate_export(self.alter(change))
 def test_null_preserved_and_uncovered_cells_not_inserted(self):
  d=self.alter(lambda d:d['cells'][0]['f']['2026-10']['p'].__setitem__(0,None));self.assertIsNone(validate_export(d)['cells'][0]['f']['2026-10']['p'][0]);self.assertEqual(len(d['cells']),255)
 def test_boolean_nan_infinity_and_probability_range_rejected(self):
  for value in [True,float('nan'),float('inf'),-.01,1.01]:
   with self.subTest(value=value),self.assertRaises(OutlookError):validate_export(self.alter(lambda d:d['cells'][0]['f']['2026-10']['p'].__setitem__(0,value)))
 def test_kelvin_values_and_anomaly_outside_contract_rejected(self):
  for key,value in [('t',300),('a',40),('n',273.15),('lo',-100),('hi',100)]:
   with self.subTest(key=key),self.assertRaises(OutlookError):validate_export(self.alter(lambda d:d['cells'][0]['f']['2026-10'][key].__setitem__(0,value)))
 def test_missing_and_extra_month_arrays_rejected(self):
  for key in ['t','a','p','lo','hi','n']:
   with self.subTest(key=key),self.assertRaises(OutlookError):validate_export(self.alter(lambda d:d['cells'][0]['f']['2026-10'][key].pop()))
 def test_issue_and_valid_month_alignment(self):
  for change in [lambda d:d['issues'][0]['months'].__setitem__(0,'2026-11'),lambda d:d['issues'].reverse(),lambda d:d['issues'][0].update(key='2026-09'),lambda d:d['cells'][0]['f'].pop('2026-11')]:
   with self.assertRaises(OutlookError):validate_export(self.alter(change))
 def test_coordinates_identity_and_duplicate_rejected(self):
  for change in [lambda d:d['cells'][0].update(lat=-35.4),lambda d:d['cells'][0].update(id='wrong'),lambda d:d['cells'].__setitem__(0,copy.deepcopy(d['cells'][1])),lambda d:d['cells'][0].update(lon=130.5)]:
   with self.assertRaises(OutlookError):validate_export(self.alter(change))
 def test_no_silent_incomplete_export(self):
  with self.assertRaises(OutlookError):validate_export(self.alter(lambda d:d['cells'].pop()))
 def test_partial_and_carried_indices_metadata_required(self):
  for change in [lambda d:d['issues'][1].update(uses_partial_month=False),lambda d:d['meta'].update(indices_carried_forward=[])]:
   with self.assertRaises(OutlookError):validate_export(self.alter(change))
 def test_range_and_rounded_anomaly_consistency(self):
  for change in [lambda d:d['cells'][0]['f']['2026-10']['lo'].__setitem__(0,40),lambda d:d['cells'][0]['f']['2026-10']['a'].__setitem__(0,5)]:
   with self.assertRaises(OutlookError):validate_export(self.alter(change))
 def test_negative_skill_valid_not_a_probability(self):
  self.assertLess(min(x for c in validate_export(BASE)['cells'] for x in c['skill']),0)
 def test_skill_nonfinite_or_greater_than_one_rejected(self):
  for v in [float('nan'),float('-inf'),True,1.01]:
   with self.assertRaises(OutlookError):validate_export(self.alter(lambda d:d['cells'][0]['skill'].__setitem__(0,v)))
 def test_locality_coordinate_join(self):
  with self.assertRaises(OutlookError):validate_export(self.alter(lambda d:d['localities'][0].update(lon=113.5)))
 def test_stale_and_advance_issue_status(self):
  now=datetime(2026,10,29,tzinfo=timezone.utc);s=issue_status(BASE,now);self.assertEqual(s['2026-10']['state'],'available');self.assertEqual(s['2026-11']['state'],'advance');self.assertTrue(s['2026-11']['uses_partial_month']);self.assertTrue(all(s['state']=='stale' for s in issue_status(BASE,datetime(2027,5,1,tzinfo=timezone.utc)).values()))
 def test_bad_replacement_retains_last_validated_bytes_and_fresh_reads_are_isolated(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'export.json';p.write_bytes(RAW);store=StatisticalOutlook(p);one=store.read();one['data']['cells'].clear();self.assertEqual(len(store.read()['data']['cells']),255);p.write_bytes(b'{}');failed=store.read();self.assertEqual(failed['status']['state'],'stale');self.assertTrue(failed['status']['last_good_retained']);self.assertEqual(failed['data'],BASE);p.write_bytes(RAW);self.assertEqual(store.read()['status']['state'],'ready')
 def test_cold_bad_export_unavailable(self):
  with tempfile.TemporaryDirectory() as tmp:self.assertIsNone(StatisticalOutlook(Path(tmp)/'absent').read()['data'])

class StatisticalHTTP(unittest.TestCase):
 setUpClass=classmethod(auth_fixture.ActualQ3Auth.setUpClass.__func__)
 setUp=auth_fixture.ActualQ3Auth.setUp
 call=auth_fixture.ActualQ3Auth.call
 login=auth_fixture.ActualQ3Auth.login
 def test_authenticated_manager_reads_actual_new_route(self):
  self.server.statistical_outlook=StatisticalOutlook(EXPORT);r,h=self.call('GET','/api/q3/statistical-outlook',headers=self.login());self.assertEqual(r['status'],200);self.assertEqual(r['body']['source_id'],SOURCE);self.assertEqual(len(r['body']['data']['cells']),255);self.assertEqual(h.principal.role,'manager')
 def test_no_auth_forged_role_officer_and_q1_cookie_denied(self):
  self.assertEqual(self.call('GET','/api/q3/statistical-outlook',headers={'X-Role':'manager'})[0]['status'],401);h=self.login();h['Cookie']=h['Cookie'].replace('tc_q3_session','tc_q1_session');self.assertEqual(self.call('GET','/api/q3/statistical-outlook',headers=h)[0]['status'],401);h=self.login();self.accounts['manager']=replace(self.accounts['manager'],role='officer');self.assertEqual(self.call('GET','/api/q3/statistical-outlook',headers=h)[0]['status'],401)
 def test_cross_site_denied_and_no_pipeline_write_route(self):
  h=self.login();self.assertEqual(self.call('GET','/api/q3/statistical-outlook',headers={**h,'Sec-Fetch-Site':'cross-site'})[0]['status'],403);self.assertEqual(self.call('POST','/api/q3/statistical-outlook',b'{}',h)[0]['status'],404)
