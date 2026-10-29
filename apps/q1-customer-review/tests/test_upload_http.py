"""Actual loopback HTTP acceptance, including interrupted request bodies."""
import http.client
import json
from pathlib import Path
import socket
import os,time
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import uuid
from prototype.inputs import DEFAULT_SOURCE
from prototype.review import build_review
from prototype.uploads import MAX_BODY
from serve import make_server,Handler
from tests.make_upload_fixtures import fixture_parts,mutate

def op():return uuid.uuid4().hex
def multipart(parts,request,revision):
    boundary='Q1Boundary'+uuid.uuid4().hex;chunks=[]
    for name,raw in parts:
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),raw,b'\r\n'])
    for name,value in [('request_id',request),('expected_revision',revision)]:chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(f'--{boundary}--\r\n'.encode());return b''.join(chunks),'multipart/form-data; boundary='+boundary

@unittest.skipUnless(os.environ.get('Q1_CANONICAL_SOCKET_TESTS')=='1','Requires coordinated ownership of canonical port8891; in-process handler tests run by default')
class HttpUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.demo=build_review();cls.a=fixture_parts();cls.b=fixture_parts(('C103794','C105072'),True)
    def setUp(self):
        self.tmp=TemporaryDirectory();self.log=patch.object(Handler,'log_message',lambda *args:None);self.log.start();self.start()
    def start(self):
        self.server=make_server(8891,Path(self.tmp.name),self.demo);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base=f'http://127.0.0.1:{self.server.server_port}';self.state=self.get('/api/state')[2];self.token=self.state['request_token']
    def stop(self):self.server.shutdown();self.server.upload_jobs.close();self.server.server_close();self.thread.join(2)
    def tearDown(self):self.stop();self.log.stop();self.tmp.cleanup()
    def request(self,path,body=None,headers=None,method=None):
        req=Request(self.base+path,data=body,headers=headers or {},method=method)
        try:r=urlopen(req,timeout=20)
        except HTTPError as e:r=e
        raw=r.read();ct=r.headers.get('Content-Type','');result=json.loads(raw) if ct.startswith('application/json') else raw
        status=r.status;headers=r.headers;r.close();return status,headers,result
    def get(self,path):return self.request(path)
    def post(self,path,value,**extra):
        headers={'Content-Type':'application/json','Origin':self.base,'X-Q1-Request-Token':self.token,**extra};return self.request(path,json.dumps(value).encode(),headers,'POST')
    def stage(self,parts=None,revision=None,request=None):
        raw,ct=multipart(parts or self.a,request or op(),revision or self.get('/api/state')[2]['revision'])
        status,headers,job=self.request('/api/uploads/stage',raw,{'Content-Type':ct,'Origin':self.base,'X-Q1-Request-Token':self.token},'POST')
        if status!=202:return status,headers,job
        deadline=time.monotonic()+75
        while time.monotonic()<deadline:
            status,headers,job=self.get('/api/uploads/status?request_id='+job['request_id'])
            if status!=200:return status,headers,job
            if job['state']=='ready':return 200,headers,job['receipt']
            if job['state'] in ('failed','cancelled'):return 400,headers,{'error':job.get('error','Upload cancelled')}
            time.sleep(.02)
        self.fail('Asynchronous upload did not finish within75seconds')
    def activate(self,parts=None):
        status,_,r=self.stage(parts);self.assertEqual(status,200,r)
        status,_,state=self.post('/api/uploads/activate',{'stage_id':r['stage_id'],'expected_revision':r['expected_revision'],'confirm_replace':True});self.assertEqual(status,200,state);return state
    def test_confirmation_snapshot_and_versioned_csv_pdf(self):
        _,_,receipt=self.stage();self.assertEqual(self.get('/api/review?mode=upload')[0],404)
        body={'stage_id':receipt['stage_id'],'expected_revision':'none'};self.assertEqual(self.post('/api/uploads/activate',body)[0],400)
        body['confirm_replace']=True;status,_,state=self.post('/api/uploads/activate',body);self.assertEqual(status,200)
        review=self.get('/api/review?mode=upload&revision='+state['revision'])[2]
        self.assertAlmostEqual(review['customers'][0]['predictions'][0]['predicted'],30.79099107142857)
        value={'mode':'upload','batch_revision':state['revision'],'customer_ids':['C103794']}
        status,h,raw=self.post('/api/export.csv',value);self.assertEqual(status,200);self.assertIn(state['revision'],raw.decode('utf-8-sig'));self.assertIn('30.79099107142857',raw.decode('utf-8-sig'));self.assertEqual(h['X-Q1-Data-Version'],state['revision'])
        status,h,raw=self.post('/api/customer-summary.pdf',value);self.assertEqual(status,200);self.assertEqual(h['Content-Type'],'application/pdf');self.assertTrue(raw.startswith(b'%PDF-'));self.assertEqual(h['X-Q1-Data-Version'],state['revision'])
        self.assertEqual(self.post('/api/uploads/activate',body)[2]['revision'],state['revision'])
    def test_stale_confirmation_and_exports_cannot_use_replaced_data(self):
        first=self.activate();_,_,pending=self.stage();second=self.activate(self.b)
        self.assertEqual(self.post('/api/uploads/activate',{'stage_id':pending['stage_id'],'expected_revision':first['revision'],'confirm_replace':True})[0],409)
        for path in ['/api/export.csv','/api/customer-summary.pdf']:
            self.assertEqual(self.post(path,{'mode':'upload','batch_revision':first['revision'],'customer_ids':['C103794']})[0],409)
        self.assertEqual(self.get('/api/review?mode=upload&revision='+first['revision'])[0],409)
        self.assertEqual(self.get('/api/state')[2]['revision'],second['revision'])
        self.assertEqual(len(self.get('/api/review')[2]['customers']),37)
    def test_cancellation_and_bad_schema_keep_last_good(self):
        state=self.activate();_,_,r=self.stage(self.b)
        for _ in range(2):self.assertEqual(self.post('/api/uploads/cancel',{'request_id':r['stage_id']})[0],200)
        self.assertEqual(self.post('/api/uploads/activate',{'stage_id':r['stage_id'],'expected_revision':state['revision'],'confirm_replace':True})[0],409)
        bad=mutate(self.a,'customers.csv',lambda h,r:h.reverse());status,_,error=self.stage(bad)
        self.assertEqual(status,400);self.assertIn('customers.csv',error['error']);self.assertEqual(self.get('/api/state')[2]['revision'],state['revision'])
    def test_host_origin_token_runtime_and_oversize_guards(self):
        value={'request_id':op()}
        self.assertEqual(self.post('/api/uploads/cancel',value,**{'X-Q1-Request-Token':''})[0],403)
        self.assertEqual(self.post('/api/uploads/cancel',value,Origin='http://outside.invalid')[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'outside.invalid'})[0],403)
        for path in ['/runtime/uploads/state.json','/assets/%2e%2e/runtime/uploads/state.json','/serve.py']:
            self.assertEqual(self.get(path)[0],404)
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        c.putrequest('POST','/api/uploads/stage');c.putheader('Origin',self.base);c.putheader('X-Q1-Request-Token',self.token);c.putheader('Content-Type','multipart/form-data; boundary=x');c.putheader('Content-Length',str(MAX_BODY+1));c.endheaders();self.assertEqual(c.getresponse().status,413);c.close()
    def test_interrupted_transport_does_not_stage_or_activate(self):
        state=self.activate();c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        c.putrequest('POST','/api/uploads/stage');c.putheader('Origin',self.base);c.putheader('X-Q1-Request-Token',self.token);c.putheader('Content-Type','multipart/form-data; boundary=x');c.putheader('Content-Length','100000');c.endheaders();c.send(b'--x\r\npartial');c.sock.shutdown(socket.SHUT_WR)
        self.assertEqual(c.getresponse().status,400);c.close();self.assertEqual(self.get('/api/state')[2]['revision'],state['revision'])
    def test_restart_recovers_last_good_and_invalidates_old_session_token(self):
        first=self.activate();second=self.activate(self.b);old_token=self.token;self.stop()
        (Path(self.tmp.name)/'batches'/second['active_batch']/'review.json').write_text('broken')
        self.start();self.assertEqual(self.state['active_batch'],first['active_batch']);self.assertTrue(self.state['recovery'])
        self.assertEqual(self.post('/api/uploads/cancel',{'request_id':op()},**{'X-Q1-Request-Token':old_token})[0],403)
    def test_full_unchanged_source_batch_validates_without_source_writes(self):
        manifest=json.loads((DEFAULT_SOURCE/'SCHEMAS-AND-COVERAGE.json').read_text());parts=[(Path(s['file']).name,(DEFAULT_SOURCE/s['file']).read_bytes()) for s in manifest['files']]
        status,_,r=self.stage(parts);self.assertEqual(status,200,r);self.assertEqual(r['summary']['total_rows'],437278);self.assertEqual(r['summary']['review_customers'],37)
    def test_replacement_during_export_rendering_invalidates_response(self):
        from types import SimpleNamespace
        first=self.activate();_,_,pending=self.stage(self.b)
        def render(*args,**kwargs):
            self.server.uploads.activate(pending['stage_id'],first['revision'])
            return SimpleNamespace(stdout=b'%PDF-1.4 test-only')
        with patch('serve.subprocess.run',render):
            status,_,error=self.post('/api/customer-summary.pdf',{'mode':'upload','batch_revision':first['revision'],'customer_ids':['C103794']})
        self.assertEqual(status,409);self.assertIn('changed',error['error'])

if __name__=='__main__':unittest.main()
