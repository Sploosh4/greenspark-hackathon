"""Actual Q3 handler boundary with ephemeral accounts and mocked transport."""
import io,json,secrets,sys,unittest
from dataclasses import replace
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
import test_upload_http as http_fixture
from local_auth import Account,AuthService,hash_password
from source_adapter import canonical

class NoBody(io.BytesIO):
 def read(self,*args):raise AssertionError('Unauthorised request consumed the upload body')

class ActualQ3Auth(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.password=secrets.token_urlsafe(24);cls.record=hash_password(cls.password)
 def setUp(self):
  self.accounts={'manager':Account('test-only-q3','manager','manager',self.record)};self.clock=[1000.0];self.auth=AuthService('q3',self.accounts.get,clock=lambda:self.clock[0]);self.server=SimpleNamespace(auth=self.auth,server_port=8797)
 def call(self,method,path,body=b'',headers=None,deny_read=False):
  h=http_fixture.app.Q3Handler.__new__(http_fixture.app.Q3Handler);h.server=self.server;h.path=path;h.command=method;h.headers=Message()
  values={'Host':'127.0.0.1:8797','Content-Type':'application/json','Content-Length':str(len(body)),**(headers or {})}
  for k,v in values.items():h.headers[k]=v
  h.rfile=NoBody() if deny_read else io.BytesIO(body);h.connection=SimpleNamespace(settimeout=lambda t:None);captured=[]
  h.json_reply=lambda value,status=200:captured.append({'status':status,'body':value,'headers':()})
  h.reply=lambda value,kind,status=200,cache=False,extra_headers=(),csp=None:captured.append({'status':status,'body':json.loads(value) if kind=='application/json' else value,'headers':extra_headers,'csp':csp})
  getattr(h,'do_'+method)();return captured[0],h
 def login(self):
  challenge,_=self.call('GET','/api/auth/challenge');cookie=challenge['headers'][0][1].split(';')[0]
  reply,_=self.call('POST','/api/auth/login',canonical({'username':'manager','password':self.password}),{'Origin':'http://127.0.0.1:8797','Cookie':cookie,'X-Team-Connect-CSRF':challenge['body']['csrf_token']})
  self.assertEqual(reply['status'],200);self.assertEqual(len(reply['headers']),2)
  return {'Cookie':reply['headers'][0][1].split(';')[0],'Origin':'http://127.0.0.1:8797','X-Team-Connect-CSRF':reply['body']['csrf_token']}
 def test_private_gets_including_inherited_map_static_data_deny_without_session(self):
  for path in ['/','/business.html','/styles.css','/vendor/maplibre-gl.js','/maptiler/maps/streets-v4/style.json','/api/q3/snapshot','/api/q3/business/stage-status?id='+('a'*32),'/api/q3/history/metadata','/history/average-11.png','/unknown']:
   with self.subTest(path=path):self.assertEqual(self.call('GET',path,headers={'X-Role':'manager'})[0]['status'],401)
 def test_unauthorised_upload_does_not_read_large_body(self):
  reply,_=self.call('POST','/api/q3/business/stage',headers={'Content-Length':'16000000','Origin':'http://127.0.0.1:8797','X-Role':'manager'},deny_read=True);self.assertEqual(reply['status'],401)
 def test_manager_session_can_read_actual_snapshot_handler(self):
  headers=self.login();self.server.snapshots=SimpleNamespace(read=lambda:{'only':'ephemeral fixture'});r,h=self.call('GET','/api/q3/snapshot',headers=headers);self.assertEqual(r['body'],{'only':'ephemeral fixture'});self.assertEqual(h.principal.role,'manager')
 def test_csrf_and_exact_origin_checked_before_upload_read(self):
  headers=self.login()
  for changed in [{'X-Team-Connect-CSRF':'forged'},{'Origin':'http://localhost:8797'},{'Origin':'https://evil.example'}]:
   with self.subTest(changed=changed):r,_=self.call('POST','/api/q3/business/stage',headers={**headers,**changed},deny_read=True);self.assertEqual(r['status'],403)
 def test_q1_cookie_and_forged_roles_never_access_q3(self):
  headers=self.login();headers['Cookie']=headers['Cookie'].replace('tc_q3_session=','tc_q1_session=');headers['X-Role']='manager';self.assertEqual(self.call('GET','/api/q3/snapshot',headers=headers)[0]['status'],401)
 def test_expiry_disabled_account_role_or_version_revokes_session(self):
  for mutation in ['expiry','disabled','role','version']:
   with self.subTest(mutation=mutation):
    self.accounts['manager']=Account('test-only-q3','manager','manager',self.record);headers=self.login()
    if mutation=='expiry':self.clock[0]+=1801
    elif mutation=='disabled':self.accounts['manager']=replace(self.accounts['manager'],enabled=False)
    elif mutation=='role':self.accounts['manager']=replace(self.accounts['manager'],role='officer')
    else:self.accounts['manager']=replace(self.accounts['manager'],credential_version=2)
    self.assertEqual(self.call('GET','/api/q3/snapshot',headers=headers)[0]['status'],401)
 def test_officer_cannot_log_into_q3(self):
  self.accounts['manager']=replace(self.accounts['manager'],role='officer');challenge,_=self.call('GET','/api/auth/challenge');headers={'Origin':'http://127.0.0.1:8797','Cookie':challenge['headers'][0][1].split(';')[0],'X-Team-Connect-CSRF':challenge['body']['csrf_token']};r,_=self.call('POST','/api/auth/login',canonical({'username':'manager','password':self.password}),headers);self.assertEqual(r['status'],401)
 def test_logout_revokes_and_expiry_headers_are_forwarded(self):
  headers=self.login();r,_=self.call('POST','/api/auth/logout',b'{}',headers);self.assertEqual(r['status'],200);self.assertIn('Max-Age=0',r['headers'][0][1]);self.assertEqual(self.call('GET','/api/q3/snapshot',headers=headers)[0]['status'],401)
 def test_auth_body_framing_bounded_before_read(self):
  for extra in [{'Content-Length':'4097'},{'Transfer-Encoding':'chunked'},{'Content-Length':'-1'}]:
   with self.subTest(extra=extra):r,_=self.call('POST','/api/auth/login',headers=extra,deny_read=True);self.assertEqual(r['status'],400)
 def test_health_and_exact_login_page_are_public_data_free(self):
  r,_=self.call('GET','/healthz');self.assertEqual(r['body'],{'alive':True,'instance':'q3','authenticationConfigured':True});r,_=self.call('GET','/auth/login');self.assertEqual(r['status'],200);self.assertIn("script-src 'sha256-",r['csp']);self.assertNotIn(self.password.encode(),r['body'])
 def test_preview_session_does_not_claim_enforcement(self):
  self.server.auth=None;r,_=self.call('GET','/api/session');self.assertFalse(r['body']['authenticated']);self.assertFalse(r['body']['enforcementConfigured']);self.assertEqual(r['body']['mode'],'local-preview');self.assertEqual(self.call('GET','/api/auth/challenge')[0]['status'],503)
 def test_unsupported_methods_are_guarded_before_dispatch(self):
  for method in ['HEAD','PUT','PATCH','DELETE','OPTIONS']:
   with self.subTest(method=method):self.assertEqual(self.call(method,'/api/q3/snapshot')[0]['status'],400 if method=='OPTIONS' else 401)

 def test_authenticated_manager_can_stage_and_explicitly_replace_through_actual_handler(self):
  from business_upload import UploadStages,UploadJobs
  from test_upload_jobs import DeferredExecutor
  import test_source_adapter as source_fixture
  import threading
  source_fixture.Sources.setUp(self)
  try:
   before=self.store.read();self.server.snapshots=self.store;self.server.uploads=UploadStages(self.store,before['data']['business'],lambda:source_fixture.NOW);self.server.upload_slot=threading.BoundedSemaphore(1);executor=DeferredExecutor();self.server.upload_jobs=UploadJobs(self.server.uploads,executor)
   headers=self.login();body,kind=http_fixture.UploadHTTP.multipart(self);r,_=self.call('POST','/api/q3/business/stage',body,{**headers,'Content-Type':kind});self.assertEqual(r['status'],202);self.assertEqual(self.store.read()['generation'],before['generation']);receipt=r['body'];pending,_=self.call('GET','/api/q3/business/stage-status?id='+receipt['jobId'],headers=headers);self.assertEqual(pending['body']['state'],'accepted');executor.run();ready,_=self.call('GET','/api/q3/business/stage-status?id='+receipt['jobId'],headers=headers);stage=ready['body']['result']
   r,_=self.call('POST','/api/q3/business/replace',canonical({'stageId':stage['stageId'],'baseGeneration':stage['baseGeneration']}),headers);self.assertEqual(r['status'],200);self.assertEqual(r['body']['data']['business']['totalAccounts'],1)
  finally:source_fixture.Sources.tearDown(self)
 def test_authorized_inherited_static_route_uses_same_guard(self):
  self.server.missing_data=False;self.server.missing_map=False;r,_=self.call('GET','/styles.css',headers=self.login());self.assertEqual(r['status'],200);self.assertGreater(len(r['body']),100)
