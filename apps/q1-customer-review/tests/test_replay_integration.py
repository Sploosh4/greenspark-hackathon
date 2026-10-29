"""Sealed replay arithmetic, in-process handlers and actual local PDF bytes."""
from copy import deepcopy
import csv,json,hashlib,os
from io import BytesIO,StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pypdf import PdfReader
import pdfplumber
from prototype.inputs import DEFAULT_SOURCE
from prototype.replay_snapshot import load_snapshot,seal,digest,MODE,compose_review
from prototype.exports import csv_bytes
from prototype.uploads import UploadStore
import tests.test_export_handler as export_handlers
import tests.test_auth_handler as auth_handlers
from serve import Handler,make_server
from pdf_export import create_summary,create_condensed_summary

ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT=ROOT/'replay-data/cohort.json'

class ReplaySnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.review=load_snapshot(SNAPSHOT,source_root=DEFAULT_SOURCE,availability_mode=MODE)
    def test_default_runtime_loading_is_strict_and_live_never_estimates(self):
        for opts in ({},{'availability_mode':'live'}):
            review=load_snapshot(SNAPSHOT,source_root=DEFAULT_SOURCE,**opts)
            for row in review['customers']:
                self.assertEqual(row['replay_evidence']['events'],[])
                for prediction in row['predictions']:
                    self.assertIsNone(prediction['predicted']);self.assertIsNone(prediction['increase'])
                    self.assertIsNone(prediction['comparison']['predicted']);self.assertNotIn('source_event',prediction)
                self.assertTrue(row['legacy_predictions'])
    def test_integrity_and_internal_snapshot_identity_are_enforced(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'snapshot.json';envelope=json.loads(SNAPSHOT.read_bytes())
            envelope['review']['customers'][0]['predictions'][0]['predicted']=900
            path.write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError,'integrity'):load_snapshot(path,source_root=DEFAULT_SOURCE,availability_mode=MODE)
            envelope['review_sha256']=digest(envelope['review']);path.write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError,'identity'):load_snapshot(path,source_root=DEFAULT_SOURCE,availability_mode=MODE)
    def test_changed_or_missing_source_is_not_silently_accepted(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(OSError):load_snapshot(SNAPSHOT,source_root=tmp,availability_mode=MODE)
        with patch('prototype.replay_snapshot.MAX_BYTES',10):
            with self.assertRaisesRegex(ValueError,'16MiB'):load_snapshot(SNAPSHOT,source_root=DEFAULT_SOURCE)
    def test_hand_arithmetic_and_reviewed_eligibility(self):
        row=next(r for r in self.review['customers'] if r['customer']['customer_id']=='C103794')
        p=row['predictions'][0];episode=row['episodes'][-1]
        self.assertAlmostEqual(p['predicted'],30.2332970552,places=9)
        self.assertAlmostEqual(p['baseline'],28.0349454545,places=9)
        self.assertAlmostEqual(p['increase'],100*(p['predicted']/p['baseline']-1),places=11)
        self.assertAlmostEqual(p['event_total'],3*p['predicted'],places=11)
        self.assertAlmostEqual(p['comparison']['predicted'],31.8810534043,places=9)
        linked=next(e for e in row['episodes'] if e['start']=='2024-10-22')
        self.assertAlmostEqual(linked['actual_mean'],107.825/4,places=10)
        self.assertAlmostEqual(linked['denominator'],27.0071818182,places=9)
        self.assertAlmostEqual(linked['increase_percent'],100*((107.825/4)/linked['denominator']-1),places=10)
        self.assertTrue(row['replay_evidence']['qualifies']['M5'])
        other=next(r for r in self.review['customers'] if r['customer']['customer_id']=='C102502')
        self.assertFalse(other['replay_evidence']['qualifies']['M5'])
    def test_reporting_and_legacy_separation(self):
        for row in self.review['customers']:
            self.assertTrue(all(r['date']<='2024-10-31' for r in row['usage']+row['financial']+row['records']))
            self.assertEqual(row['history_coverage']['available_days'],489)
            self.assertEqual(row['history_coverage']['expected_days'],731)
            self.assertTrue(all(p['method_id']=='frozen-v3-M5-simulated-replay' for p in row['predictions']))
            self.assertTrue(all('frozen-v3-M5' not in p['method_id'] for p in row['legacy_predictions']))
        self.assertEqual(len(self.review['past_events']),4)
        self.assertIsNone(self.review['replay']['original_available_at'])
    def test_explicit_alternative_preserves_kwh_and_changes_only_denominator_meaning(self):
        from prototype.review import build_review
        common=json.loads((Path(os.environ.get('Q1_REPLAY_CONTRACT_STAGE',str(ROOT.parents[1]/'staged-v3-replay-contract')))/'evidence/cohort-common_review_B.json').read_text())
        alternative=compose_review(build_review(),common,model_manifest_sha256=self.review['replay']['model_manifest_sha256'],source_files=self.review['replay']['source_files_sha256'],past_events=self.review['past_events'],policy='common_review_B')
        seal(alternative)
        self.assertNotEqual(alternative['snapshot_id'],self.review['snapshot_id'])
        for left,right in zip(self.review['customers'],alternative['customers']):
            self.assertEqual(left['predictions'],right['predictions'])
            for past in right['episodes']:
                p=right['predictions'][0];self.assertEqual(past['denominator'],p['baseline'])
                if past['actual_mean'] is not None:self.assertAlmostEqual(past['increase_percent'],100*(past['actual_mean']/p['baseline']-1))
    def test_make_server_uses_exact_snapshot_revision_without_binding(self):
        with TemporaryDirectory() as tmp,patch('serve.ThreadingHTTPServer',return_value=SimpleNamespace()) as factory:
            server=make_server(store_root=tmp,replay_snapshot=SNAPSHOT,replay_mode=MODE)
            try:
                factory.assert_called_once_with(('127.0.0.1',8891),Handler)
                self.assertEqual(server.demo_revision,self.review['snapshot_id'])
                self.assertEqual(server.review,self.review)
            finally:server.upload_jobs.close()
    def test_snapshot_is_not_a_static_download_route(self):
        handler=Handler.__new__(Handler);handler.path='/replay-data/cohort.json'
        self.assertFalse(handler.static_allowed())

class ReplayExportHandlerTests(unittest.TestCase):
    request=export_handlers.ExportHandlerTests.request
    @classmethod
    def setUpClass(cls):cls.review=load_snapshot(SNAPSHOT,source_root=DEFAULT_SOURCE,availability_mode=MODE)
    def setUp(self):
        self.tmp=TemporaryDirectory();self.store=UploadStore(self.tmp.name)
        self.server=SimpleNamespace(server_port=8891,request_token='ephemeral-test',review=self.review,demo_revision=self.review['snapshot_id'],uploads=self.store)
    def tearDown(self):self.tmp.cleanup()
    def request_demo(self,path,ids=None):return self.request(path,mode='demo',ids=ids,revision=self.review['snapshot_id'])
    def test_get_and_csv_are_same_snapshot_and_values(self):
        h=Handler.__new__(Handler);h.server=self.server
        review=h.review('demo');self.assertEqual(review['batch_revision'],self.review['snapshot_id'])
        result=self.request_demo('/api/export.csv');self.assertEqual(result['status'],200)
        self.assertEqual(result['headers']['X-Q1-Data-Version'],review['batch_revision'])
        row=next(r for r in review['customers'] if r['customer']['customer_id']=='C103794');p=row['predictions'][0]
        csv_row=next(csv.DictReader(StringIO(result['body'].decode('utf-8-sig'))))
        for column,key in [('estimated_daily_import_kwh','predicted'),('expected_increase_percent','increase'),('estimated_event_import_kwh','event_total')]:self.assertEqual(float(csv_row[column]),p[key])
        self.assertEqual(float(csv_row['S1_daily_import_kwh']),p['comparison']['predicted'])
        self.assertAlmostEqual(float(csv_row['past_observed_daily_import_kwh']),107.825/4)
        self.assertAlmostEqual(float(csv_row['past_baseline_daily_import_kwh']),27.0071818182,places=9)
        self.assertEqual(result['body'],(ROOT/'replay-data/cohort.csv').read_bytes())
        self.assertEqual(csv_row['percentage_policy'],'event_local_B');self.assertEqual(csv_row['snapshot_id'],review['batch_revision'])
    def test_real_pdf_handler_selected_one_and_multiple(self):
        for ids in (['C103794'],['C103794','C102502']):
            result=self.request_demo('/api/customer-summary.pdf',ids)
            self.assertEqual(result['status'],200,result['body'][:300]);self.assertEqual(result['headers']['Content-Type'],'application/pdf')
            self.assertEqual(result['headers']['X-Q1-Data-Version'],self.review['snapshot_id'])
            self.assertTrue(result['body'].startswith(b'%PDF-'))
            text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(result['body'])).pages)
            for word in ['30.2 kWh','31.9 kWh/day','+7.8%','-0.2%','26.96 kWh/day','27.01 kWh/day','event_local_B','Simulated historical replay']:
                self.assertIn(word,text)
            for cid in ids:self.assertIn(cid,text)
    def test_stale_revision_and_replacement_during_export_are_rejected(self):
        self.assertEqual(self.request('/api/export.csv',mode='demo',revision='old')['status'],409)
        def render(*args,**kwargs):self.server.demo_revision='replacement';return SimpleNamespace(stdout=b'%PDF-1.4 test')
        with patch('serve.subprocess.run',render):self.assertEqual(self.request_demo('/api/customer-summary.pdf')['status'],409)
    def test_restart_load_retains_exact_view_and_upload_generation(self):
        first=load_snapshot(SNAPSHOT,source_root=DEFAULT_SOURCE,availability_mode=MODE)
        second=load_snapshot(SNAPSHOT,source_root=DEFAULT_SOURCE,availability_mode=MODE)
        self.assertEqual(first,second);self.assertEqual(self.store.status()['revision'],'none')

class ReplayPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review=load_snapshot(SNAPSHOT,source_root=DEFAULT_SOURCE,availability_mode=MODE)
        cls.review.update(data_mode='demo',batch_id='preloaded',batch_revision=cls.review['snapshot_id'])
    def test_missing_zero_long_values_and_condensed_geometry(self):
        d=deepcopy(self.review);row=next(r for r in d['customers'] if r['customer']['customer_id']=='C103794')
        row['customer']['locality']='Long locality '+('longword'*22)
        p=row['predictions'][0];p.update(predicted=None,increase=None,event_total=None)
        for renderer in (create_summary,create_condensed_summary):
            raw=renderer(d,['C103794','C102502']);text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(raw)).pages)
            self.assertIn('Unavailable',text);self.assertIn('S1',text)
            with pdfplumber.open(BytesIO(raw)) as doc:
                for page in doc.pages:
                    for char in page.chars:
                        self.assertGreaterEqual(char['x0'],43);self.assertLessEqual(char['x1'],page.width-43)
                        self.assertGreaterEqual(char['top'],20);self.assertLessEqual(char['bottom'],page.height-20)
        p.update(predicted=p['baseline'],increase=0,event_total=p['baseline']*p['duration'])
        text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(create_summary(d,['C103794']))).pages)
        self.assertIn('0.0%',text)

class ReplayAuthenticatedHandlerTests(unittest.TestCase):
    request=auth_handlers.AuthHandlerTests.request
    login=auth_handlers.AuthHandlerTests.login
    @classmethod
    def setUpClass(cls):auth_handlers.AuthHandlerTests.setUpClass.__func__(cls)
    def setUp(self):
        auth_handlers.AuthHandlerTests.setUp(self)
        self.server.review=load_snapshot(SNAPSHOT,source_root=DEFAULT_SOURCE,availability_mode=MODE)
        self.server.demo_revision=self.server.review['snapshot_id']
    def tearDown(self):auth_handlers.AuthHandlerTests.tearDown(self)
    def test_existing_role_csrf_and_revocation_protect_replay_exports(self):
        for role in ('officer','manager'):
            self.assertEqual(self.request('/api/review')['status'],401)
            headers=self.login(role);reply=self.request('/api/review',headers=headers)
            revision=reply['body']['batch_revision'];self.assertEqual(revision,self.server.demo_revision)
            payload={'mode':'demo','batch_revision':revision,'customer_ids':['C103794']}
            bad=self.request('/api/export.csv','POST',payload,{**headers,'X-Team-Connect-CSRF':'wrong'})
            self.assertEqual(bad['status'],403)
            result=self.request('/api/export.csv','POST',payload,headers);self.assertEqual(result['status'],200)
            self.assertIn(b'30.233297055',result['raw'])
            self.assertEqual(self.request('/api/auth/logout','POST',{},headers)['status'],200)
            self.assertEqual(self.request('/api/export.csv','POST',payload,headers)['status'],401)
