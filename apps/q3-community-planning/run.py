"""Q3 community planning prototype: separate loopback instance, no source fetcher."""
import argparse
import json
import base64,hashlib,re,sqlite3
from email.parser import BytesParser
from email.policy import default
from collections import OrderedDict
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit,parse_qs
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent/'server'))
from map_proxy import Handler,read_maptiler_key
from source_adapter import SnapshotStore,SourceError,parse
from business_upload import UploadStages,UploadJobs,MAX_UPLOAD,load_trusted_context
from history_archive import HistoryArchive
from financial_intake import FinancialStages,FinancialJobs,MAX_FINANCIAL_UPLOAD,PART_FILES
from local_auth import AuthService,AuthError,AUTH_PATHS,header
from account_lookup import ReadOnlyAccounts
from statistical_outlook import StatisticalOutlook

ROOT=Path(__file__).resolve().parent
STATISTICAL=StatisticalOutlook(ROOT/'data/statistical/ml_outlook_layer.json')
class Q3Handler(Handler):
    def reply(self,payload,content_type,status=200,cache=False,extra_headers=(),csp=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','private, max-age=3600' if cache else 'no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',csp or "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
        for name,value in extra_headers:self.send_header(name,value)
        self.end_headers()
        try:self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError):pass

    def _auth_guard(self,method):
        path=urlsplit(self.path).path;auth=getattr(self.server,'auth',None)
        try:
            if path=='/healthz' and method=='GET':
                self.json_reply({'alive':True,'instance':'q3','authenticationConfigured':auth is not None});return True
            if path=='/auth/login' and method=='GET':
                if header(self.headers,'Host') not in {'localhost:8797','127.0.0.1:8797'}:raise AuthError(403,'Canonical local host required')
                payload=(ROOT/'web/login.html').read_bytes();script=re.search(rb'<script>(.*?)</script>',payload,re.S).group(1);sha=base64.b64encode(hashlib.sha256(script).digest()).decode()
                self.reply(payload,'text/html',csp="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'sha256-"+sha+"'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'");return True
            if path in AUTH_PATHS:
                if auth is None:
                    self.json_reply({'authenticated':False,'mode':'local-preview','enforcementConfigured':False} if path=='/api/session' and method=='GET' else {'error':'Sign-in is not configured for this local preview'},200 if path=='/api/session' and method=='GET' else 503);return True
                body=b''
                if method=='POST':
                    length=header(self.headers,'Content-Length')
                    if header(self.headers,'Transfer-Encoding') or not re.fullmatch(r'[0-9]{1,5}',length) or not 0<int(length)<=4096:
                        self.close_connection=True;raise AuthError(400,'Invalid auth body framing')
                    self.connection.settimeout(5);body=self.rfile.read(int(length))
                    if len(body)!=int(length):raise AuthError(400,'Incomplete auth body')
                result=auth.auth_route(method,self.path,self.headers,body)
                self.reply(json.dumps(result.body).encode(),'application/json',result.status,extra_headers=result.headers);return True
            if auth is not None:self.principal=auth.authorize(method,self.path,self.headers,'q3')
            return False
        except AuthError as error:
            self.close_connection=True
            if method=='GET' and error.status==401 and self.headers.get('Sec-Fetch-Mode')=='navigate':self.reply(b'','text/plain',303,extra_headers=(('Location','/auth/login'),))
            else:self.json_reply({'error':error.message},error.status)
            return True
        except (OSError,ValueError,sqlite3.Error):
            self.close_connection=True;self.json_reply({'error':'Sign-in service unavailable'},503);return True

    def do_GET(self):
        if self._auth_guard('GET'):return
        parsed=urlsplit(self.path)
        try:host=urlsplit('http://'+self.headers.get('Host','')).hostname
        except ValueError:host=None
        if parsed.path in {'/api/q3/business/stage-status','/api/q3/financial/stage-status'}:
            if host not in {'127.0.0.1','localhost'} or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.json_reply({'error':'same_origin_loopback_required'},403);return
            try:
                query=parse_qs(parsed.query,strict_parsing=True)
                if set(query)!={'id'} or len(query['id'])!=1:raise SourceError('invalid_validation_receipt')
                jobs=self.server.financial_jobs if parsed.path.startswith('/api/q3/financial/') else self.server.upload_jobs
                self.json_reply(jobs.status(query['id'][0]))
            except SourceError as error:self.json_reply({'error':str(error)},404 if str(error)=='validation_receipt_missing_or_expired' else 422)
            except (ValueError,KeyError,TypeError):self.json_reply({'error':'invalid_validation_receipt'},422)
            return
        if parsed.path.startswith('/api/q3/history/') or parsed.path.startswith('/history/'):
            if host not in {'127.0.0.1','localhost'} or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.json_reply({'error':'same_origin_loopback_required'},403);return
            archive=self.server.history
            if archive is None:self.json_reply({'error':'historical_archive_unavailable'},503);return
            try:
                if parsed.path=='/api/q3/history/metadata':self.json_reply(archive.metadata)
                elif parsed.path=='/api/q3/history/cell':
                    query=parse_qs(parsed.query,strict_parsing=True)
                    if set(query)!={'layer','lon','lat'} or any(len(v)!=1 for v in query.values()):raise SourceError('history_query_invalid')
                    self.json_reply(archive.cell(query['layer'][0],float(query['lon'][0]),float(query['lat'][0])))
                elif parsed.path.startswith('/history/') and parsed.path.endswith('.png'):
                    self.reply(archive.image(parsed.path.removeprefix('/history/').removesuffix('.png')),'image/png',cache=True)
                else:self.json_reply({'error':'history_route_not_allowed'},404)
            except (OSError,ValueError,KeyError,TypeError):self.json_reply({'error':'historical_layer_unavailable'},503)
            return
        if parsed.path=='/api/q3/statistical-outlook':
            if host not in {'127.0.0.1','localhost'} or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.json_reply({'error':'same_origin_loopback_required'},403);return
            self.json_reply(getattr(self.server,'statistical_outlook',STATISTICAL).read());return
        if parsed.path=='/api/q3/snapshot':
            if host not in {'127.0.0.1','localhost'} or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.json_reply({'error':'Same-origin loopback request required'},403);return
            self.json_reply(self.server.snapshots.read());return
        if parsed.path in {'/','/business.html'} and host in {'127.0.0.1','localhost'} and self.headers.get('Sec-Fetch-Mode')=='navigate':
            page='index.html' if parsed.path=='/' else 'business.html'
            self.reply((ROOT/'web'/page).read_bytes(),'text/html');return
        super().do_GET()

    def do_POST(self):
        if self._auth_guard('POST'):return
        try:
            host=self.headers.get('Host','');parsed=urlsplit('http://'+host)
            allowed=parsed.hostname in {'127.0.0.1','localhost'} and parsed.port==self.server.server_port
            if not allowed or self.headers.get('Origin')!='http://'+host or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.close_connection=True;self.json_reply({'error':'same_origin_loopback_required'},403);return
            path=urlsplit(self.path).path
            financial=path.startswith('/api/q3/financial/')
            prefix='/api/q3/financial/' if financial else '/api/q3/business/'
            if path not in {prefix+'stage',prefix+'replace',prefix+'discard'}:
                self.close_connection=True;self.json_reply({'error':'route_not_allowed'},404);return
            raw_length=self.headers.get('Content-Length','')
            lengths=self.headers.get_all('Content-Length') if hasattr(self.headers,'get_all') else [raw_length]
            if len(lengths)!=1 or re.fullmatch(r'[0-9]{1,9}',raw_length) is None:raise SourceError('invalid_body_framing')
            length=int(raw_length)
            limit=(MAX_FINANCIAL_UPLOAD if financial else MAX_UPLOAD) if path.endswith('/stage') else 4096
            if not 0<length<=limit or self.headers.get('Transfer-Encoding'):
                self.close_connection=True;self.json_reply({'error':'upload_size_limit'},413);return
            gate=getattr(self.server,'validation_gate',None)
            if path.endswith('/stage') and gate is not None and gate.locked():
                self.close_connection=True;self.json_reply({'error':'another_validation_in_progress'},409);return
            stages=self.server.financial_uploads if financial else self.server.uploads
            jobs=self.server.financial_jobs if financial else self.server.upload_jobs
            if not self.server.upload_slot.acquire(blocking=False):
                self.close_connection=True;self.json_reply({'error':'another_upload_in_progress'},409);return
            try:
                self.connection.settimeout(30)
                raw=self.rfile.read(length)
                if len(raw)!=length:raise SourceError('incomplete_upload')
                if path.endswith('/stage'):
                    kind=self.headers.get('Content-Type','')
                    if len(kind)>300 or not kind.startswith('multipart/form-data;'):raise SourceError('multipart_upload_required')
                    message=BytesParser(policy=default).parsebytes(('Content-Type: '+kind+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
                    if not message.is_multipart() or message.defects:raise SourceError('invalid_multipart')
                    expected=set(PART_FILES)|{'synthetic','baseGeneration'} if financial else {'customers','usage','synthetic'}
                    parts={}
                    for part in message.iter_parts():
                        name=part.get_param('name',header='content-disposition')
                        if part.is_multipart() or part.defects or part.get('Content-Transfer-Encoding') is not None or name not in expected or name in parts:raise SourceError('unexpected_upload_fields')
                        parts[name]=part
                    if set(parts)!=expected:raise SourceError('complete_financial_upload_required' if financial else 'two_files_and_declaration_required')
                    if financial:
                        if any(parts[k].get_filename()!=name for k,name in PART_FILES.items()) or any(parts[k].get_filename() is not None for k in ['synthetic','baseGeneration']):raise SourceError('use_existing_financial_schema_filenames')
                        files={k:parts[k].get_payload(decode=True) for k in PART_FILES}
                        base=parts['baseGeneration'].get_payload(decode=True)
                        if re.fullmatch(rb'[0-9a-f]{64}',base) is None:raise SourceError('invalid_base_generation')
                        result=jobs.submit(files,parts['synthetic'].get_payload(decode=True)==b'true',base.decode('ascii'))
                    else:
                        cname=parts['customers'].get_filename();uname=parts['usage'].get_filename()
                        if cname!='customers.csv' or uname not in {'consumption_daily.csv','consumption_daily.csv.gz'}:raise SourceError('use_existing_schema_filenames')
                        result=jobs.submit(parts['customers'].get_payload(decode=True),parts['usage'].get_payload(decode=True),uname.endswith('.gz'),parts['synthetic'].get_payload(decode=True)==b'true')
                    self.json_reply(result,202)
                else:
                    if self.headers.get('Content-Type')!='application/json':raise SourceError('json_required')
                    request=parse(raw.decode('utf-8'));token=request.get('stageId')
                    if not isinstance(token,str) or len(token)>100:raise SourceError('invalid_stage_id')
                    if path.endswith('/replace'):
                        self.json_reply(stages.replace(token,request.get('baseGeneration')))
                        jobs.discard_receipt(token)
                    else:
                        stages.discard(token);jobs.discard_receipt(token);self.json_reply({'discarded':True})
            finally:self.server.upload_slot.release()
        except SourceError as exc:
            code=str(exc);self.json_reply({'error':code},409 if code in {'stage_missing_or_expired','staged_generation_mismatch','active_snapshot_changed_restage_required','current_source_unavailable','too_many_staged_uploads','another_validation_in_progress','too_many_validation_receipts'} else 422)
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            self.close_connection=True;self.json_reply({'error':'upload_or_storage_failed_previous_data_retained'},503)

    def _unsupported(self):
        if not self._auth_guard(self.command):self.json_reply({'error':'Method not allowed'},405)
    do_HEAD=_unsupported
    do_PUT=_unsupported
    do_PATCH=_unsupported
    do_DELETE=_unsupported
    do_OPTIONS=_unsupported

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8797)
    p.add_argument('--inputs-dir',type=Path,default=ROOT/'data/inputs')
    p.add_argument('--runtime-dir',type=Path,default=ROOT/'.runtime')
    p.add_argument('--auth-mode',choices=['preview','enforced'],default='preview')
    p.add_argument('--auth-store',type=Path,help='Existing approved Q3-only SQLite account store; read-only')
    p.add_argument('--maptiler-env',type=Path,default=ROOT/'.runtime/maptiler.env')
    args=p.parse_args()
    auth=None
    if args.auth_mode=='enforced':
        if args.port!=8797 or args.auth_store is None:p.error('Enforced mode requires canonical port8797 and an approved existing Q3 account store')
        try:auth=AuthService('q3',ReadOnlyAccounts(args.auth_store))
        except (OSError,ValueError,sqlite3.Error):p.error('Approved Q3 account store unavailable; no account or credential was created')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Q3Handler)
    server.auth=auth
    server.snapshots=SnapshotStore(args.inputs_dir,args.runtime_dir)
    trusted=load_trusted_context(args.inputs_dir)
    server.uploads=UploadStages(server.snapshots,trusted,server.snapshots.clock)
    from concurrent.futures import ThreadPoolExecutor
    server.validation_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='q3-validation')
    server.validation_gate=threading.Lock()
    server.upload_jobs=UploadJobs(server.uploads,server.validation_executor,server.validation_gate)
    server.financial_uploads=FinancialStages(server.snapshots,trusted,server.snapshots.clock)
    server.financial_jobs=FinancialJobs(server.financial_uploads,server.validation_executor,server.validation_gate)
    server.upload_slot=threading.BoundedSemaphore(1)
    try:server.history=HistoryArchive(ROOT/'data/history')
    except (OSError,ValueError,KeyError,TypeError):server.history=None
    server.missing_map=server.missing_data=server.missing_basemap=False
    server.maptiler_key=read_maptiler_key(args.maptiler_env)
    server.map_cache=OrderedDict();server.map_lock=threading.Lock()
    server.map_stats={'upstream_successes':0,'upstream_failures':0,'cache_hits':0,'last_failure_status':None}
    print(f'Q3 community planning prototype: http://127.0.0.1:{args.port}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();server.validation_executor.shutdown(wait=True,cancel_futures=False)
if __name__=='__main__':main()
