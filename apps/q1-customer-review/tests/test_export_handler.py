"""Exercise real export handlers in memory, reusing port8891 without binding."""
from email.message import Message
from io import BytesIO
import json
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from prototype.review import build_review
from prototype.uploads import UploadStore
from serve import Handler

class ExportHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.review=build_review()
    def setUp(self):
        self.tmp=TemporaryDirectory();self.store=UploadStore(self.tmp.name)
        self.store.state.update(active='test-batch',revision='A')
        self.store.cache['test-batch']=(self.review,{})
        self.server=SimpleNamespace(server_port=8891,request_token='ephemeral-test',review=self.review,demo_revision='demo-A',uploads=self.store)
    def tearDown(self):self.tmp.cleanup()
    def request(self,path,mode='upload',ids=None,revision=None):
        h=Handler.__new__(Handler);h.server=self.server;h.path=path;h.headers=Message()
        raw=json.dumps({'mode':mode,'batch_revision':revision or ('A' if mode=='upload' else 'demo-A'),'customer_ids':ids or ['C103794']}).encode()
        for k,v in {'Host':'127.0.0.1:8891','Origin':'http://127.0.0.1:8891','X-Q1-Request-Token':'ephemeral-test','Content-Type':'application/json','Content-Length':str(len(raw))}.items():h.headers[k]=v
        h.rfile=BytesIO(raw);h.wfile=BytesIO();h.connection=SimpleNamespace(settimeout=lambda value:None)
        result={'headers':{}}
        h.send_response=lambda status:result.update(status=status)
        h.send_header=lambda name,value:result['headers'].update({name:value})
        h.end_headers=lambda:None
        h.do_POST();result['body']=h.wfile.getvalue();return result
    def test_selected_pdf_payload_is_projected_and_deduplicated_without_changing_context(self):
        seen=[]
        def render(*args,**kwargs):seen.append(json.loads(kwargs['input']));return SimpleNamespace(stdout=b'%PDF-1.4 test')
        ids=['C102502','C105072','C102502']
        with patch('serve.subprocess.run',render):r=self.request('/api/customer-summary.pdf',ids=ids)
        self.assertEqual(r['status'],200);self.assertEqual(r['headers']['Content-Type'],'application/pdf')
        payload=seen[0];self.assertEqual(payload['customer_ids'],ids)
        self.assertEqual([x['customer']['customer_id'] for x in payload['review']['customers']],ids[:2])
        self.assertEqual(payload['review']['weather'],self.review['weather']);self.assertEqual(payload['review']['batch_revision'],'A')
    def test_replacement_during_pdf_render_still_rejects_download(self):
        def render(*args,**kwargs):
            with self.store.lock:self.store.state['revision']='B'
            return SimpleNamespace(stdout=b'%PDF-1.4 test')
        with patch('serve.subprocess.run',render):r=self.request('/api/customer-summary.pdf')
        self.assertEqual(r['status'],409);self.assertIn('changed',json.loads(r['body'])['error'])
    def test_replacement_during_csv_generation_still_rejects_download(self):
        def csv(*args):
            with self.store.lock:self.store.state['revision']='B'
            return iter([b'test'])
        with patch('serve.iter_csv_chunks',csv):r=self.request('/api/export.csv')
        self.assertEqual(r['status'],409)
    def test_valid_csv_retains_version_and_values(self):
        r=self.request('/api/export.csv');self.assertEqual(r['status'],200)
        self.assertEqual(r['headers']['X-Q1-Data-Version'],'A');self.assertIn(b'30.79099107142857',r['body'])
    def test_oversize_csv_is_rejected_before_download_headers_or_any_csv_bytes(self):
        with patch('serve.MAX_CSV_BYTES',10):r=self.request('/api/export.csv')
        self.assertEqual(r['status'],413);self.assertNotIn('Content-Disposition',r['headers']);self.assertIn('error',json.loads(r['body']))
    def test_stale_pdf_never_starts_renderer_and_unknown_selection_is_rejected(self):
        with patch('serve.subprocess.run',side_effect=AssertionError('should not render')):
            self.assertEqual(self.request('/api/customer-summary.pdf',revision='old')['status'],409)
            self.assertEqual(self.request('/api/customer-summary.pdf',ids=['unknown'])['status'],409)
