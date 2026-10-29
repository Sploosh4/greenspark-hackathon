"""Mock transport, actual handler: staging, origin and explicit promotion; no port."""
import importlib.util,json,sys,threading,unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from test_business_upload import file_bytes,CUSTOMER_HEADERS,USAGE_HEADERS,customer,usage
import test_source_adapter as fixtures
from business_upload import UploadStages,UploadJobs
from test_upload_jobs import DeferredExecutor
spec=importlib.util.spec_from_file_location('q3_run',fixtures.ROOT/'run.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class UploadHTTP(unittest.TestCase):
 def setUp(self):
  fixtures.Sources.setUp(self);self.store.read();self.origin='http://127.0.0.1:8797'
  from types import SimpleNamespace
  self.server=SimpleNamespace(server_port=8797,snapshots=self.store,uploads=UploadStages(self.store,self.store.good['data']['business'],lambda:fixtures.NOW),upload_slot=threading.BoundedSemaphore(1))
  self.executor=DeferredExecutor();self.server.upload_jobs=UploadJobs(self.server.uploads,self.executor)
 def tearDown(self):fixtures.Sources.tearDown(self)
 def request(self,path,body,kind='application/json',origin=True):
  from types import SimpleNamespace
  import io
  body=body.encode() if isinstance(body,str) else body
  handler=app.Q3Handler.__new__(app.Q3Handler);handler.server=self.server;handler.path=path;handler.headers={'Host':'127.0.0.1:8797','Content-Type':kind,'Content-Length':str(len(body))};handler.rfile=io.BytesIO(body);handler.connection=SimpleNamespace(settimeout=lambda t:None)
  if origin:handler.headers['Origin']=self.origin
  captured=[];handler.json_reply=lambda value,status=200:captured.append((status,value));handler.do_POST();return captured[0]
 def multipart(self):
  chunks=[];boundary='q3-unit-test-boundary'
  for name,filename,raw in [('customers','customers.csv',file_bytes(CUSTOMER_HEADERS,[customer('NEW1')])),('usage','consumption_daily.csv',file_bytes(USAGE_HEADERS,[usage('NEW1')])),('synthetic',None,b'true')]:
   chunks.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"'+('; filename="'+filename+'"' if filename else '')+'\r\n\r\n').encode()+raw+b'\r\n')
  return b''.join(chunks)+('--'+boundary+'--\r\n').encode(),'multipart/form-data; boundary='+boundary
 def test_stage_then_explicit_replace(self):
  raw,kind=self.multipart();status,receipt=self.request('/api/q3/business/stage',raw,kind);self.assertEqual(status,202);self.assertEqual(receipt['state'],'accepted');self.executor.run();stage=self.server.upload_jobs.status(receipt['jobId'])['result'];self.assertEqual(self.store.read()['data']['business']['totalAccounts'],393);self.assertEqual(stage['proposed']['totalAccounts'],1)
  status,p=self.request('/api/q3/business/replace',json.dumps({'stageId':stage['stageId'],'baseGeneration':stage['baseGeneration']}));self.assertEqual(status,200);self.assertEqual(p['data']['business']['totalAccounts'],1)
 def test_missing_origin_rejected_before_read_or_mutation(self):
  status,p=self.request('/api/q3/business/stage',b'bad',origin=False);self.assertEqual(status,403);self.assertEqual(self.store.read()['data']['business']['totalAccounts'],393)
 def test_bad_payload_and_unknown_route_keep_good_data(self):
  self.assertEqual(self.request('/api/q3/business/stage',b'{}')[0],422);self.assertEqual(self.request('/api/q3/business/other',b'{}')[0],404);self.assertEqual(self.store.read()['data']['business']['totalAccounts'],393)

 def test_actual_status_handler_returns_pending_then_ready_or_failed(self):
  from types import SimpleNamespace
  raw,kind=self.multipart();_,r=self.request('/api/q3/business/stage',raw,kind)
  def get(token):
   h=app.Q3Handler.__new__(app.Q3Handler);h.server=self.server;h.path='/api/q3/business/stage-status?id='+token;h.headers={'Host':'127.0.0.1:8797'};captured=[];h.json_reply=lambda value,status=200:captured.append((status,value));h.do_GET();return captured[0]
  self.assertEqual(get(r['jobId'])[1]['state'],'accepted');self.executor.run();self.assertEqual(get(r['jobId'])[1]['state'],'ready');self.assertEqual(get('a'*32)[0],404);self.assertEqual(get('bad')[0],422)
