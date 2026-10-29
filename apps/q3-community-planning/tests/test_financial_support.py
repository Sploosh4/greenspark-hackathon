import copy,csv,gzip,io,json,unittest
from datetime import date
import test_source_adapter as base
from test_business_upload import customer,usage,file_bytes
from business_upload import CUSTOMER_HEADERS,USAGE_HEADERS,derive_business,load_trusted_context
from financial_support import HEADERS,derive_support_context,unavailable_support
from source_adapter import SourceError,digest,canonical

class Support(unittest.TestCase):
 def setUp(self):
  self.trusted=load_trusted_context(base.ROOT/'data/inputs')
  self.customers=file_bytes(CUSTOMER_HEADERS,[customer('A'),customer('B',closed='2025-06-30'),customer('C',opened=''),customer('D')])
  self.usage=file_bytes(USAGE_HEADERS,[usage('A','2025-06-30'),usage('B','2025-06-30'),usage('C','2025-06-30'),usage('D','2025-06-30'),usage('A','2025-06-01')])
  self.business=derive_business(self.customers,self.usage,False,self.trusted,date(2026,10,28))[0]
  self.rows={k:[] for k in HEADERS}
  self.add('payment_arrangements.csv.gz',arrangement_id='PA',customer_id='A',type='payment_plan',start_date='2025-06-01',status='active')
  self.add('payment_arrangements.csv.gz',arrangement_id='PD',customer_id='D',type='payment_plan',start_date='2025-06-01',end_date='2025-06-30',status='completed')
  self.add('hardship_programs.csv.gz',hardship_id='HA',customer_id='A',assessment_date='2025-06-01',assessment_outcome='accepted',start_date='2025-06-01')
  for ident,cid,typ,table,end in [('PA','A','payment_plan','payment_arrangements',''),('PD','D','payment_plan','payment_arrangements','2025-06-30'),('HA','A','hardship_program','hardship_programs','')]:
   self.add('support_arrangement_history.csv.gz',history_id=ident+':1',arrangement_id=ident,customer_id=cid,arrangement_type=typ,status='active',effective_from='2025-06-01',effective_to=end,source_event_date='2025-06-01',source_table=table)
  for i,amount in [(1,'100.00'),(2,'200.01')]:
   self.add('hugs_grants.csv.gz',hugs_id='G'+str(i),customer_id='A',application_date='2025-06-01',payment_date='2025-06-14',grant_amount=amount,outcome='approved',hardship_id='HA')
   self.add('payments.csv.gz',payment_id='P_G'+str(i),customer_id='A',date='2025-06-14',amount=amount,method='hugs_grant',kind='hugs_grant',status='cleared')
 def add(self,name,**values):
  self.rows[name].append({k:str(values.get(k,'')) for k in HEADERS[name]})
 def packet(self):
  sidecars={k:gzip.compress(file_bytes(HEADERS[k],v),mtime=0) for k,v in self.rows.items()}
  files={k:{'sha256':digest(raw),'headers':HEADERS[k],'rows':len(self.rows[k])} for k,raw in sidecars.items()}
  files.update({'customers.csv':{'sha256':digest(self.customers)},'consumption_daily.csv':{'sha256':digest(self.usage)}})
  manifest=canonical({'files':files});return sidecars,manifest,digest(manifest)
 def derive(self):
  s,m,h=self.packet();return derive_support_context(self.customers,self.usage,False,self.trusted,date(2026,10,28),self.business,s,m,h)
 def test_snapshot_union_deduplicates_and_end_is_exclusive(self):
  p=self.derive();a=p['areas'][0];self.assertEqual([a[k] for k in ['activeAccountDenominator','activePaymentArrangementAccounts','activeHardshipProgramAccounts','activeAccountsInEitherSupport']],[2,1,1,1]);self.assertEqual(a['snapshotDate'],'2025-06-30')
 def test_paid_grants_count_once_distinct_accounts_not_double_money(self):
  p=self.derive()['monthlyGrantLedger'][0];self.assertEqual([p[k] for k in ['retainedAccountsReceivingPaidGrant','paidGrantCount','paidGrantAmountCents']],[1,2,30001])
 def test_missing_sidecars_is_not_zero(self):
  self.assertEqual(unavailable_support()['state'],'unavailable');s,m,h=self.packet();s.pop('payments.csv.gz')
  with self.assertRaisesRegex(SourceError,'complete_financial'):derive_support_context(self.customers,self.usage,False,self.trusted,date(2026,10,28),self.business,s,m,h)
 def test_different_core_snapshot_is_rejected(self):
  self.business['snapshotDate']='2025-05-31'
  with self.assertRaisesRegex(SourceError,'cohort_or_snapshot'):self.derive()
 def test_tampered_manifest_and_table_are_rejected(self):
  s,m,h=self.packet()
  with self.assertRaisesRegex(SourceError,'manifest_hash'):derive_support_context(self.customers,self.usage,False,self.trusted,date(2026,10,28),self.business,s,m+b' ',h)
  s['payments.csv.gz']+=b'bad'
  with self.assertRaisesRegex(SourceError,'source_hash'):derive_support_context(self.customers,self.usage,False,self.trusted,date(2026,10,28),self.business,s,m,h)
 def test_unrelated_customer_and_wrong_parent_join_fail(self):
  self.rows['support_arrangement_history.csv.gz'][0]['customer_id']='Z'
  with self.assertRaisesRegex(SourceError,'customer_not_in_cohort'):self.derive()
  self.rows['support_arrangement_history.csv.gz'][0]['customer_id']='D'
  with self.assertRaisesRegex(SourceError,'parent_foreign_key'):self.derive()
 def test_overlap_and_duplicate_history_rejected(self):
  self.rows['support_arrangement_history.csv.gz'].append(copy.deepcopy(self.rows['support_arrangement_history.csv.gz'][0]))
  with self.assertRaisesRegex(SourceError,'duplicate_support'):self.derive()
  self.rows['support_arrangement_history.csv.gz'][-1]['history_id']='PA:2'
  with self.assertRaisesRegex(SourceError,'overlapping_support'):self.derive()
 def test_future_event_and_unpaid_grant_rejected(self):
  self.rows['payments.csv.gz'][0]['date']='2025-07-01'
  with self.assertRaisesRegex(SourceError,'outside_history'):self.derive()
  self.rows['payments.csv.gz'][0]['date']='2025-06-14';self.rows['payments.csv.gz'].pop()
  with self.assertRaisesRegex(SourceError,'without_cleared_payment'):self.derive()
 def test_no_raw_identifiers_or_risk_values_in_result(self):
  p=self.derive();text=json.dumps(p);self.assertNotIn('customer_id',text);self.assertNotIn('P_G1',text);self.assertNotIn('debt_at_entry',text);self.assertNotIn('riskScore',text)
 def test_two_file_contract_still_has_no_support_claim(self):
  self.assertNotIn('financialSupport',self.business);self.assertFalse(any('activePaymentArrangementAccounts' in a for a in self.business['areas']))


 def test_active_parent_without_history_is_not_a_validated_zero(self):
  self.rows['support_arrangement_history.csv.gz'].clear()
  with self.assertRaisesRegex(SourceError,'parent_history_incomplete'):self.derive()
