"""Bounded two-file synthetic account import. Raw rows never leave this process."""
import copy
import csv
from datetime import date, timedelta
import gzip
import io
import math
import re
import secrets
import threading
import zlib
from source_adapter import SourceError, canonical, digest, require, validate_business, records, FILES, MAX_BYTES, parse

CUSTOMER_HEADERS='customer_id,postcode,locality,region,retailer,climate_zone,tariff,meter_type,prepayment_meter,payment_method,has_solar,solar_kw,concession_card,life_support,life_support_registered_date,medical_cooling_subsidy,interpreter_required,account_open_date,account_close_date,opening_position_1jul2023'.split(',')
USAGE_HEADERS='customer_id,date,import_kwh,import_peak_kwh,import_offpeak_kwh,import_superoffpeak_kwh,export_kwh,supply_status,outage_hours'.split(',')
MAX_UPLOAD=16*1024*1024
MAX_EXPANDED=96*1024*1024
MAX_CUSTOMERS=100000
MAX_USAGE=1500000
STAGE_LIFETIME=timedelta(minutes=30)

def load_trusted_context(inputs):
    """Upload context must be a hash-verified seed, never arbitrary edited JSON.

    An unavailable seed disables uploads without taking the cached map offline.
    """
    try:
        def read(path):
            with path.open('rb') as f:raw=f.read(MAX_BYTES+1)
            require(len(raw)<=MAX_BYTES,'source_too_large')
            return raw.decode('utf-8')
        manifest=parse(read(inputs/'manifest.json'))
        data,_=records(manifest,{k:read(inputs/name) for k,name in FILES.items()})
        from geography_reference import extend_trusted_context
        return extend_trusted_context(data['business'])
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return None

class ExpandedLimit(io.RawIOBase):
    def __init__(self,stream):self.stream=stream;self.total=0
    def readable(self):return True
    def readinto(self,buffer):
        data=self.stream.read(min(len(buffer),MAX_EXPANDED-self.total+1))
        self.total+=len(data);require(self.total<=MAX_EXPANDED,'expanded_size_limit')
        buffer[:len(data)]=data;return len(data)
    def close(self):self.stream.close();super().close()

def csv_rows(raw,headers,compressed=False):
    require(0<len(raw)<=MAX_UPLOAD,'upload_size_limit')
    try:
        stream=gzip.GzipFile(fileobj=io.BytesIO(raw)) if compressed else io.BytesIO(raw)
        with io.TextIOWrapper(io.BufferedReader(ExpandedLimit(stream)),encoding='utf-8-sig',newline='') as text:
            reader=csv.DictReader(text,strict=True)
            require(reader.fieldnames==headers,'csv_headers_must_match_reviewed_schema')
            for row in reader:
                require(None not in row and all(v is not None and len(v)<=1024 and '\x00' not in v for v in row.values()),'csv_row_shape')
                yield row
    except (OSError,EOFError,UnicodeError,csv.Error,zlib.error):
        raise SourceError('invalid_csv_or_gzip') from None

def iso(value,optional=False):
    if value=='' and optional:return None
    try:
        parsed=date.fromisoformat(value)
        require(parsed.isoformat()==value,'date_format_yyyy_mm_dd')
        return parsed
    except ValueError:raise SourceError('invalid_account_or_usage_date') from None

def derive_business(customer_bytes,usage_bytes,compressed,trusted,today):
    """Latest supplied actual observation date is the cutoff, never forecast month."""
    by_postcode={a['postcode']:a for a in trusted['areas']}
    customers={}
    for r in csv_rows(customer_bytes,CUSTOMER_HEADERS):
        require(len(customers)<MAX_CUSTOMERS,'customer_row_limit')
        ident=r['customer_id'];require(re.fullmatch(r'[A-Za-z0-9_-]{1,64}',ident) is not None,'invalid_customer_id')
        require(ident not in customers,'duplicate_customer_id')
        area=by_postcode.get(r['postcode'])
        require(area is not None and r['locality'].casefold()==area['name'].casefold(),'unsupported_or_mismatched_locality')
        require(r['prepayment_meter'] in {'True','False'},'prepayment_flag_must_be_true_or_false')
        opened=iso(r['account_open_date'],True);closed=iso(r['account_close_date'],True)
        require(not (opened and closed and closed<opened),'closure_before_opening')
        customers[ident]={'postcode':r['postcode'],'prepaid':r['prepayment_meter']=='True','opened':opened,'closed':closed}
    require(customers,'empty_customer_file')
    seen={};earliest=None;latest=None;latest_ids=set();rows=0
    for r in csv_rows(usage_bytes,USAGE_HEADERS,compressed):
        rows+=1;require(rows<=MAX_USAGE,'usage_row_limit')
        ident=r['customer_id'];require(ident in customers,'usage_customer_not_in_customer_file')
        d=iso(r['date']);require(d<=today,'future_usage_observation')
        # Per-year bitsets detect duplicates without retaining every date object.
        years=seen.setdefault(ident,{})
        bit=1 << (d.toordinal()-date(d.year,1,1).toordinal())
        previous=years.get(d.year,0);require(not previous&bit,'duplicate_customer_usage_date');years[d.year]=previous|bit
        c=customers[ident]
        require(not c['opened'] or d>=c['opened'],'usage_before_account_opening')
        require(not c['closed'] or d<=c['closed'],'usage_after_recorded_closure')
        require(r['supply_status'] in {'connected','disconnected_non_payment'},'unsupported_supply_status')
        try:
            numbers=[float(r[k]) for k in USAGE_HEADERS[2:7]+['outage_hours']]
            require(all(math.isfinite(v) and v>=0 for v in numbers) and numbers[-1]<=24,'invalid_usage_number')
        except ValueError:raise SourceError('invalid_usage_number') from None
        earliest=min(earliest,d) if earliest else d
        if latest is None or d>latest:latest=d;latest_ids={ident}
        elif d==latest:latest_ids.add(ident)
    require(latest is not None,'empty_usage_file')
    areas={}
    keys=['accountCount','prepaidAccounts','billedAccounts','retainedAccountCount','closedAccounts','unknownStatusAccounts','notOpenAtSnapshotAccounts']
    for ident,c in customers.items():
        pc=c['postcode']
        if pc not in areas:
            a=copy.deepcopy(by_postcode[pc]);a.update({k:0 for k in keys});areas[pc]=a
        a=areas[pc];a['retainedAccountCount']+=1
        if c['opened'] and c['opened']>latest:a['notOpenAtSnapshotAccounts']+=1
        elif c['closed'] and c['closed']<=latest:a['closedAccounts']+=1
        elif not c['opened'] or ident not in latest_ids:a['unknownStatusAccounts']+=1
        else:
            a['accountCount']+=1;a['prepaidAccounts' if c['prepaid'] else 'billedAccounts']+=1
    result={
        'businessClassification':'Historical synthetic account aggregates; manually staged two-file import',
        'historyStart':earliest.isoformat(),'historyEnd':latest.isoformat(),'snapshotDate':latest.isoformat(),
        'snapshotBasis':'Latest actual date present in supplied consumption_daily rows',
        'activityRule':'Opened on/before snapshot, no closure on/before snapshot, and a supplied usage row on snapshot date. Missing opening or snapshot evidence is unknown and excluded. Known later openings are counted separately. Disconnected supply does not imply account closure.',
        'totalAccounts':sum(a['accountCount'] for a in areas.values()),'retainedTotalAccounts':len(customers),
        'closedAccounts':sum(a['closedAccounts'] for a in areas.values()),
        'unknownStatusAccounts':sum(a['unknownStatusAccounts'] for a in areas.values()),
        'notOpenAtSnapshotAccounts':sum(a['notOpenAtSnapshotAccounts'] for a in areas.values()),
        'snapshotUsageAccounts':len(latest_ids),'customerSourceSha256':digest(customer_bytes),'usageSourceSha256':digest(usage_bytes),
        'contextSourceSha256':trusted['contextSourceSha256'],'areas':sorted(areas.values(),key=lambda a:a['postcode'])}
    if trusted.get('geographyRegistrySha256'):
        result.update({k:trusted[k] for k in ['geographyRegistrySha256','geographySource','geographyMeaning']})
    # Trusted coordinates, income and history are copied from the existing public context.
    points=[{'postcode':a['postcode'],'name':a['name'],'lon':a['referencePoint'][0],'lat':a['referencePoint'][1]} for a in trusted['areas']]
    validate_business(result,points)
    return result,{'customerRows':len(customers),'usageRows':rows,'rawRowsPersisted':False}

class UploadStages:
    """At most four aggregate-only, one-use proposals; restart discards all stages."""
    def __init__(self,store,trusted,clock):
        self.store=store;self.trusted=trusted;self.clock=clock;self.stages={};self.lock=threading.RLock()

    def _expire(self):
        now=self.clock()
        self.stages={k:v for k,v in self.stages.items() if now<v['expires']}

    def stage(self,customers,usage,compressed,declared):
        require(declared is True,'synthetic_declaration_required')
        require(self.trusted is not None,'trusted_upload_context_unavailable')
        current=self.store.read();require(current['data'] is not None and not current['status']['last_refresh_error'],'current_source_unavailable')
        proposal,checks=derive_business(customers,usage,compressed,self.trusted,self.clock().date())
        old=current['data']['business'];old_areas={a['postcode']:a for a in old['areas']};new_areas={a['postcode']:a for a in proposal['areas']}
        differences=[{'postcode':pc,'name':(new_areas.get(pc) or old_areas[pc])['name'],'before':old_areas[pc]['accountCount'] if pc in old_areas else None,'after':new_areas[pc]['accountCount'] if pc in new_areas else None} for pc in sorted(set(old_areas)|set(new_areas))]
        with self.lock:
            self._expire();require(len(self.stages)<4,'too_many_staged_uploads')
            token=secrets.token_urlsafe(24);expires=self.clock()+STAGE_LIFETIME
            public={'stageId':token,'baseGeneration':current['generation'],'expiresAt':expires.isoformat(),'proposed':proposal,'previous':{k:old[k] for k in ['snapshotDate','totalAccounts','retainedTotalAccounts']},'differences':differences,'validation':checks}
            self.stages[token]={'public':public,'expires':expires,'proposal':proposal,'base':current['generation']}
            return public

    def replace(self,token,generation):
        with self.lock:
            self._expire();stage=self.stages.get(token);require(stage is not None,'stage_missing_or_expired')
            require(generation==stage['base'],'staged_generation_mismatch')
            packet=self.store.replace_business(stage['proposal'],generation)
            del self.stages[token]
            return packet

    def discard(self,token):
        with self.lock:self.stages.pop(token,None)

class UploadJobs:
    """One validation at a time, at most four aggregate receipts, no raw storage.

    Acceptance is separate from validation. Only UploadStages can create a
    replaceable proposal, and explicit Replace retains its generation check.
    """
    def __init__(self,stages,executor=None,gate=None):
        from concurrent.futures import ThreadPoolExecutor
        self.stages=stages;self.clock=stages.clock;self.lock=threading.RLock()
        self.owns_executor=executor is None;self.gate=gate or threading.Lock()
        self.executor=executor or ThreadPoolExecutor(max_workers=1,thread_name_prefix='q3-upload-validation')
        self.jobs={};self.running=False

    def _expire(self):
        now=self.clock()
        for token,job in list(self.jobs.items()):
            if now>=job['expires'] and job['state'] not in {'accepted','validating'}:
                if job.get('result'):self.stages.discard(job['result']['stageId'])
                del self.jobs[token]

    def submit(self,customers,usage,compressed,declared):
        require(declared is True,'synthetic_declaration_required')
        require(self.stages.trusted is not None,'trusted_upload_context_unavailable')
        require(type(customers) is bytes and type(usage) is bytes and 0<len(customers)+len(usage)<=MAX_UPLOAD,'upload_size_limit')
        return self._enqueue((customers,usage,compressed,declared))

    def _enqueue(self,args):
        with self.lock:
            self._expire();require(not self.running,'another_validation_in_progress')
            for old,job in list(self.jobs.items()):
                if len(self.jobs)<4:break
                if job['state']=='failed':del self.jobs[old]
            require(len(self.jobs)<4,'too_many_validation_receipts')
            require(self.gate.acquire(blocking=False),'another_validation_in_progress')
            token=secrets.token_urlsafe(24);expires=self.clock()+STAGE_LIFETIME
            self.jobs[token]={'state':'accepted','expires':expires};self.running=True
            try:self.executor.submit(self._validate,token,args)
            except Exception:
                self.running=False;del self.jobs[token];self.gate.release();raise SourceError('validation_worker_unavailable') from None
            return {'jobId':token,'state':'accepted','validation':'pending','expiresAt':expires.isoformat(),'currentDataChanged':False}

    def _validate(self,token,args):
        try:
            with self.lock:self.jobs[token]['state']='validating'
            proposal=self.stages.stage(*args)
            with self.lock:self.jobs[token].update(state='ready',result=proposal)
        except SourceError as error:
            with self.lock:self.jobs[token].update(state='failed',error=str(error))
        except Exception:
            with self.lock:self.jobs[token].update(state='failed',error='validation_failed_previous_data_retained')
        finally:
            with self.lock:self.running=False;self.gate.release()

    def status(self,token):
        require(type(token) is str and re.fullmatch(r'[A-Za-z0-9_-]{32}',token) is not None,'invalid_validation_receipt')
        with self.lock:
            self._expire();job=self.jobs.get(token);require(job is not None,'validation_receipt_missing_or_expired')
            return {'jobId':token,'state':job['state'],'expiresAt':job['expires'].isoformat(),'currentDataChanged':False,**({'result':copy.deepcopy(job['result'])} if job.get('result') else {}),**({'error':job['error']} if job.get('error') else {})}

    def discard_receipt(self,stage_id):
        with self.lock:
            for token,job in list(self.jobs.items()):
                if job.get('result',{}).get('stageId')==stage_id:del self.jobs[token]

    def close(self):
        if self.owns_executor:self.executor.shutdown(wait=True,cancel_futures=False)
