"""Adversarial raw-table validation and atomic recovery, in disposable state."""
import copy,gzip,json,unittest
from unittest.mock import patch
import test_source_adapter as source
from test_business_upload import customer,usage,file_bytes
from business_upload import CUSTOMER_HEADERS,USAGE_HEADERS,derive_business,load_trusted_context
from financial_support import HEADERS
from financial_intake import FinancialStages,validate_attachment
from synthetic_financial import POLICY,derive_synthetic_context,validate_synthetic_attachment
from source_adapter import canonical,digest,SourceError,SnapshotStore

class SyntheticFixture:
 def __init__(self):
  self.trusted=load_trusted_context(source.ROOT/'data/inputs');self.cs=[customer('A'),customer('B',closed='2025-06-30'),customer('C',opened=''),customer('D')]
  for r in self.cs:
   for k in ['has_solar','concession_card','life_support','medical_cooling_subsidy','interpreter_required']:r[k]='False'
   r['solar_kw']='0'
  self.us=[usage(c,'2025-06-30') for c in ['A','B','C','D']]+[usage('A','2025-06-01')]
  self.tables={n:[] for n in HEADERS}
  self.add('payment_arrangements.csv.gz',arrangement_id='PA',customer_id='A',type='payment_plan',start_date='2025-06-01',amount='300.00',instalment='75.00',n_instalments='4',status='active',trigger='synthetic_customer_request')
  self.add('payment_arrangements.csv.gz',arrangement_id='PD',customer_id='D',type='payment_plan',start_date='2025-06-01',end_date='2025-06-30',amount='300.00',instalment='75.00',n_instalments='4',status='completed',trigger='synthetic_customer_request')
  self.add('hardship_programs.csv.gz',hardship_id='HA',customer_id='A',assessment_date='2025-06-01',trigger='synthetic_request',assessment_outcome='accepted',debt_at_entry='1000.00',start_date='2025-06-01',instalment='50.00',write_off='0.00',financial_counselling_referral='True',energy_efficiency_advice='True')
  for ident,cid,typ,table,end in [('PA','A','payment_plan','payment_arrangements',''),('PD','D','payment_plan','payment_arrangements','2025-06-30'),('HA','A','hardship_program','hardship_programs','')]:
   self.add('support_arrangement_history.csv.gz',history_id=ident+':1',arrangement_id=ident,customer_id=cid,arrangement_type=typ,status='active',effective_from='2025-06-01',effective_to=end,source_event_date='2025-06-01',source_table=table)
  self.add('support_arrangement_history.csv.gz',history_id='PD:2',arrangement_id='PD',customer_id='D',arrangement_type='payment_plan',status='completed',effective_from='2025-06-30',source_event_date='2025-06-30',source_table='payment_arrangements')
  for i,amount in [(1,'100.00'),(2,'200.01')]:
   self.add('hugs_grants.csv.gz',hugs_id='G'+str(i),customer_id='A',application_date='2025-06-01',payment_date='2025-06-14',debt_at_application='1000.00',region_cap='1000.00',grant_amount=amount,outcome='approved',hardship_id='HA')
   self.add('payments.csv.gz',payment_id='P_G'+str(i),customer_id='A',date='2025-06-14',amount=amount,method='hugs_grant',kind='hugs_grant',status='cleared')
 def add(self,name,**values):self.tables[name].append({k:str(values.get(k,'')) for k in HEADERS[name]})
 def packet(self):
  c=file_bytes(CUSTOMER_HEADERS,self.cs);u=gzip.compress(file_bytes(USAGE_HEADERS,self.us),mtime=0);self.business=derive_business(c,u,True,self.trusted,source.NOW.date())[0]
  sidecars={n:gzip.compress(file_bytes(HEADERS[n],r),mtime=0) for n,r in self.tables.items()};all_files={'customers.csv':c,'consumption_daily.csv.gz':u,**sidecars}
  files={n:{'sha256':digest(raw),'bytes':len(raw),'expandedBytes':len(gzip.decompress(raw)) if n.endswith('.gz') else len(raw),'headers':CUSTOMER_HEADERS if n=='customers.csv' else USAGE_HEADERS if n=='consumption_daily.csv.gz' else HEADERS[n],'rows':len(self.cs) if n=='customers.csv' else len(self.us) if n=='consumption_daily.csv.gz' else len(self.tables[n])} for n,raw in all_files.items()}
  self.manifest={'synthetic_financial_contract':POLICY,'synthetic':True,'generator':'unit-fixture','generator_source_sha256':'0'*64,'geography_sha256':self.business['geographyRegistrySha256'],'parameters':{'profile':'season-ahead','count':len(self.cs),'seed':1,'start':self.business['historyStart'],'end':self.business['historyEnd']},'financial_coverage':{'accountPostcodes':sorted(a['postcode'] for a in self.business['areas']),'historyStart':self.business['historyStart'],'historyEnd':self.business['historyEnd'],'declaration':'complete-synthetic-source-tables'},'files':files}
  return c,u,sidecars,canonical(self.manifest)
 def derive(self):
  c,u,s,m=self.packet();return derive_synthetic_context(c,u,self.trusted,source.NOW.date(),self.business,s,m)

class SyntheticContent(unittest.TestCase):
 def setUp(self):self.f=SyntheticFixture()
 def rejection(self,mutate,reason=''):
  mutate(self.f)
  with self.assertRaisesRegex(SourceError,reason):self.f.derive()
 def test_valid_fresh_manifest_derives_v3_without_registering_seed(self):
  s=self.f.derive();self.assertEqual(s['schemaVersion'],3);self.assertNotIn('reviewedManifestSha256',s);self.assertEqual(s['validation']['policy'],POLICY);validate_attachment(s,self.f.business)
  a=s['areas'][0];self.assertEqual([a[k] for k in ['activeAccountDenominator','activePaymentArrangementAccounts','activeHardshipProgramAccounts','activeAccountsInEitherSupport','paidGrantCountInPeriod','paidGrantAmountCentsInPeriod']],[2,1,1,1,2,30001]);self.assertIn('Uploader-declared',s['validation']['generator']['assertion']);self.assertNotIn('customer_id',json.dumps(s))
 def test_schema_valid_but_wrong_instalment_total_fails_after_rehash(self):self.rejection(lambda f:f.tables['payment_arrangements.csv.gz'][0].update(amount='299.99'),'instalment_total')
 def test_negative_nonfinite_exponent_and_fractional_cent_money_fail(self):
  for val in ['-1','NaN','Infinity','1e3','0.001','100000000000.00']:
   with self.subTest(val=val):
    f=SyntheticFixture();f.tables['hugs_grants.csv.gz'][0]['grant_amount']=val
    with self.assertRaisesRegex(SourceError,'money_'):f.derive()
 def test_invalid_instalment_count_and_customer_flags_fail(self):
  self.rejection(lambda f:f.tables['payment_arrangements.csv.gz'][0].update(n_instalments='-1'),'instalment_count');self.f=SyntheticFixture();self.rejection(lambda f:f.cs[0].update(has_solar='yes'),'customer_boolean')
 def test_usage_components_cannot_be_forged_with_rehashed_manifest(self):self.rejection(lambda f:f.us[0].update(import_kwh='1.000'),'usage_components')
 def test_solar_and_registration_consistency(self):
  self.rejection(lambda f:f.cs[0].update(solar_kw='1.0'),'customer_solar');self.f=SyntheticFixture();self.rejection(lambda f:f.cs[0].update(life_support='True'),'customer_registration')
 def test_missing_terminal_and_active_history_cannot_be_zero(self):
  self.rejection(lambda f:f.tables['support_arrangement_history.csv.gz'].pop(),'parent_history_complete');self.f=SyntheticFixture();self.rejection(lambda f:f.tables['support_arrangement_history.csv.gz'].clear(),'parent_history_complete')
 def test_orphan_duplicate_foreign_key_and_history_dates(self):
  for mutate,reason in [(lambda f:f.tables['payments.csv.gz'][0].update(customer_id='UNKNOWN'),'customer_not_in_cohort'),(lambda f:f.tables['payment_arrangements.csv.gz'].append(copy.deepcopy(f.tables['payment_arrangements.csv.gz'][0])),'duplicate_financial_parent'),(lambda f:f.tables['support_arrangement_history.csv.gz'][0].update(customer_id='D'),'parent_foreign_key'),(lambda f:f.tables['support_arrangement_history.csv.gz'][0].update(source_event_date='2025-06-02'),'support_event_date'),(lambda f:f.tables['support_arrangement_history.csv.gz'][0].update(effective_from='2025-07-01'),'outside_history')]:
   with self.subTest(reason=reason):self.f=SyntheticFixture();self.rejection(mutate,reason)
 def test_closure_after_snapshot_does_not_close_current_support(self):
  self.f.cs[0]['account_close_date']='2025-07-01'
  support=self.f.derive();self.assertEqual(self.f.business['snapshotDate'],'2025-06-30');self.assertEqual(self.f.business['totalAccounts'],2);self.assertEqual(support['areas'][0]['activePaymentArrangementAccounts'],1);self.assertEqual(support['areas'][0]['activeHardshipProgramAccounts'],1)
 def test_known_opening_and_closure_bounds_enforced(self):
  self.f.cs[0]['account_open_date']='2025-06-10';self.f.us[-1]=usage('D','2025-06-01')
  with self.assertRaisesRegex(SourceError,'account_lifecycle'):self.f.derive()
  self.f=SyntheticFixture();self.f.cs[0]['account_close_date']='2025-06-20';self.f.us[0]['date']='2025-06-20'
  with self.assertRaisesRegex(SourceError,'open_support_after_closure'):self.f.derive()
 def test_grant_cap_debt_interval_and_payment_match(self):
  for mutate,reason in [(lambda f:f.tables['hugs_grants.csv.gz'][0].update(region_cap='99.99'),'debt_or_cap'),(lambda f:f.tables['hugs_grants.csv.gz'][0].update(debt_at_application='99.99'),'debt_or_cap'),(lambda f:f.tables['hugs_grants.csv.gz'][0].update(application_date='2025-06-15'),'payment_interval'),(lambda f:f.tables['payments.csv.gz'][0].update(amount='101.00'),'grant_payment_join'),(lambda f:f.tables['payments.csv.gz'].pop(),'without_cleared_payment'),(lambda f:f.tables['payments.csv.gz'].append(copy.deepcopy(f.tables['payments.csv.gz'][0])),'duplicate_payment_id')]:
   with self.subTest(reason=reason):self.f=SyntheticFixture();self.rejection(mutate,reason)
 def test_rehashed_metadata_alone_does_not_establish_actual_rows_or_bytes(self):
  for key,val,reason in [('rows',0,'actual_row_count'),('bytes',1,'hash_or_size'),('expandedBytes',1,'expanded_size')]:
   c,u,s,m=self.f.packet();manifest=json.loads(m);manifest['files']['payments.csv.gz'][key]=val
   with self.subTest(key=key),self.assertRaisesRegex(SourceError,reason):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,s,canonical(manifest))
 def test_no_opt_in_unknown_policy_fake_geography_or_coverage(self):
  for mutate in [lambda m:m.pop('synthetic_financial_contract'),lambda m:m.update(synthetic_financial_contract='unknown'),lambda m:m.update(synthetic=False),lambda m:m.update(geography_sha256='1'*64),lambda m:m['financial_coverage']['accountPostcodes'].clear(),lambda m:m['parameters'].update(seed=True),lambda m:m['parameters'].update(count=True)]:
   c,u,s,m=self.f.packet();manifest=json.loads(m);mutate(manifest)
   with self.assertRaises(SourceError):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,s,canonical(manifest))
 def test_duplicate_json_keys_and_malformed_manifest_rejected(self):
  c,u,s,m=self.f.packet()
  for raw in [b'{"synthetic":true,"synthetic":false}',b'[]',b'{',b'\xff']:
   with self.assertRaises(SourceError):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,s,raw)
 def test_missing_or_extra_financial_table_fails(self):
  c,u,s,m=self.f.packet()
  for changed in [{k:v for k,v in s.items() if k!='payments.csv.gz'},{**s,'untrusted.csv.gz':b'x'}]:
   with self.assertRaisesRegex(SourceError,'complete_financial'):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,changed,m)
 def test_actual_gzip_expansion_bound_even_when_declared_size_lies(self):
  c,u,s,m=self.f.packet();metadata=json.loads(m)
  for f in metadata['files'].values():f['expandedBytes']=1
  with patch('synthetic_financial.MAX_EXPANDED',200),self.assertRaisesRegex(SourceError,'expanded_limit'):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,s,canonical(metadata))
 def test_manifest_row_and_batch_bounds_preflight(self):
  for edit in [lambda m:m['files']['payments.csv.gz'].update(rows=1500001),lambda m:m['files']['payment_arrangements.csv.gz'].update(rows=200001),lambda m:m['files']['support_arrangement_history.csv.gz'].update(rows=400001),lambda m:m['files']['customers.csv'].update(bytes=16777217),lambda m:m['files']['payments.csv.gz'].update(expandedBytes=100663297)]:
   c,u,s,m=self.f.packet();metadata=json.loads(m);edit(metadata)
   with self.assertRaises(SourceError):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,s,canonical(metadata))
 def test_receipt_ledger_schema_policy_and_aggregate_tampering_fail(self):
  original=self.f.derive()
  for edit in [lambda s:s['validation'].update(policy='unknown'),lambda s:s['validation']['generator'].update(assertion='Trusted real source'),lambda s:s['areas'][0].update(activeAccountsInEitherSupport=0),lambda s:s['monthlyGrantLedger'].append(s['monthlyGrantLedger'][0]),lambda s:s['monthlyGrantLedger'][0].update(paidGrantAmountCents=1),lambda s:s.update(customer_id='not-allowed')]:
   s=copy.deepcopy(original);edit(s)
   with self.assertRaises(SourceError):validate_synthetic_attachment(s,self.f.business)
 def test_even_rehashed_aggregate_cannot_break_ledger_invariants(self):
  s=self.f.derive();s['monthlyGrantLedger'][0]['paidGrantAmountCents']+=1;s['validation']['aggregateSha256']=digest(canonical({k:v for k,v in s.items() if k!='validation'}))
  with self.assertRaisesRegex(SourceError,'period_reconciliation'):validate_synthetic_attachment(s,self.f.business)

 def test_real_decoded_per_file_ceiling_streams_and_stops_before_csv(self):
  import io
  c,u,sidecars,m=self.f.packet();metadata=json.loads(m);buf=io.BytesIO()
  with gzip.GzipFile(fileobj=buf,mode='wb',mtime=0) as out:
   for _ in range(97):out.write(b'x'*(1024*1024))
  raw=buf.getvalue();sidecars['payments.csv.gz']=raw;entry=metadata['files']['payments.csv.gz'];entry.update(sha256=digest(raw),bytes=len(raw),expandedBytes=1)
  with self.assertRaisesRegex(SourceError,'expanded_limit'):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,sidecars,canonical(metadata))
 def test_real_encoded_per_file_ceiling_rejects_lying_manifest(self):
  c,u,sidecars,m=self.f.packet();raw=b'x'*(16*1024*1024+1);sidecars['payments.csv.gz']=raw;metadata=json.loads(m);metadata['files']['payments.csv.gz'].update(sha256=digest(raw),bytes=1,expandedBytes=1)
  with self.assertRaisesRegex(SourceError,'hash_or_size'):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,sidecars,canonical(metadata))
 def test_actual_batch_expansion_bound_is_checked_while_reading(self):
  c,u,sidecars,m=self.f.packet();metadata=json.loads(m)
  for entry in metadata['files'].values():entry['expandedBytes']=1
  with patch('synthetic_financial.MAX_BATCH_EXPANDED',200),self.assertRaisesRegex(SourceError,'expanded_limit'):derive_synthetic_context(c,u,self.f.trusted,source.NOW.date(),self.f.business,sidecars,canonical(metadata))

class SyntheticRecovery(unittest.TestCase):
 def setUp(self):
  source.Sources.setUp(self);self.store.read();self.f=SyntheticFixture();c,u,sidecars,m=self.f.packet();self.store.replace_business(self.f.business,self.store.read()['generation'])
  from financial_intake import PART_FILES
  by_name={'customers.csv':c,'consumption_daily.csv.gz':u,'manifest.json':m,**sidecars};self.files={key:by_name[name] for key,name in PART_FILES.items()};self.stages=FinancialStages(self.store,self.f.trusted,lambda:source.NOW);self.base=self.store.read()
 def tearDown(self):source.Sources.tearDown(self)
 def test_generic_stage_explicit_replace_restart_and_same_pair_retention(self):
  s=self.stages.stage(self.files,True,self.base['generation']);self.assertEqual(self.store.read()['generation'],self.base['generation']);self.assertEqual(s['proposedSupport']['schemaVersion'],3)
  p=self.stages.replace(s['stageId'],s['baseGeneration']);fresh=SnapshotStore(self.inputs,self.runtime,lambda:source.NOW).read();self.assertEqual(fresh['data'],p['data']);self.assertNotIn('customer_id',(self.runtime/'last-good.json').read_text())
  same=self.store.replace_business(self.f.business,p['generation']);self.assertEqual(same['data']['business']['financialSupport'],p['data']['business']['financialSupport'])
 def test_atomic_failure_wrong_generation_and_invalid_replacement_retain_last_good(self):
  proposal=self.stages.stage(self.files,True,self.base['generation']);before=(self.runtime/'last-good.json').read_bytes()
  with self.assertRaises(SourceError):self.stages.replace(proposal['stageId'],'0'*64)
  with patch.object(self.store,'_persist',side_effect=OSError('fixture disk full')),self.assertRaises(OSError):self.stages.replace(proposal['stageId'],proposal['baseGeneration'])
  self.assertEqual((self.runtime/'last-good.json').read_bytes(),before);p=self.stages.replace(proposal['stageId'],proposal['baseGeneration']);before=(self.runtime/'last-good.json').read_bytes();bad=copy.deepcopy(self.files);bad['payments']+=b'corrupt'
  with self.assertRaises(SourceError):self.stages.stage(bad,True,p['generation'])
  self.assertEqual((self.runtime/'last-good.json').read_bytes(),before)
