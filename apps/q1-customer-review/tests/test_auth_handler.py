"""Actual Q1 handlers with ephemeral accounts; never opens a socket or saves credentials."""
from email.message import Message
from io import BytesIO
import json,secrets,threading,time,uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from prototype.vendor.auth.local_auth import Account,AuthService,hash_password
from prototype.uploads import UploadStore
from prototype.public_weather import PublicWeatherStore
from prototype.weather_job import DailyCacheJob
from prototype.jobs import UploadJobs
from serve import Handler
from tests.test_upload_http import multipart
from tests.make_upload_fixtures import fixture_parts

class AuthHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password=secrets.token_urlsafe(24);record=hash_password(cls.password)
        cls.accounts={role:Account('fixture-'+role,role,role,record) for role in ('officer','manager')};cls.parts=fixture_parts()
    def setUp(self):
        self.tmp=TemporaryDirectory();root=Path(self.tmp.name);self.accounts=dict(self.__class__.accounts);self.auth=AuthService('q1',self.accounts.get)
        weather=PublicWeatherStore(root/'weather',root/'absent')
        self.server=SimpleNamespace(server_port=8891,request_token='test-request',auth=self.auth,review={'customers':[]},demo_revision='demo-A',uploads=UploadStore(root/'uploads'),public_weather=weather,weather_job=DailyCacheJob(weather),settings={'opening_mode':'demo','weather_time':'06:00'},settings_path=root/'settings.json',clock=lambda:__import__('datetime').datetime.now(__import__('datetime').timezone.utc))
        self.server.upload_jobs=UploadJobs(self.server.uploads);self.server.upload_slots=threading.BoundedSemaphore(2)
    def tearDown(self):self.server.upload_jobs.close();self.tmp.cleanup()
    def request(self,path,method='GET',value=None,headers=None,raw=None,body_guard=False):
        h=Handler.__new__(Handler);h.command=method;h.server=self.server;h.path=path;h.headers=Message()
        body=raw if raw is not None else json.dumps(value).encode() if value is not None else b''
        fields={'Host':'127.0.0.1:8891','Origin':'http://127.0.0.1:8891','Content-Type':'application/json','Content-Length':str(len(body)),'X-Q1-Request-Token':'test-request',**(headers or {})}
        for key,item in fields.items():h.headers[key]=item
        h.rfile=BytesIO(body);h.wfile=BytesIO();h.connection=SimpleNamespace(settimeout=lambda value:None)
        result={'headers':[]};h.send_response=lambda status:result.update(status=status);h.send_header=lambda key,item:result['headers'].append((key,item));h.end_headers=lambda:None
        if body_guard:h.read_body=lambda *args:(_ for _ in ()).throw(AssertionError('body read before authorization'))
        getattr(h,'do_'+method)();result['raw']=h.wfile.getvalue()
        if any(k=='Content-Type' and v.startswith('application/json') for k,v in result['headers']) and result['raw']:result['body']=json.loads(result['raw'])
        return result
    def login(self,role):
        challenge=self.request('/api/auth/challenge');cookie=next(v.split(';',1)[0] for k,v in challenge['headers'] if k=='Set-Cookie')
        result=self.request('/api/auth/login','POST',{'username':role,'password':self.password},{'Cookie':cookie,'X-Team-Connect-CSRF':challenge['body']['csrf_token']})
        self.assertEqual(result['status'],200,result);self.assertEqual(sum(k=='Set-Cookie' for k,v in result['headers']),2)
        session=next(v.split(';',1)[0] for k,v in result['headers'] if k=='Set-Cookie' and v.startswith('tc_q1_session='))
        return {'Cookie':session,'X-Team-Connect-CSRF':result['body']['csrf_token']}
    def test_private_get_head_and_upload_authorize_before_large_body(self):
        for path in ['/api/review','/api/state','/api/live-weather','/assets/review-fixture.json','/app.mjs','/unknown']:
            self.assertEqual(self.request(path)['status'],401)
        result=self.request('/api/review','HEAD');self.assertEqual(result['status'],401);self.assertEqual(result['raw'],b'')
        self.assertEqual(self.request('/api/uploads/stage','POST',raw=b'large',body_guard=True)['status'],401)
        self.assertEqual(self.request('/')['status'],303)
    def test_both_roles_can_stage_and_cancel_using_actual_upload_handlers(self):
        for role in ['officer','manager']:
            headers=self.login(role);operation=uuid.uuid4().hex;raw,content_type=multipart(self.parts,operation,'none')
            result=self.request('/api/uploads/stage','POST',headers={**headers,'Content-Type':content_type},raw=raw)
            self.assertEqual(result['status'],202,result)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                status=self.request('/api/uploads/status?request_id='+operation,headers=headers)
                if status['body']['state'] not in ('queued','running'):break
                time.sleep(.01)
            self.assertEqual(status['body']['state'],'ready',status);self.assertEqual(status['body']['receipt']['stage_id'],operation)
            self.assertEqual(self.request('/api/uploads/cancel','POST',{'request_id':operation},headers)['status'],200)
    def test_officer_cannot_read_or_write_settings_or_forge_manager_role(self):
        headers={**self.login('officer'),'X-Role':'manager'}
        self.assertEqual(self.request('/api/settings?role=manager',headers=headers)['status'],403)
        self.assertEqual(self.request('/api/settings','POST',{'opening_mode':'upload','weather_time':'07:00'},headers,body_guard=True)['status'],403)
        self.assertFalse(self.server.settings_path.exists())
    def test_manager_settings_read_write_and_session_bound_csrf(self):
        headers=self.login('manager');self.assertEqual(self.request('/api/settings',headers=headers)['status'],200)
        value={'opening_mode':'upload','weather_time':'07:30'}
        self.assertEqual(self.request('/api/settings','POST',value,{**headers,'X-Team-Connect-CSRF':'forged'})['status'],403)
        self.assertEqual(self.request('/api/settings','POST',value,headers)['status'],200)
        self.assertEqual({k:v for k,v in json.loads(self.server.settings_path.read_text()).items() if k!='weather_schedule'},value);self.assertEqual(self.server.weather_job.local_time,'07:30')
    def test_session_logout_disabling_and_cross_instance_cookie_reject(self):
        headers=self.login('manager');self.assertEqual(self.request('/api/session',headers=headers)['body']['role'],'manager')
        self.assertEqual(self.request('/api/review',headers={'Cookie':headers['Cookie'].replace('tc_q1_session','tc_q3_session')})['status'],401)
        self.assertEqual(self.request('/api/auth/logout','POST',{},headers)['status'],200)
        self.assertEqual(self.request('/api/review',headers=headers)['status'],401)
        headers=self.login('manager');self.accounts.pop('manager');self.assertEqual(self.request('/api/review',headers=headers)['status'],401)
    def test_auth_bodies_are_bounded_and_preview_stays_usable_without_bootstrap(self):
        self.assertEqual(self.request('/api/auth/login','POST',raw=b'x'*4097)['status'],413)
        self.server.auth=None
        self.assertEqual(self.request('/api/review')['status'],200);self.assertFalse(self.request('/api/session')['body']['login_enabled'])
        self.assertEqual(self.request('/api/auth/challenge')['status'],503);self.assertEqual(self.request('/api/settings')['status'],403)
