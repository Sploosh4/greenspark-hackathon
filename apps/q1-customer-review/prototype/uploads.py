"""One local synthetic instance: immutable staging, explicit activation, recovery.

This is file/version handling, not authentication or a prediction method.
"""
from pathlib import Path
from io import BytesIO,TextIOWrapper
from datetime import datetime
from dataclasses import dataclass
from collections import OrderedDict
import copy
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import threading
import uuid
import time
from .inputs import InputError,DEFAULT_SOURCE,KEYS,validate_row,number,iso
from .review import build_review
from .work import WorkControl,WorkCancelled,WorkLimit,work_scope,checkpoint

APP_ROOT=Path(__file__).resolve().parents[1]
CONTRACT=json.loads((APP_ROOT/'docs/UPLOAD-VALIDATION-CONTRACT.json').read_text())
SPECS=CONTRACT['files']
NAMES={s['filename'] for s in SPECS}
MAX_BODY=64*1024*1024
MAX_FILE=32*1024*1024
MAX_DECODED=128*1024*1024
MAX_DECODED_BATCH=256*1024*1024
MAX_ROWS=1_000_000
MAX_BATCH_ROWS=1_000_000
MAX_CUSTOMERS=50_000
ID=re.compile(r'^[a-f0-9]{32}$')
BOOLS={'customers':('prepayment_meter','has_solar','concession_card','life_support','medical_cooling_subsidy','interpreter_required'),
       'bills':('due_date_extended','final_bill','opening_balance','paid_on_time','is_opening_debt'),
       'hardship_programs':('financial_counselling_referral','energy_efficiency_advice')}
DOMAINS={('payments','status'):{'cleared','dishonoured'},('hardship_programs','assessment_outcome'):{'accepted','denied'},
 ('hugs_grants','outcome'):{'approved','declined'},('payment_arrangements','type'):{'bill_extension','payment_plan'},
 ('payment_arrangements','status'):{'active','broken','closed_account','completed','granted','transferred_to_hardship'},
 ('support_needs_history','status'):{'closed_account','current','resolved'},
 ('support_arrangement_history','source_table'):{'hardship_programs','payment_arrangements'}}
REQUIRED_DATES={'bills':('issue_date','original_due_date','due_date'),'payments':('date',),
 'support_needs_history':('effective_from','source_event_date'),'support_arrangement_history':('effective_from','source_event_date'),
 'hardship_programs':('assessment_date',),'hugs_grants':('application_date',),'payment_arrangements':('start_date',)}

class UploadError(ValueError):
    def __init__(self,message,status=400):super().__init__(message);self.status=status

@dataclass(frozen=True)
class RetentionLimits:
    snapshots:int=16
    bytes:int=512*1024*1024
    jobs:int=128
    cache_entries:int=2
    stage_ttl_seconds:int=3600
    review_bytes:int=64*1024*1024

METADATA_RESERVATION=1024*1024

def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe_id(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise UploadError('Invalid upload operation identifier')
    return value

def write_json(path,value):
    """Durable file then same-directory atomic rename; never a partial pointer."""
    path=Path(path);tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as out:out.write(encoded(value));out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
        fd=os.open(path.parent,os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:tmp.unlink(missing_ok=True)

def check_extra(table,row):
    for field in BOOLS.get(table,()):
        if row[field] not in ('True','False'):raise InputError(f'{field}: expected True or False')
    for (name,field),values in DOMAINS.items():
        if name==table and row[field] not in values:raise InputError(f'{field}: unsupported value')
    for field in REQUIRED_DATES.get(table,()):iso(row[field],field=field,required=True)
    for start,end,exclusive in [('period_start_date','period_end_date',False),('effective_from','effective_to',True),('start_date','end_date',False),('start_date','exit_date',False)]:
        if row.get(start) and row.get(end):
            if row[end]<row[start] or (exclusive and row[end]==row[start]):raise InputError(f'{end}: precedes or empties {start}')
    if table=='prepay_topups':
        value=row['datetime']
        try:
            parsed=datetime.fromisoformat(value)
            if len(value)==10:iso(value,field='datetime',required=True)
            elif len(value)<16 or value[10] not in ('T',' '):raise ValueError()
        except ValueError as e:raise InputError('datetime: expected an ISO date or timestamp') from e
    if table=='customer_locations':
        for field,lo,hi in [('latitude',-90,90),('longitude',-180,180)]:
            v=number(row[field],field=field,required=True)
            if not lo<=v<=hi:raise InputError(f'{field}: out of range')

def validate_files(parts,root,cancelled=lambda:False):
    """Only server-owned filenames/columns. Counts/hashes belong to this batch."""
    if len(parts)!=12:raise UploadError('Choose the complete set of twelve business files')
    names=[name for name,_ in parts]
    if len(set(names))!=len(names):raise UploadError('Duplicate filenames in the upload')
    if set(names)!=NAMES:raise UploadError('Unexpected or missing filename. Use the twelve existing CSV/gzip names; archives and paths are not accepted')
    files=dict(parts)
    if sum(len(b) for b in files.values())>MAX_BODY:raise UploadError('Upload exceeds 64 MiB',413)
    for name,raw in parts:
        if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_FILE:raise UploadError(f'{name}: empty or exceeds 32 MiB',413)
    folder=root/'candidate-business-data';folder.mkdir()
    known=set();local=set();parents={'payment_arrangements':{},'hardship_programs':{}};links=[];grants=[];specs=[];total_decoded=0;total_rows=0
    for spec in SPECS:
        if cancelled():raise UploadError('Upload cancelled',409)
        name=spec['filename'];table=spec['table'];raw=files[name]
        try:
            decoded=0
            source=gzip.GzipFile(fileobj=BytesIO(raw)) if name.endswith('.gz') else BytesIO(raw)
            with source:
                while chunk:=source.read(65536):
                    checkpoint()
                    decoded+=len(chunk)
                    if decoded>MAX_DECODED or total_decoded+decoded>MAX_DECODED_BATCH:raise UploadError(f'{name}: decoded data exceeds the limit',413)
                    if cancelled():raise UploadError('Upload cancelled',409)
            total_decoded+=decoded
            source=gzip.GzipFile(fileobj=BytesIO(raw)) if name.endswith('.gz') else BytesIO(raw)
            seen=set();count=0;dates=[]
            with TextIOWrapper(source,encoding='utf-8-sig',newline='') as stream:
                reader=csv.DictReader(stream,strict=True)
                if reader.fieldnames!=spec['ordered_headers']:raise InputError('ordered columns differ from the existing schema')
                for row in reader:
                    count+=1;total_rows+=1
                    if count%256==0:checkpoint(256)
                    if count>MAX_ROWS:raise UploadError(f'{name}: too many rows',413)
                    if total_rows>MAX_BATCH_ROWS:raise UploadError('The batch exceeds one million business rows',413)
                    if count%1000==0 and cancelled():raise UploadError('Upload cancelled',409)
                    if None in row or any(v is None for v in row.values()):raise InputError('malformed CSV row')
                    key=tuple(row[k] for k in KEYS[table])
                    if any(not x for x in key) or key in seen:raise InputError('blank or duplicate primary key')
                    seen.add(key)
                    if table=='customers':
                        known.add(row['customer_id'])
                        if len(known)>MAX_CUSTOMERS:raise UploadError('The batch exceeds 50,000 customers',413)
                        if row['postcode']=='6765':local.add(row['customer_id'])
                    validate_row(table,row,known);check_extra(table,row)
                    if table in parents:parents[table][row['arrangement_id' if table=='payment_arrangements' else 'hardship_id']]=row['customer_id']
                    if table=='support_arrangement_history':links.append((row['source_table'],row['arrangement_id'],row['customer_id']))
                    if table=='hugs_grants':grants.append((row['hardship_id'],row['customer_id']))
            with (folder/name).open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
            specs.append({'file':'candidate-business-data/'+name,'headers':spec['ordered_headers'],'rows':count,'sha256':digest(raw)})
        except (UploadError,WorkCancelled,WorkLimit):raise
        except (InputError,UnicodeError,csv.Error,OSError,EOFError,ValueError) as e:raise UploadError(f'{name}, data row {locals().get("count",0)}: {e}') from e
    if not local:raise UploadError('No Fitzroy Crossing 6765 customer is present')
    for table,record,cid in links:
        if parents.get(table,{}).get(record)!=cid:raise UploadError('support_arrangement_history.csv: parent record/customer does not match')
    for record,cid in grants:
        if record and parents['hardship_programs'].get(record)!=cid:raise UploadError('hugs_grants.csv: hardship parent/customer does not match')
    manifest={'source_version':'Local synthetic upload; existing business schemas','files':specs}
    write_json(root/'SCHEMAS-AND-COVERAGE.json',manifest)
    return {'files':specs,'total_rows':sum(s['rows'] for s in specs),'source_customers':len(known),'locality_customers':len(local),'decoded_bytes':total_decoded,'source_fingerprint':digest(encoded([(s['file'],s['sha256']) for s in specs]))}

class UploadStore:
    def __init__(self,root,builder=None,fault=None,*,limits=None,clock=time.time):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.staging=self.root/'staging';self.batches=self.root/'batches';self.quarantine=self.root/'quarantine'
        for folder in (self.staging,self.batches,self.quarantine):
            folder.mkdir(exist_ok=True)
            if folder.is_symlink():raise UploadError('Saved upload directory is unsafe')
        self.limits=limits or RetentionLimits();self.clock=clock
        if any(value<=0 for value in vars(self.limits).values()):raise ValueError('Retention limits must be positive')
        self.lock=threading.RLock();self.jobs=OrderedDict();self.cancelled=OrderedDict();self.recovery=None;self.fault=fault or (lambda phase:None)
        self.builder=builder or (lambda path:build_review(path,weather_root=DEFAULT_SOURCE))
        # Unknown/interrupted copies are preserved, not silently deleted at boot.
        for folder in list(self.staging.iterdir()):
            if ID.fullmatch(folder.name) and folder.is_dir() and not folder.is_symlink():self._quarantine_stage(folder.name)
        self.state={'revision':'none','active':None,'previous':None,'operation':None};self.cache=OrderedDict()
        self._recover()

    def _inventory(self):
        def size_of(path):
            try:return os.stat(path,follow_symlinks=False).st_size
            except FileNotFoundError:return 0 # An unfinished atomic write may rename its temporary file.
        sizes={};total=0
        for tier in (self.staging,self.batches,self.quarantine):
            for folder in tier.iterdir():
                size=folder.lstat().st_size if folder.is_symlink() or not folder.is_dir() else 0
                if folder.is_dir() and not folder.is_symlink():
                    for directory,dirs,files in os.walk(folder,followlinks=False):
                        for name in files:size+=size_of(Path(directory)/name)
                        for name in dirs:
                            q=Path(directory)/name
                            if q.is_symlink():size+=q.lstat().st_size
                sizes[(tier.name,folder.name)]=size;total+=size
        for file in self.root.iterdir():
            if file.is_file() or file.is_symlink():total+=file.lstat().st_size
        return sizes,total

    def _quarantine_stage(self,operation):
        folder=self.staging/operation
        if not folder.exists():return
        if folder.is_symlink() or not folder.is_dir():raise UploadError('Saved stage is unsafe')
        target=self.quarantine/('stage-'+operation)
        if target.exists():target=target.with_name(target.name+'-'+uuid.uuid4().hex)
        os.replace(folder,target) # Same filesystem; every original byte retained.
        for directory in (self.staging,self.quarantine):
            fd=os.open(directory,os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)

    def _pinned_job(self,operation,job):
        return not job.get('finished') or (job.get('receipt',{}).get('expected_revision')==self.state['revision'] and (self.batches/operation).exists() and operation!=self.state['active'])

    def _retire(self,operation):
        job=self.jobs.get(operation)
        if job is None:return True
        if self._pinned_job(operation,job):return False
        self._quarantine_stage(operation);self.jobs.pop(operation,None);return True

    def _maintenance(self):
        now=self.clock()
        for operation,job in list(self.jobs.items()):
            if job.get('finished') and job.get('expires_at',now+1)<=now:self._retire(operation)
        while len(self.jobs)>self.limits.jobs:
            victim=next((op for op,job in self.jobs.items() if not self._pinned_job(op,job)),None)
            if victim is None:break
            self._retire(victim)
        while len(self.cache)>self.limits.cache_entries:self.cache.popitem(last=False)

    def retire(self,operation):
        """Coordinate outer status eviction with the underlying checked copy."""
        with self.lock:return self._retire(safe_id(operation))

    def stage_available(self,operation):
        with self.lock:
            self._maintenance();job=self.jobs.get(operation)
            return bool(job and job.get('receipt') and not job['cancel_event'].is_set() and ((self.staging/operation).is_dir() or (self.batches/operation).is_dir()))

    def _capacity(self,reservation):
        sizes,total=self._inventory();reserved=0;count=len(sizes)
        for operation,job in self.jobs.items():
            if job.get('finished'):continue
            written=sizes.get(('staging',operation),0)
            reserved+=max(0,job['reserved_bytes']-written)
            if ('staging',operation) not in sizes:count+=1
        if count+1>self.limits.snapshots or total+reserved+reservation>self.limits.bytes:
            raise UploadError('Upload storage limit reached. Retained files were preserved; the owner must archive copies before another upload.',429)

    def _put_cache(self,bid,value):
        self.cache[bid]=value;self.cache.move_to_end(bid)
        while len(self.cache)>self.limits.cache_entries:self.cache.popitem(last=False)
        return value

    def _snapshot(self,bid):
        safe_id(bid);folder=self.batches/bid
        if folder.is_symlink():raise UploadError('Saved batch path is unsafe')
        snapshot_path=folder/'snapshot.json';review_path=folder/'review.json'
        if snapshot_path.is_symlink() or snapshot_path.stat().st_size>METADATA_RESERVATION:raise UploadError('Saved snapshot metadata exceeds its limit or is unsafe')
        if review_path.is_symlink() or review_path.stat().st_size>self.limits.review_bytes:raise UploadError('Saved review exceeds its snapshot limit or is unsafe')
        info=json.loads(snapshot_path.read_text());review_raw=review_path.read_bytes()
        if digest(review_raw)!=info['review_sha256']:raise UploadError('Saved review integrity check failed')
        for name in NAMES:
            p=folder/'candidate-business-data'/name
            if p.is_symlink() or p.stat().st_size>MAX_FILE or digest(p.read_bytes())!=info['file_sha256'][name]:raise UploadError('Saved source integrity check failed')
        if not info.get('complete'):raise UploadError('Saved batch is incomplete')
        return json.loads(review_raw),info

    def _recover(self):
        current=self.root/'state.json';backup=self.root/'last-good.json'
        if not current.exists() and not backup.exists():return
        try:
            state=json.loads(current.read_text());safe_id(state['revision'])
            review,info=self._snapshot(state['active']);self.state=state;self._put_cache(state['active'],(review,info));return
        except (OSError,ValueError,KeyError,TypeError):pass
        options=[]
        try:
            state=json.loads(current.read_text());options.append(state.get('previous'))
        except (OSError,ValueError):pass
        try:options.append(json.loads(backup.read_text()).get('active'))
        except (OSError,ValueError):pass
        for bid in options:
            if not bid:continue
            try:review,info=self._snapshot(bid)
            except (OSError,ValueError,KeyError,TypeError):continue
            self._put_cache(bid,(review,info));self.state={'revision':uuid.uuid4().hex,'active':bid,'previous':None,'operation':None}
            write_json(current,self.state);self.recovery='Recovered the previous valid uploaded batch after a saved-data integrity check failed.';return
        self.recovery='Uploaded data is unavailable because no intact saved batch could be recovered. The preloaded demonstration is still available.'
        self.state={'revision':uuid.uuid4().hex,'active':None,'previous':None,'operation':None};write_json(current,self.state)

    def _get(self,bid):
        if bid not in self.cache:return self._put_cache(bid,self._snapshot(bid))
        self.cache.move_to_end(bid);return self.cache[bid]

    def status(self):
        with self.lock:
            self._maintenance()
            info=self._get(self.state['active'])[1] if self.state['active'] else None
            sizes,retained_bytes=self._inventory()
            return {'retention':{'snapshots':len(sizes),'bytes':retained_bytes,'max_snapshots':self.limits.snapshots,'max_bytes':self.limits.bytes,'quarantined':sum(tier=='quarantine' for tier,name in sizes),'stage_ttl_seconds':self.limits.stage_ttl_seconds},'revision':self.state['revision'],'active_batch':self.state['active'],'previous_available':bool(self.state['previous']),'summary':info.get('summary') if info else None,'recovery':self.recovery,'limits':{'transport_mib':64,'file_mib':32,'decoded_file_mib':128,'decoded_batch_mib':256,'files':12},'filenames':sorted(NAMES)}

    def view(self,revision=None):
        with self.lock:
            if revision is not None and revision!=self.state['revision']:raise UploadError('Uploaded data changed. Reload the review before exporting.',409)
            bid=self.state['active']
            if not bid:raise UploadError('No uploaded data is active',404)
            review,info=self._get(bid);r=copy.deepcopy(review)
            r.update(data_mode='upload',batch_id=bid,batch_revision=self.state['revision'])
            return r

    def assert_revision(self,revision):
        """Recheck export version without copying an already captured snapshot."""
        with self.lock:
            if revision!=self.state['revision']:raise UploadError('Uploaded data changed. Reload the review before exporting.',409)
            if not self.state['active']:raise UploadError('No uploaded data is active',404)

    def stage(self,parts,operation,expected_revision):
        operation=safe_id(operation)
        fingerprint=digest(encoded([(n,digest(b)) for n,b in parts]))
        with self.lock:
            self._maintenance()
            if operation in self.jobs:
                job=self.jobs[operation]
                if job['fingerprint']!=fingerprint:raise UploadError('Operation identifier reused with different files',409)
                if job.get('receipt'):return copy.deepcopy(job['receipt'])
                raise UploadError('This upload is already being checked or was cancelled',409)
            if expected_revision!=self.state['revision']:raise UploadError('Uploaded data changed. Review the current batch and try again.',409)
            if operation in self.cancelled:raise UploadError('Upload cancelled',409)
            if (self.batches/operation).exists() or (self.staging/operation).exists() or any(p.name.split('-')[1:2]==[operation] for p in self.quarantine.iterdir()):raise UploadError('This operation already belongs to a retained copy',409)
            if sum(not j.get('finished') for j in self.jobs.values())>=2:raise UploadError('Another upload is being checked. Wait or cancel it.',409)
            reservation=sum(len(raw) for _,raw in parts)+self.limits.review_bytes+METADATA_RESERVATION
            self._capacity(reservation)
            event=threading.Event();self.jobs[operation]={'fingerprint':fingerprint,'finished':False,'cancel_event':event,'reserved_bytes':reservation,'expires_at':self.clock()+self.limits.stage_ttl_seconds}
        folder=self.staging/operation;created=False
        control=WorkControl(event.is_set)
        try:
            folder.mkdir();created=True
            with work_scope(control):
                summary=validate_files(parts,folder,event.is_set)
                control.calculation();review=self.builder(folder);checkpoint()
                review['input_validation']['source_root']=str(self.batches/operation)
                encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'),allow_nan=False)
                size=0;sha=hashlib.sha256()
                with (folder/'review.json').open('xb') as out:
                    for chunk in encoder.iterencode(review):
                        checkpoint();raw=chunk.encode();size+=len(raw)
                        if size>self.limits.review_bytes:raise UploadError('Calculated review exceeds the 64 MiB snapshot limit',413)
                        out.write(raw);sha.update(raw)
                    out.flush();os.fsync(out.fileno())
                receipt={'stage_id':operation,'expected_revision':expected_revision,'summary':{**summary,'review_customers':len(review['customers']),'events':len(review['events']),'review_date':review['review_date'],'method_id':review['method']['id']},'warnings':['Historical synthetic replay for Fitzroy Crossing; the review date and weather are unchanged.']}
                info={'complete':True,'review_sha256':sha.hexdigest(),'file_sha256':{Path(s['file']).name:s['sha256'] for s in summary['files']},'summary':receipt['summary'],'receipt':receipt}
                if len(encoded(info))>METADATA_RESERVATION:raise UploadError('Calculated snapshot metadata exceeds its size limit',413)
                write_json(folder/'snapshot.json',info);checkpoint()
                with self.lock:
                    checkpoint();self.jobs[operation].update(receipt=receipt,finished=True)
                    self._maintenance()
                return copy.deepcopy(receipt)
        except Exception as error:
            # Only this attempt's incomplete scratch copy is discarded. Finished
            # or pre-existing material is never deleted by retention maintenance.
            with self.lock:
                if created:shutil.rmtree(folder,ignore_errors=True)
                self.jobs[operation].update(finished=True);self._maintenance()
            if isinstance(error,WorkCancelled):raise UploadError(str(error),409) from error
            if isinstance(error,WorkLimit):raise UploadError(str(error),422) from error
            raise

    def cancel(self,operation):
        operation=safe_id(operation)
        with self.lock:
            self.cancelled[operation]=None;self.cancelled.move_to_end(operation)
            job=self.jobs.get(operation)
            if job:
                job['cancel_event'].set()
                if job.get('finished'):
                    self._quarantine_stage(operation);job.pop('receipt',None)
            while len(self.cancelled)>self.limits.jobs:self.cancelled.popitem(last=False)
            self._maintenance()
            return {'cancelled':True,'revision':self.state['revision']}

    def _commit(self,bid,previous,operation):
        state={'revision':uuid.uuid4().hex,'active':bid,'previous':previous,'operation':operation}
        write_json(self.root/'last-good.json',self.state);self.fault('backup_written')
        try:write_json(self.root/'state.json',state)
        except OSError:
            # A directory-sync failure may be reported after atomic rename.
            # Reflect that complete pointer in status rather than claiming the
            # old version is still active; repeating this operation is safe.
            try:
                if json.loads((self.root/'state.json').read_text())==state:
                    self.state=state;self.recovery='The complete replacement switched, but storage sync reported a problem. Check this data version before continuing.'
            except (OSError,ValueError):pass
            raise
        self.state=state;self.recovery=None;self.fault('pointer_switched')
        return self.status()

    def activate(self,operation,expected_revision):
        operation=safe_id(operation)
        with self.lock:
            if self.state['operation']==operation:return self.status()
            self._maintenance()
            if expected_revision!=self.state['revision']:raise UploadError('Replacement is stale. Current data was kept; stage the files again.',409)
            if operation in self.cancelled:raise UploadError('Upload cancelled',409)
            job=self.jobs.get(operation)
            if not job or not job.get('receipt'):raise UploadError('Upload is not ready for confirmation',409)
            receipt=job['receipt']
            if receipt['expected_revision']!=expected_revision:raise UploadError('Replacement confirmation is stale',409)
            old=self.state['active']
            if old and self._get(old)[1]['summary']['source_fingerprint']==receipt['summary']['source_fingerprint']:
                self.cancel(operation);return {**self.status(),'unchanged':True}
            folder=self.staging/operation;target=self.batches/operation
            if folder.exists():os.replace(folder,target)
            elif not target.exists():raise UploadError('Checked snapshot is no longer available',409)
            # A failed pre-pointer attempt may already have moved the complete
            # snapshot. Verify it again and allow an idempotent same-process retry.
            review,info=self._snapshot(operation)
            if info['receipt']!=receipt:raise UploadError('Checked snapshot no longer matches its confirmation',409)
            self._put_cache(operation,(review,info));self.fault('snapshot_ready')
            return self._commit(operation,old,operation)

    def rollback(self,operation,expected_revision):
        operation=safe_id(operation)
        with self.lock:
            if self.state['operation']==operation:return self.status()
            self._maintenance()
            if expected_revision!=self.state['revision']:raise UploadError('Recovery request is stale. Reload current data.',409)
            previous=self.state['previous']
            if not previous:raise UploadError('No previous uploaded batch is available',409)
            self._put_cache(previous,self._snapshot(previous))
            return self._commit(previous,self.state['active'],operation)
