"""Synthetic future issues exist only in isolated fixture stores, never live data."""
import copy,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
import test_source_adapter as fixtures
from source_adapter import SourceError,SnapshotStore,canonical,digest
from climate_pack import decode_messages,validate_pair,LATS,LONS,month_at,decode_grib
from refresh_scheduler import check_plan,run_local_check,read_inbox

def messages(kind,issue='2026-11'):
 out=[]
 for i in range(6):
  info={'edition':1,'centre':'ecmf','systemNumber':51,'dataDate':int(issue.replace('-','')+'01'),'dataTime':0,'shortName':'2t' if kind=='mean' else '2ta','paramId':167 if kind=='mean' else 171167,'units':'K','typeOfLevel':'surface','level':0,'dataType':'em','marsStream':'msmm' if kind=='mean' else 'mmsa','forecastMonth':i+1,'verifyingMonth':int(month_at(issue,i).replace('-','')),'validityDate':int(month_at(issue,i+1).replace('-','')+'01'),'validityTime':0,'gridType':'regular_ll','Ni':18,'Nj':23,'numberOfDataPoints':414,'numberOfMissing':0,'iDirectionIncrementInDegrees':1,'jDirectionIncrementInDegrees':1}
  out.append({'metadata':info,'latitudes':LATS.copy(),'longitudes':LONS.copy(),'valuesK':[300.125 if kind=='mean' else .5]*414})
 return out

def pair(issue='2026-11'):
 return {k:decode_messages(messages(k,issue),k,issue,('1' if k=='mean' else '2')*64) for k in ['mean','anomaly']}

class Decoder(unittest.TestCase):
 def test_future_months_year_boundary_and_no_anomaly_offset(self):
  p=pair();r=validate_pair(p['mean'],p['anomaly']);self.assertEqual(r['validMonths'],['2026-11','2026-12','2027-01','2027-02','2027-03','2027-04']);self.assertAlmostEqual(p['mean']['fields'][0]['valuesC'][0][0],26.975);self.assertEqual(p['anomaly']['fields'][0]['valuesAnomalyC'][0][0],.5)
 def test_incomplete_duplicate_or_reordered_leads(self):
  for edit in [lambda m:m.pop(),lambda m:m.__setitem__(1,m[0]),lambda m:m.reverse()]:
   m=messages('mean');edit(m)
   with self.assertRaises(SourceError):decode_messages(m,'mean','2026-11','1'*64)
 def test_model_parameter_units_stream_and_dates_fail_closed(self):
  for key,value in [('systemNumber',52),('centre','other'),('paramId',169),('units','degC'),('marsStream','mmsa'),('dataDate',20261102),('verifyingMonth',202612),('validityDate',20261101)]:
   m=messages('mean');m[0]['metadata'][key]=value
   with self.assertRaisesRegex(SourceError,'metadata|mismatch'):decode_messages(m,'mean','2026-11','1'*64)
 def test_native_missing_preserved_counted_not_filled(self):
  m=messages('anomaly');m[0]['valuesK'][0]=None;m[0]['metadata']['numberOfMissing']=1
  a=decode_messages(m,'anomaly','2026-11','2'*64);self.assertIsNone(a['fields'][0]['valuesAnomalyC'][0][0]);validate_pair(pair()['mean'],a)
  m[0]['metadata']['numberOfMissing']=0
  with self.assertRaisesRegex(SourceError,'missingness'):decode_messages(m,'anomaly','2026-11','2'*64)
 def test_nan_shape_grid_and_bad_hash(self):
  for mutate in [lambda m:m[0]['valuesK'].__setitem__(0,float('nan')),lambda m:m[0]['valuesK'].pop(),lambda m:m[0]['latitudes'].__setitem__(0,-13.4)]:
   m=messages('mean');mutate(m)
   with self.assertRaises(SourceError):decode_messages(m,'mean','2026-11','1'*64)
  with self.assertRaises(SourceError):decode_messages(messages('mean'),'mean','2026-11','bad')
 def test_mixed_pair_issues_and_modified_metadata(self):
  p=pair();p['anomaly']=pair('2026-12')['anomaly']
  with self.assertRaises(SourceError):validate_pair(p['mean'],p['anomaly'])
  p=pair();p['mean']['fields'][1]['gribMetadata']['numberOfMissing']=1
  with self.assertRaises(SourceError):validate_pair(p['mean'],p['anomaly'])
 def test_raw_hash_required_before_dependency_or_decode(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.grib';p.write_bytes(b'GRIB7777')
   with self.assertRaisesRegex(SourceError,'hash_or_size'):decode_grib(p,'mean','2026-11','1'*64)

class Promotion(unittest.TestCase):
 tearDown=fixtures.Sources.tearDown
 def setUp(self):
  fixtures.Sources.setUp(self);self.now=datetime(2026,11,12,tzinfo=timezone.utc);self.store.clock=lambda:self.now;self.old=self.store.read();self.pair=pair()
 def test_atomic_new_issue_keeps_business_history_and_survives_restart(self):
  new=self.store.promote_climate(self.pair,self.old['generation']);self.assertEqual(new['status']['climate_issue_date'],'2026-11-01');self.assertEqual(new['status']['state'],'ready');self.assertNotEqual(new['generation'],self.old['generation'])
  for k in ['business','history']:self.assertEqual(new['data'][k],self.old['data'][k])
  restored=SnapshotStore(self.inputs,self.runtime,lambda:self.now).read();self.assertEqual(restored['generation'],new['generation']);self.assertEqual(restored['data'],new['data'])
 def test_old_equal_future_issue_and_race_do_not_replace(self):
  for p,gen,code in [(pair('2026-10'),self.old['generation'],'not_newer'),(pair('2026-12'),self.old['generation'],'in_future'),(self.pair,'a'*64,'changed')]:
   with self.assertRaisesRegex(SourceError,code):self.store.promote_climate(p,gen)
   self.assertEqual(self.store.read()['generation'],self.old['generation'])
 def test_incomplete_or_invalid_pair_does_not_replace(self):
  p=pair();p['mean']['fields'].pop();before=(self.runtime/'last-good.json').read_bytes()
  with self.assertRaises(SourceError):self.store.promote_climate(p,self.old['generation'])
  self.assertEqual((self.runtime/'last-good.json').read_bytes(),before)
 def test_failed_storage_does_not_promote_in_memory(self):
  before=(self.runtime/'last-good.json').read_bytes()
  with patch.object(self.store,'_persist',side_effect=OSError('fixture storage failure')):
   with self.assertRaises(OSError):self.store.promote_climate(self.pair,self.old['generation'])
  self.assertEqual(self.store.read()['generation'],self.old['generation']);self.assertEqual((self.runtime/'last-good.json').read_bytes(),before)
 def test_failure_notice_retained_restart_and_cleared_on_success(self):
  p=self.store.record_climate_failure('2026-11','climate_source_incomplete');self.assertEqual(p['generation'],self.old['generation']);self.assertEqual(p['status']['state'],'stale');self.assertTrue(p['status']['last_good_retained']);self.assertEqual(SnapshotStore(self.inputs,self.runtime,lambda:self.now).read()['status']['climate_refresh_error'],'climate_source_incomplete')
  p=self.store.promote_climate(self.pair,self.old['generation']);self.assertIsNone(p['status']['climate_refresh_error'])
 def test_staleness_uses_actual_issue_and_seed_cannot_rollback(self):
  p=self.store.promote_climate(self.pair,self.old['generation']);self.now=datetime(2026,12,2,tzinfo=timezone.utc);again=self.store.read();self.assertEqual(again['generation'],p['generation']);self.assertTrue(again['status']['earlier_forecast_issue']);self.assertEqual(again['status']['state'],'stale')
 def test_separate_store_detects_commit_rejects_old_generation_and_preserves_pair(self):
  other=SnapshotStore(self.inputs,self.runtime,lambda:self.now);old=other.read();new=self.store.promote_climate(self.pair,self.old['generation'])
  self.assertEqual(other.read()['generation'],new['generation'])
  with self.assertRaisesRegex(SourceError,'changed'):other.replace_business(old['data']['business'],old['generation'])
  changed=other.replace_business(old['data']['business'],new['generation']);self.assertEqual(self.store.read()['generation'],changed['generation']);self.assertEqual(changed['data']['mean'],new['data']['mean']);self.assertEqual(changed['data']['anomaly'],new['data']['anomaly'])
 def test_lock_failure_returns_stale_retained_packet(self):
  with patch.object(self.store,'_disk_lock',side_effect=OSError('fixture lock unavailable')):
   p=self.store.read();self.assertEqual(p['generation'],self.old['generation']);self.assertEqual(p['status']['state'],'stale')
 def inbox(self,issue='2026-11'):
  self.inbox=self.root/'inbox';self.inbox.mkdir(exist_ok=True);files={}
  for k in ['mean','anomaly']:
   raw=(k+' synthetic test-only bytes').encode();name=k+'.grib';(self.inbox/name).write_bytes(raw);files[k]={'file':name,'sha256':digest(raw)}
  p=self.inbox/'release.json';p.write_bytes(canonical({'schemaVersion':1,'centre':'ECMWF','system':'51','issueMonth':issue,'files':files}));return p
 def test_local_check_dry_run_then_explicit_promotion_and_dedup(self):
  path=self.inbox();fake=lambda *args:self.pair
  out=run_local_check(path,self.store,decoder=fake);self.assertFalse(out['promoted']);self.assertEqual(self.store.read()['generation'],self.old['generation'])
  out=run_local_check(path,self.store,promote=True,expected_generation=self.old['generation'],decoder=fake);self.assertTrue(out['promoted'])
  with patch('refresh_scheduler.decode_pair',side_effect=AssertionError('must not decode')):
   out=run_local_check(path,self.store,decoder=lambda *a:(_ for _ in ()).throw(AssertionError('must not decode')));self.assertFalse(out['decoded'])
 def test_incomplete_manifest_and_traversal_fail_with_notice(self):
  path=self.inbox();d=json.loads(path.read_text());d['files'].pop('anomaly');path.write_bytes(canonical(d));out=run_local_check(path,self.store,promote=True);self.assertFalse(out['promoted']);self.assertTrue(out['noticePersisted']);self.assertEqual(self.store.read()['status']['climate_refresh_error'],'climate_source_incomplete')
  d['files']['anomaly']={'file':'../outside.grib','sha256':'2'*64};path.write_bytes(canonical(d));self.assertEqual(run_local_check(path,self.store)['action'],'failed_last_good_retained')

 def test_superseded_failed_issue_cannot_stale_newer_success(self):
  self.now=datetime(2026,12,12,tzinfo=timezone.utc);path=self.inbox('2026-11')
  def decoder(*args):
   self.store.promote_climate(pair('2026-12'),self.old['generation']);raise SourceError('grib_decode_failed')
  out=run_local_check(path,self.store,promote=True,decoder=decoder);p=self.store.read();self.assertEqual(p['status']['state'],'ready');self.assertIsNone(p['status']['climate_refresh_error']);self.assertEqual(out['action'],'superseded_during_validation');self.assertFalse(out['noticePersisted'])

class Schedule(unittest.TestCase):
 def setUp(self):self.config={'schemaVersion':1,'scheduleEnabled':False,'releaseDayUTC':6,'releaseLagDays':None,'checkIntervalHours':24,'retrievalMode':'existing_local_inbox_only'};self.now=datetime(2026,11,12,tzinfo=timezone.utc)
 def test_disabled_and_unreviewed_lag_never_activate(self):
  self.assertEqual(check_plan(self.now,'2026-10',self.config)['action'],'schedule_disabled');self.config['scheduleEnabled']=True;self.assertEqual(check_plan(self.now,'2026-10',self.config)['action'],'release_lag_configuration_required')
 def test_release_lag_interval_and_latest_success(self):
  self.config.update(scheduleEnabled=True,releaseLagDays=2);self.assertEqual(check_plan(self.now.replace(day=7),'2026-10',self.config)['action'],'wait_for_release_plus_lag');self.assertEqual(check_plan(self.now,'2026-10',self.config)['action'],'check_existing_local_inbox');self.assertEqual(check_plan(self.now,'2026-11',self.config)['action'],'latest_issue_already_active');self.assertEqual(check_plan(self.now,'2026-10',self.config,'2026-11-12T00:00:00+00:00')['action'],'wait_for_check_interval')
 def test_invalid_cadence_retrieval_and_timezone(self):
  for key,value in [('checkIntervalHours',0),('releaseLagDays',20),('releaseDayUTC',7),('retrievalMode','submit_api_job')]:
   c={**self.config,key:value}
   with self.assertRaises(SourceError):check_plan(self.now,'2026-10',c)
  with self.assertRaises(SourceError):check_plan(datetime(2026,11,12),'2026-10',self.config)
