"""Loopback-only synthetic Q1 app: controlled local replacement and recovery."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
from email.parser import BytesParser
from email import policy
import argparse
import copy
import hmac
import json
import secrets
import socket
import subprocess
from tempfile import SpooledTemporaryFile
import threading
from datetime import datetime,timezone
from prototype.review import build_review
from prototype.inputs import InputError
from prototype.uploads import UploadStore,UploadError,MAX_BODY,write_json
from prototype.exports import csv_bytes,iter_csv_chunks,selected_rows,MAX_CSV_CUSTOMERS,MAX_CSV_BYTES
from prototype.public_weather import PublicWeatherStore
from prototype.public_source import PublicSourceStore
from prototype.weather_job import DailyCacheJob,next_daily
from prototype.public_weather import utc
from prototype.live import business_coverage
from prototype.vendor.auth.local_auth import AUTH_PATHS,AuthError
from prototype.jobs import UploadJobs

ROOT=Path(__file__).resolve().parent
PDF_PYTHON=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python'

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'")
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()
    def list_directory(self,path):self.send_error(404)
    def json(self,status,value,headers=()):
        raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
        for name,value in headers:self.send_header(name,value)
        self.end_headers()
        if getattr(self,'command',None)!='HEAD':self.wfile.write(raw)
    def auth_dispatch(self,method):
        path=urlsplit(self.path).path;auth=getattr(self.server,'auth',None)
        if path not in AUTH_PATHS:return False
        if auth is None:
            if path=='/api/session' and method=='GET':self.json(200,{'authenticated':False,'login_enabled':False,'mode':'local_synthetic_preview'})
            else:self.json(503,{'error':'Local sign-in is not enabled; approved account bootstrap is required.'})
            return True
        body=self.read_body(4096) if method=='POST' else b''
        reply=auth.auth_route(method,self.path,self.headers,body)
        self.json(reply.status,reply.body,reply.headers);return True
    def auth_guard(self,method):
        path=urlsplit(self.path).path
        capability='settings' if path=='/api/settings' else 'upload' if path.startswith('/api/uploads/') else 'export' if path in ('/api/export.csv','/api/customer-summary.pdf') else 'review'
        auth=getattr(self.server,'auth',None)
        if auth is not None:self.principal=auth.authorize(method,self.path,self.headers,capability)
        elif capability=='settings':raise UploadError('Settings require an approved authenticated manager account',403)
    def check_host(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed:raise UploadError('Local host required',403)
        return allowed
    def read_body(self,limit):
        if self.headers.get('Transfer-Encoding'):raise UploadError('Chunked upload is not supported')
        if hasattr(self.headers,'get_all') and len(self.headers.get_all('Content-Length') or [])!=1:raise UploadError('Exactly one body length is required')
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:raise UploadError('Invalid body length')
        if not 0<length<=limit:raise UploadError('Request exceeds its size limit or has no body',413)
        self.connection.settimeout(15);chunks=[];remaining=length
        try:
            while remaining:
                chunk=self.rfile.read(min(65536,remaining))
                if not chunk:raise UploadError('Upload interrupted before all bytes arrived')
                chunks.append(chunk);remaining-=len(chunk)
        except (socket.timeout,ConnectionError) as e:raise UploadError('Upload interrupted; current data was kept') from e
        return b''.join(chunks)
    def multipart(self):
        ct=self.headers.get('Content-Type','')
        if not ct.startswith('multipart/form-data;') or '\r' in ct or '\n' in ct:raise UploadError('Choose the twelve files using the upload form')
        msg=BytesParser(policy=policy.default).parsebytes(b'Content-Type: '+ct.encode('ascii')+b'\r\nMIME-Version: 1.0\r\n\r\n'+self.read_body(MAX_BODY))
        if msg.defects or not msg.is_multipart():raise UploadError('Incomplete or malformed multipart upload')
        parts=[];fields={};items=list(msg.iter_parts())
        if len(items)!=14:raise UploadError('The upload needs twelve files and its two version fields')
        for part in items:
            if part.defects or part.is_multipart() or part.get('Content-Transfer-Encoding'):raise UploadError('Unsupported multipart encoding')
            if part.get_content_disposition()!='form-data':raise UploadError('Invalid upload part')
            name=part.get_param('name',header='content-disposition');filename=part.get_filename();raw=part.get_payload(decode=True)
            if filename is not None:
                if name!='files':raise UploadError('Unexpected file field')
                parts.append((filename,raw))
            else:
                if name not in ('request_id','expected_revision') or name in fields or len(raw)>100:raise UploadError('Invalid upload version fields')
                fields[name]=raw.decode('ascii')
        if set(fields)!= {'request_id','expected_revision'}:raise UploadError('Missing upload version fields')
        return parts,fields
    def review(self,mode,revision=None):
        if mode=='upload':return self.server.uploads.view(revision)
        if mode!='demo':raise UploadError('Unknown data mode')
        if self.server.review is None:raise UploadError('Preloaded inputs could not be validated',503)
        r=copy.deepcopy(self.server.review);r.update(data_mode='demo',batch_id='preloaded',batch_revision=self.server.demo_revision)
        if revision is not None and revision!=r['batch_revision']:raise UploadError('The preloaded review changed. Reload before exporting.',409)
        return r
    def static_allowed(self):
        path=unquote(urlsplit(self.path).path)
        if '\\' in path or '\x00' in path or '..' in path.split('/'):return False
        name=path.lstrip('/') or 'index.html'
        if name not in ('index.html','app.mjs','core.mjs') and name.split('/')[0] not in ('assets','docs','tests','screenshots','output'):return False
        target=(ROOT/name).resolve()
        return target.is_relative_to(ROOT) and not (ROOT/name).is_symlink()
    def assert_revision(self,mode,revision):
        if mode=='upload':return self.server.uploads.assert_revision(revision)
        if mode!='demo':raise UploadError('Unknown data mode')
        if self.server.review is None:raise UploadError('Preloaded inputs could not be validated',503)
        if revision!=self.server.demo_revision:raise UploadError('The preloaded review changed. Reload before exporting.',409)
    def do_HEAD(self):
        try:self.check_host();self.auth_guard('HEAD')
        except UploadError as e:self.send_error(e.status,str(e));return
        except AuthError as e:self.json(e.status,{'error':e.message});return
        if not self.static_allowed():self.send_error(404);return
        super().do_HEAD()
    def do_GET(self):
        try:
            self.check_host();url=urlsplit(self.path);query=parse_qs(url.query)
            if self.auth_dispatch('GET'):return
            if url.path=='/healthz':self.json(200,{'status':'ready'});return
            if url.path=='/auth/login':
                raw=(ROOT/'assets/auth-login.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            if url.path=='/assets/auth-login.mjs':
                super().do_GET();return
            self.auth_guard('GET')
            if url.path=='/api/settings':self.json(200,{**self.server.settings,'instance':'q1','timezone':'Australia/Perth','schedule':self.server.weather_job.status()});return
            if url.path=='/api/state':self.json(200,{**self.server.uploads.status(),'request_token':self.server.request_token,'demo_revision':self.server.demo_revision,'opening_mode':self.server.settings['opening_mode']});return
            if url.path=='/api/uploads/status':self.json(200,self.server.upload_jobs.status(query.get('request_id',[None])[0]));return
            if url.path=='/api/review':self.json(200,self.review(query.get('mode',['demo'])[0],query.get('revision',[None])[0]));return
            if url.path=='/api/live-weather':
                mode=query.get('mode',['demo'])[0];review=self.review(mode);now=self.server.clock();weather=self.server.public_weather.view(now)
                key=(mode,review['batch_revision'],weather['review_date'])
                with self.server.live_coverage_lock:
                    coverage=self.server.live_coverage.get(key)
                    if coverage is None:
                        coverage=business_coverage(review['input_validation']['source_root'],now)
                        self.server.live_coverage={key:coverage}
                self.json(200,{**weather,'business':coverage,'business_mode':mode,'business_revision':review['batch_revision'],'schedule':self.server.weather_job.status()});return
            if not self.static_allowed():raise UploadError('Not found',404)
            super().do_GET()
        except UploadError as e:self.json(e.status,{'error':str(e)})
        except AuthError as e:
            if e.status==401 and urlsplit(self.path).path in ('/','/index.html'):
                self.send_response(303);self.send_header('Location','/auth/login');self.send_header('Content-Length','0');self.end_headers()
            else:self.json(e.status,{'error':e.message})
        except (InputError,ValueError,OSError):self.json(503,{'error':'The source inputs could not be validated. The historical demonstration is retained.'})
        except (BrokenPipeError,ConnectionError):pass
    def do_POST(self):
        try:
            hosts=self.check_host()
            if self.auth_dispatch('POST'):return
            self.auth_guard('POST') # Authorize before any large upload body is consumed.
            if self.headers.get('Origin') not in {'http://'+h for h in hosts}:raise UploadError('Same-origin local request required',403)
            if not hmac.compare_digest(self.headers.get('X-Q1-Request-Token',''),self.server.request_token):raise UploadError('The local session restarted. Reload the page and retry.',403)
            if self.path=='/api/uploads/stage':
                if not self.server.upload_slots.acquire(blocking=False):raise UploadError('Another upload body is being received. Wait before retrying.',429)
                try:parts,fields=self.multipart();job=self.server.upload_jobs.submit(parts,fields['request_id'],fields['expected_revision'])
                finally:self.server.upload_slots.release()
                self.json(202,job);return
            if self.headers.get('Content-Type')!='application/json':raise UploadError('Expected JSON')
            request=json.loads(self.read_body(8*1024*1024 if self.path=='/api/export.csv' else 65536))
            if not isinstance(request,dict):raise UploadError('Expected an object')
            if self.path=='/api/uploads/cancel':self.json(200,self.server.upload_jobs.cancel(request.get('request_id')));return
            if self.path=='/api/uploads/activate':
                if request.get('confirm_replace') is not True:raise UploadError('Explicit replacement confirmation is required')
                self.json(200,self.server.uploads.activate(request.get('stage_id'),request.get('expected_revision')));return
            if self.path=='/api/uploads/rollback':
                if request.get('confirm_restore') is not True:raise UploadError('Explicit recovery confirmation is required')
                self.json(200,self.server.uploads.rollback(request.get('request_id'),request.get('expected_revision')));return
            if self.path=='/api/settings':
                if set(request)!={'opening_mode','weather_time'} or request['opening_mode'] not in ('demo','upload'):raise UploadError('Invalid instance settings')
                now=self.server.clock();next_daily(now,request['weather_time'])
                def commit_schedule(schedule):
                    value={**request,'weather_schedule':schedule}
                    try:write_json(self.server.settings_path,value)
                    except OSError:
                        # Atomic replacement can complete before directory sync
                        # fails. Reconcile that known committed record instead of
                        # reporting an unchanged schedule or applying it twice.
                        try:
                            if self.server.settings_path.stat().st_size>65536:raise ValueError('Settings size outside bound')
                            committed=json.loads(self.server.settings_path.read_text())
                        except (OSError,ValueError):raise
                        if committed!=value:raise
                        return {'sync_warning':True}
                    return None
                with self.server.weather_job.lock:
                    self.server.weather_job.configure(request['weather_time'],now,commit=commit_schedule)
                    self.server.settings=dict(request)
                self.json(200,{**request,'timezone':'Australia/Perth','schedule':self.server.weather_job.status()});return
            if self.path not in ('/api/customer-summary.pdf','/api/export.csv'):raise UploadError('Not found',404)
            mode=request.get('mode','demo');revision=request.get('batch_revision')
            if not isinstance(revision,str):raise UploadError('An export must identify its data version',409)
            review=self.review(mode,revision);ids=request.get('customer_ids');rows=selected_rows(review,ids,limit=100 if self.path.endswith('.pdf') else MAX_CSV_CUSTOMERS)
            if self.path.endswith('.pdf'):
                # The renderer needs selected accounts and shared context, not
                # every unselected customer's history across the process pipe.
                pdf_review={**review,'customers':rows}
                format=request.get('format','detailed')
                if format not in ('detailed','condensed'):raise UploadError('Unknown PDF format')
                raw=subprocess.run([str(PDF_PYTHON),str(ROOT/'pdf_export.py')],input=json.dumps({'review':pdf_review,'customer_ids':ids,'format':format},allow_nan=False).encode(),capture_output=True,timeout=30,check=True).stdout
                if not raw.startswith(b'%PDF-'):raise UploadError('Invalid PDF output',503)
                mime='application/pdf';filename='q1-customer-summary.pdf'
            else:
                # Bound memory and complete/version-check before sending any
                # bytes, so a stale or oversized CSV is never a partial file.
                with SpooledTemporaryFile(max_size=2*1024*1024) as spool:
                    size=0
                    for chunk in iter_csv_chunks(review,ids):
                        size+=len(chunk)
                        if size>MAX_CSV_BYTES:raise UploadError('CSV exceeds its64MiBoutput limit',413)
                        spool.write(chunk)
                    self.assert_revision(mode,revision);spool.seek(0)
                    self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8');self.send_header('Content-Disposition','attachment; filename="q1-filtered-review.csv"');self.send_header('Content-Length',str(size));self.send_header('X-Q1-Data-Version',revision);self.end_headers()
                    while chunk:=spool.read(65536):self.wfile.write(chunk)
                return
            self.assert_revision(mode,revision) # Replacement during rendering invalidates this export.
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Disposition',f'attachment; filename="{filename}"');self.send_header('Content-Length',str(len(raw)));self.send_header('X-Q1-Data-Version',revision);self.end_headers();self.wfile.write(raw)
        except UploadError as e:self.json(e.status,{'error':str(e)})
        except AuthError as e:self.json(e.status,{'error':e.message})
        except (InputError,ValueError,KeyError,UnicodeError) as e:self.json(400,{'error':str(e)})
        except (BrokenPipeError,ConnectionError):pass
        except Exception:self.json(503,{'error':'The local operation could not finish. Existing batches were preserved; reload upload status before retrying.'})

def make_server(port=8891,store_root=None,review=None,weather_time='06:00',auth=None,weather_source='cache'):
    if auth is not None and (auth.instance!='q1' or port!=8891):raise ValueError('Authenticated Q1 uses its separate canonical port8891')
    error=None
    if review is None:
        try:review=build_review()
        except Exception as e:error=str(e)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.review=review;server.review_error=error
    server.demo_revision='demo-'+review['build']['id'] if review else 'demo-unavailable'
    server.request_token=secrets.token_urlsafe(32) # Ephemeral request protection, not a login credential.
    server.auth=auth # Inject only after an approved local account bootstrap; default demo stays usable.
    server.uploads=UploadStore(store_root or ROOT/'runtime/uploads')
    server.upload_jobs=UploadJobs(server.uploads);server.upload_slots=threading.BoundedSemaphore(2)
    if weather_source not in ('cache','public'):raise ValueError('Unsupported public weather source mode')
    weather_class=PublicSourceStore if weather_source=='public' else PublicWeatherStore
    server.public_weather=weather_class(Path(store_root)/'public-weather' if store_root else ROOT/'runtime/public-weather')
    server.settings_path=Path(store_root)/'instance-settings.json' if store_root else ROOT/'runtime/instance-settings.json'
    server.settings={'opening_mode':'demo','weather_time':weather_time};configured_schedule=None
    try:
        settings=json.loads(server.settings_path.read_text())
        if set(settings) in ({'opening_mode','weather_time'},{'opening_mode','weather_time','weather_schedule'}) and settings['opening_mode'] in ('demo','upload'):
            next_daily(datetime.now(timezone.utc),settings['weather_time']);server.settings={key:settings[key] for key in ('opening_mode','weather_time')};configured_schedule=settings.get('weather_schedule')
    except (OSError,ValueError,TypeError):pass
    server.weather_job=DailyCacheJob(server.public_weather,server.settings['weather_time'],configured_state=configured_schedule);server.start_weather_updates=server.weather_job.start;server.stop_weather_updates=server.weather_job.stop;server.live_coverage={};server.live_coverage_lock=threading.RLock();server.clock=lambda:datetime.now(timezone.utc)
    return server

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8891);parser.add_argument('--weather-time',default='06:00');parser.add_argument('--weather-source',choices=['cache','public'],default='public');args=parser.parse_args()
    server=make_server(args.port,weather_time=args.weather_time,weather_source=args.weather_source)
    server.start_weather_updates()
    print(f'Q1 local synthetic prototype: http://127.0.0.1:{server.server_port}/',flush=True)
    try:server.serve_forever()
    finally:server.stop_weather_updates();server.upload_jobs.close();server.server_close()
