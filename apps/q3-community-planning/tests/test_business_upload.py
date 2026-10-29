import copy,csv,gzip,io,json,unittest
from datetime import timedelta
from unittest.mock import patch
import test_source_adapter as fixtures
NOW=fixtures.NOW;ROOT=fixtures.ROOT
from business_upload import CUSTOMER_HEADERS,USAGE_HEADERS,derive_business,UploadStages,load_trusted_context
from source_adapter import SnapshotStore,SourceError

def file_bytes(headers,rows):
    out=io.StringIO();w=csv.DictWriter(out,fieldnames=headers);w.writeheader();w.writerows(rows);return out.getvalue().encode()
def customer(ident,opened='2020-01-01',closed='',pc='6765',name='Fitzroy Crossing',prepaid='True'):
    row={k:'' for k in CUSTOMER_HEADERS};row.update(customer_id=ident,postcode=pc,locality=name,prepayment_meter=prepaid,account_open_date=opened,account_close_date=closed);return row
def usage(ident,day='2025-07-01'):
    row={k:'0' for k in USAGE_HEADERS};row.update(customer_id=ident,date=day,supply_status='connected');return row

class Uploads(unittest.TestCase):
    tearDown=fixtures.Sources.tearDown
    def setUp(self):
        fixtures.Sources.setUp(self);self.current=self.store.read();self.trusted=self.current['data']['business'];self.uploads=UploadStages(self.store,self.trusted,lambda:NOW)
    def derive(self,cs,us):return derive_business(file_bytes(CUSTOMER_HEADERS,cs),file_bytes(USAGE_HEADERS,us),False,self.trusted,NOW.date())[0]
    def stage(self,cs=None,us=None):return self.uploads.stage(file_bytes(CUSTOMER_HEADERS,cs or [customer('NEW1')]),file_bytes(USAGE_HEADERS,us or [usage('NEW1')]),False,True)
    def test_changed_cohort_and_dates_are_valid_not_fixed_393(self):
        b=self.derive([customer('NEW1'),customer('NEW2',prepaid='False')],[usage('NEW1'),usage('NEW2')]);self.assertEqual((b['snapshotDate'],b['totalAccounts'],b['retainedTotalAccounts']),('2025-07-01',2,2));self.assertEqual(len(b['areas']),1)
    def test_unknown_closed_and_later_open_separate_not_guessed(self):
        cs=[customer('A'),customer('B',opened=''),customer('C',closed='2025-06-30'),customer('D',opened='2025-08-01'),customer('E')]
        b=self.derive(cs,[usage('A'),usage('B'),usage('C','2025-06-29')]);self.assertEqual([b[k] for k in ['totalAccounts','closedAccounts','unknownStatusAccounts','notOpenAtSnapshotAccounts']],[1,1,2,1])
    def test_closure_on_cutoff_is_closed_even_with_usage(self):
        b=self.derive([customer('A',closed='2025-07-01')],[usage('A')]);self.assertEqual(b['totalAccounts'],0);self.assertEqual(b['closedAccounts'],1)
    def test_disconnected_supply_does_not_close_account(self):
        r=usage('A');r['supply_status']='disconnected_non_payment';self.assertEqual(self.derive([customer('A')],[r])['totalAccounts'],1)
    def test_stage_does_not_replace_or_persist_raw_rows(self):
        staged=self.stage();self.assertEqual(self.store.read()['generation'],self.current['generation']);self.assertEqual(self.store.read()['data']['business']['totalAccounts'],393);self.assertNotIn('NEW1',json.dumps(staged));self.assertFalse((self.runtime/'stages').exists())
    def test_explicit_replace_atomic_and_survives_restart(self):
        s=self.stage();p=self.uploads.replace(s['stageId'],s['baseGeneration']);self.assertEqual(p['data']['business']['totalAccounts'],1);self.assertEqual(p['status']['business_snapshot_date'],'2025-07-01');self.assertNotIn('NEW1',(self.runtime/'last-good.json').read_text());self.assertEqual(SnapshotStore(self.inputs,self.runtime,lambda:NOW).read()['data']['business']['totalAccounts'],1)
        self.assertEqual(self.store.read()['data']['mean'],self.current['data']['mean']);self.assertEqual(self.store.read()['data']['history'],self.current['data']['history'])
    def test_persistence_failure_retains_previous_exact_generation(self):
        s=self.stage();before=(self.runtime/'last-good.json').read_bytes()
        with patch.object(self.store,'_persist',side_effect=OSError('simulated full disk')):
            with self.assertRaises(OSError):self.uploads.replace(s['stageId'],s['baseGeneration'])
        self.assertEqual(self.store.read()['generation'],self.current['generation']);self.assertEqual((self.runtime/'last-good.json').read_bytes(),before)
    def test_other_replacement_requires_restage(self):
        a=self.stage();b=self.stage();self.uploads.replace(a['stageId'],a['baseGeneration'])
        with self.assertRaisesRegex(SourceError,'active_snapshot_changed'):self.uploads.replace(b['stageId'],b['baseGeneration'])
    def test_expired_stage_and_one_use(self):
        s=self.stage();self.uploads.clock=lambda:NOW+timedelta(minutes=31)
        with self.assertRaisesRegex(SourceError,'stage_missing_or_expired'):self.uploads.replace(s['stageId'],s['baseGeneration'])
        self.uploads.clock=lambda:NOW;s=self.stage();self.uploads.replace(s['stageId'],s['baseGeneration'])
        with self.assertRaises(SourceError):self.uploads.replace(s['stageId'],s['baseGeneration'])
    def test_discard_keeps_active_data(self):
        s=self.stage();self.uploads.discard(s['stageId']);self.assertEqual(self.store.read()['generation'],self.current['generation'])
        with self.assertRaises(SourceError):self.uploads.replace(s['stageId'],s['baseGeneration'])
    def test_duplicate_and_unknown_ids_and_dates_rejected(self):
        cases=[([customer('A'),customer('A')],[usage('A')]),([customer('A')],[usage('OTHER')]),([customer('A')],[usage('A'),usage('A')]),([customer('A')],[usage('A','2026-12-01')]),([customer('A',opened='2025-08-01')],[usage('A')]),([customer('A',closed='2025-06-01')],[usage('A')]),([customer('A',pc='9999')],[usage('A')])]
        for cs,us in cases:
            with self.subTest(cs=cs,us=us),self.assertRaises(SourceError):self.derive(cs,us)
    def test_bad_header_gzip_empty_and_numeric_rejected(self):
        raw=file_bytes(CUSTOMER_HEADERS,[customer('A')]);u=file_bytes(USAGE_HEADERS,[usage('A')])
        for bad,compressed in [(b'bad gzip',True),(b'',False),(u.replace(b'0,0,0',b'NaN,0,0'),False)]:
            with self.subTest(bad=bad[:20]),self.assertRaises(SourceError):derive_business(raw,bad,compressed,self.trusted,NOW.date())
        with self.assertRaises(SourceError):derive_business(b'customer_id\nA\n',u,False,self.trusted,NOW.date())
    def test_compressed_plain_equal_and_expansion_limit(self):
        raw=file_bytes(CUSTOMER_HEADERS,[customer('A')]);u=file_bytes(USAGE_HEADERS,[usage('A')]);a=derive_business(raw,u,False,self.trusted,NOW.date())[0];b=derive_business(raw,gzip.compress(u),True,self.trusted,NOW.date())[0];self.assertEqual(a['areas'],b['areas'])
        with patch('business_upload.MAX_EXPANDED',10),self.assertRaisesRegex(SourceError,'expanded_size_limit'):derive_business(raw,gzip.compress(u),True,self.trusted,NOW.date())
    def test_declaration_and_stage_bound_required(self):
        with self.assertRaisesRegex(SourceError,'synthetic_declaration_required'):self.uploads.stage(b'',b'',False,False)
        for _ in range(4):self.stage()
        with self.assertRaisesRegex(SourceError,'too_many_staged'):self.stage()
    def test_corrupt_persisted_override_does_not_silently_reset_to_seed(self):
        s=self.stage();self.uploads.replace(s['stageId'],s['baseGeneration']);p=self.runtime/'last-good.json';p.write_text('{}');self.assertIsNone(SnapshotStore(self.inputs,self.runtime,lambda:NOW).read()['data'])

    def test_absent_area_is_unavailable_in_review_not_zero(self):
        s=self.stage();fitz=next(a for a in s['differences'] if a['postcode']=='6765');broome=next(a for a in s['differences'] if a['postcode']=='6725');self.assertEqual(fitz['after'],1);self.assertIsNone(broome['after']);self.assertEqual(broome['before'],44)
    def test_bad_seed_disables_upload_without_crashing_cached_map(self):
        s=self.stage();self.uploads.replace(s['stageId'],s['baseGeneration']);(self.inputs/'q3-area-context.json').write_text('{')
        trusted=load_trusted_context(self.inputs);self.assertIsNone(trusted)
        restarted=SnapshotStore(self.inputs,self.runtime,lambda:NOW);p=restarted.read();self.assertEqual(p['data']['business']['totalAccounts'],1)
        (self.inputs/'q3-area-context.json').unlink();self.assertEqual(SnapshotStore(self.inputs,self.runtime,lambda:NOW).read()['status']['state'],'stale')
        with self.assertRaisesRegex(SourceError,'trusted_upload_context_unavailable'):UploadStages(restarted,trusted,lambda:NOW).stage(b'',b'',False,True)
    def test_hash_mismatch_never_supplies_trusted_upload_context(self):
        self.assertIsNotNone(load_trusted_context(self.inputs));p=self.inputs/'q3-area-context.json';p.write_text(p.read_text()+' ');self.assertIsNone(load_trusted_context(self.inputs))
