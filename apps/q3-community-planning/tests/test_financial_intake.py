import copy,gzip,json,threading,unittest
from datetime import timedelta
from unittest.mock import patch
import test_source_adapter as source
import test_financial_support as support_fixtures
from test_business_upload import file_bytes,CUSTOMER_HEADERS
from test_upload_jobs import DeferredExecutor
from business_upload import derive_business,load_trusted_context,UploadJobs,UploadStages
from financial_support import HEADERS,derive_support_context
from financial_intake import FinancialStages,FinancialJobs,validate_attachment,PART_FILES
from source_adapter import SnapshotStore,SourceError,canonical,digest

class FinancialCase(unittest.TestCase):
 def setUp(self):
  source.Sources.setUp(self);self.now=source.NOW;self.store.clock=lambda:self.now;self.store.read();self.raw=support_fixtures.Support();self.raw.setUp();self.trusted=load_trusted_context(source.ROOT/'data/inputs')
  self.files={'customers':self.raw.customers,'usage':gzip.compress(self.raw.usage,mtime=0)}
  self.business=derive_business(self.files['customers'],self.files['usage'],True,self.trusted,self.now.date())[0]
  for key,name in PART_FILES.items():
   if name in HEADERS:self.files[key]=gzip.compress(file_bytes(HEADERS[name],self.raw.rows[name]),mtime=0)
  self.rehash_manifest()
  support=derive_support_context(self.files['customers'],self.files['usage'],True,self.trusted,self.now.date(),self.business,{PART_FILES[k]:v for k,v in self.files.items() if k not in {'customers','usage','manifest'}},self.files['manifest'],digest(self.files['manifest']))
  self.entry={'snapshotDate':self.business['snapshotDate'],'historyStart':self.business['historyStart'],'historyEnd':self.business['historyEnd'],'customerSourceSha256':self.business['customerSourceSha256'],'usageSourceSha256':self.business['usageSourceSha256'],'geographyRegistrySha256':self.business['geographyRegistrySha256'],'accountPostcodes':support['coverage']['accountPostcodes'],'retainedAccounts':self.business['retainedTotalAccounts'],'aggregateSha256':digest(canonical(support))}
  self.lookup_patch=patch('financial_intake.reviewed_entry',self.lookup);self.lookup_patch.start()
  self.store.replace_business(self.business,self.store.read()['generation']);self.base=self.store.read();self.stages=FinancialStages(self.store,self.trusted,lambda:self.now,entry_lookup=self.lookup)
 def lookup(self,h):
  if h!=digest(self.files['manifest']):raise SourceError('unreviewed_financial_manifest')
  return copy.deepcopy(self.entry)
 def rehash_manifest(self):
  files={'customers.csv':{'sha256':digest(self.files['customers'])},'consumption_daily.csv.gz':{'sha256':digest(self.files['usage'])}}
  for key,name in PART_FILES.items():
   if name in HEADERS:files[name]={'sha256':digest(self.files[key]),'headers':HEADERS[name],'rows':len(self.raw.rows[name])}
  self.files['manifest']=canonical({'parameters':{'start':self.business['historyStart'],'end':self.business['historyEnd'],'count':self.business['retainedTotalAccounts']},'files':files})
 def stage(self):return self.stages.stage(self.files,True,self.store.read()['generation'])
 def activate(self):
  s=self.stage();return self.stages.replace(s['stageId'],s['baseGeneration'])
 def tearDown(self):
  self.lookup_patch.stop();source.Sources.tearDown(self)

class FinancialIntake(FinancialCase):
 def test_stage_is_aggregate_only_and_does_not_change_current_data(self):
  s=self.stage();self.assertEqual(self.store.read()['generation'],self.base['generation']);self.assertNotIn('customer_id',json.dumps(s));self.assertEqual(s['proposedSupport']['areas'][0]['activeAccountsInEitherSupport'],1);self.assertTrue(s['validation']['accountCoverageMatched'])
 def test_explicit_replace_survives_restart_and_saves_no_raw_rows(self):
  p=self.activate();self.assertEqual(p['data']['business']['financialSupport']['areas'][0]['paidGrantCountInPeriod'],2);restored=SnapshotStore(self.inputs,self.runtime,lambda:self.now).read();self.assertEqual(restored['generation'],p['generation']);self.assertEqual(restored['data'],p['data']);text=(self.runtime/'last-good.json').read_text();self.assertNotIn('customer_id',text);self.assertNotIn('debt_at_entry',text);self.assertNotIn('P_G1',text)
 def test_failed_atomic_save_retains_exact_last_good_and_proposal(self):
  s=self.stage();before=(self.runtime/'last-good.json').read_bytes()
  with patch.object(self.store,'_persist',side_effect=OSError('fixture disk full')):
   with self.assertRaises(OSError):self.stages.replace(s['stageId'],s['baseGeneration'])
  self.assertEqual((self.runtime/'last-good.json').read_bytes(),before);self.assertIn(s['stageId'],self.stages.stages);self.assertEqual(self.store.read()['generation'],self.base['generation'])
 def test_missing_partial_duplicate_or_modified_source_cannot_replace(self):
  for mutate in [lambda f:f.pop('support'),lambda f:f.__setitem__('support',b'bad'),lambda f:f.__setitem__('manifest',f['manifest']+b' '),lambda f:f.__setitem__('unexpected',b'extra')]:
   with self.subTest(mutate=mutate):
    files=copy.deepcopy(self.files);mutate(files)
    with self.assertRaises(SourceError):self.stages.stage(files,True,self.base['generation'])
    self.assertEqual(self.store.read()['generation'],self.base['generation'])
 def test_missing_active_history_with_rehashed_metadata_cannot_be_zero(self):
  self.raw.rows['support_arrangement_history.csv.gz'].clear();self.files['support']=gzip.compress(file_bytes(HEADERS['support_arrangement_history.csv.gz'],[]),mtime=0);self.rehash_manifest()
  with self.assertRaisesRegex(SourceError,'parent_history_incomplete'):self.stage()
  self.assertNotIn('financialSupport',self.store.read()['data']['business'])
 def test_duplicate_interval_and_unknown_customer_fail(self):
  row=copy.deepcopy(self.raw.rows['support_arrangement_history.csv.gz'][0]);self.raw.rows['support_arrangement_history.csv.gz'].append(row);self.files['support']=gzip.compress(file_bytes(HEADERS['support_arrangement_history.csv.gz'],self.raw.rows['support_arrangement_history.csv.gz']),mtime=0);self.rehash_manifest()
  with self.assertRaisesRegex(SourceError,'duplicate_support'):self.stage()
  self.raw.rows['support_arrangement_history.csv.gz'].pop();self.raw.rows['support_arrangement_history.csv.gz'][0]['customer_id']='UNKNOWN';self.files['support']=gzip.compress(file_bytes(HEADERS['support_arrangement_history.csv.gz'],self.raw.rows['support_arrangement_history.csv.gz']),mtime=0);self.rehash_manifest()
  with self.assertRaisesRegex(SourceError,'customer_not_in_cohort'):self.stage()
 def test_wrong_snapshot_coverage_and_aggregate_are_rejected(self):
  s=self.stage()['proposedSupport']
  for edit in [lambda p:p.update(snapshotDate='2025-05-31'),lambda p:p['coverage']['accountPostcodes'].append('6000'),lambda p:p['areas'][0].update(activeAccountsInEitherSupport=0),lambda p:p['monthlyGrantLedger'].clear()]:
   p=copy.deepcopy(s);edit(p)
   with self.assertRaises(SourceError):self.store.replace_financial_support(p,self.base['generation'])
  self.assertEqual(self.store.read()['generation'],self.base['generation'])
 def test_manifest_window_must_match_current_snapshot(self):
  m=json.loads(self.files['manifest']);m['parameters']['end']='2025-05-31';self.files['manifest']=canonical(m)
  with self.assertRaisesRegex(SourceError,'window_or_cohort'):self.stage()
 def test_failed_second_upload_keeps_existing_support(self):
  p=self.activate();before=(self.runtime/'last-good.json').read_bytes();files=copy.deepcopy(self.files);files['grants']+=b'wrong'
  with self.assertRaises(SourceError):self.stages.stage(files,True,p['generation'])
  self.assertEqual((self.runtime/'last-good.json').read_bytes(),before);self.assertEqual(self.store.read()['data']['business']['financialSupport'],p['data']['business']['financialSupport'])
 def test_new_business_hash_clears_old_support_and_same_pair_preserves_it(self):
  p=self.activate();same=self.store.replace_business(self.business,p['generation']);self.assertIn('financialSupport',same['data']['business'])
  raw=self.files['customers'].replace(b'A,6765',b'OTHER,6765',1)
  usage=gzip.decompress(self.files['usage']).replace(b'A,',b'OTHER,')
  b=derive_business(raw,gzip.compress(usage,mtime=0),True,self.trusted,self.now.date())[0]
  changed=self.store.replace_business(b,same['generation']);self.assertNotIn('financialSupport',changed['data']['business']);self.assertEqual(changed['data']['business']['financialSupportUnavailableReason'],'business_source_changed');self.assertNotIn('financial_support_upload',changed['provenance'])
 def test_old_staged_generation_expiry_discard_and_replay_do_not_commit(self):
  a=self.stage();b=self.stage();p=self.stages.replace(a['stageId'],a['baseGeneration'])
  with self.assertRaisesRegex(SourceError,'changed'):self.stages.replace(b['stageId'],b['baseGeneration'])
  with self.assertRaisesRegex(SourceError,'missing_or_expired'):self.stages.replace(a['stageId'],a['baseGeneration'])
  self.stages.discard(b['stageId']);c=self.stage();self.now+=timedelta(minutes=31)
  with self.assertRaisesRegex(SourceError,'missing_or_expired'):self.stages.replace(c['stageId'],c['baseGeneration'])
  self.assertEqual(self.store.read()['generation'],p['generation'])
 def test_climate_change_keeps_dated_financial_context(self):
  from test_climate_refresh import pair
  p=self.activate();self.now=self.now.replace(month=11);changed=self.store.promote_climate(pair('2026-11'),p['generation']);self.assertEqual(changed['data']['business']['financialSupport'],p['data']['business']['financialSupport']);self.assertEqual(changed['data']['business']['snapshotDate'],'2025-06-30')
 def test_shared_worker_backpressure_and_failed_financial_job(self):
  gate=threading.Lock();executor=DeferredExecutor();business_stages=UploadStages(self.store,self.trusted,lambda:self.now);business_jobs=UploadJobs(business_stages,executor,gate);financial_jobs=FinancialJobs(self.stages,executor,gate)
  receipt=business_jobs.submit(self.files['customers'],self.files['usage'],True,True)
  with self.assertRaisesRegex(SourceError,'another_validation'):financial_jobs.submit(self.files,True,self.base['generation'])
  executor.run();business_stages.discard(business_jobs.status(receipt['jobId'])['result']['stageId']);files=copy.deepcopy(self.files);files.pop('grants')
  with self.assertRaisesRegex(SourceError,'complete_financial'):financial_jobs.submit(files,True,self.base['generation'])
  receipt=financial_jobs.submit(self.files,True,self.base['generation']);executor.run();self.assertEqual(financial_jobs.status(receipt['jobId'])['state'],'ready');self.assertFalse(gate.locked())
