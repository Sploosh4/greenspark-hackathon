"""Read-only local inputs, validated replacement and persistent last-good bundle.

This adapter makes no source API requests and reads no credentials. The pinned v1 input contract preserves the reviewed October pack. Version2
accepts only the bounded, independently decoded ECMWF51 seasonal contract.
"""
from datetime import datetime, timezone, date
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import fcntl
from contextlib import contextmanager

FILES={'mean':'seasonal-data.json','anomaly':'anomaly-data.json','history':'historical-context.json','business':'q3-area-context.json'}
MEAN_HASH='490c6f4118e41008eed3528804265f376a72d2a0355b91d324a19fabce2a33b9'
ANOMALY_HASH='5ddc6a8adf1feaca185983895e8160b9b8e989a74fc47145ea257aee4a84d9f5'
MONTHS=['2026-10','2026-11','2026-12','2027-01','2027-02','2027-03']
MAX_BYTES=2*1024*1024

class SourceError(ValueError):
    pass

def require(test,code):
    if not test: raise SourceError(code)

def finite(v): return type(v) in (int,float) and math.isfinite(v)
def integer(v): return type(v) is int and v>=0

def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value): return hashlib.sha256(value).hexdigest()
def parse(text):
    try: return json.loads(text,parse_constant=lambda v: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError,TypeError): raise SourceError('invalid_json') from None

def grid_values(fields,key):
    require(type(fields) is list and len(fields)==6,'six_months_required')
    require([f.get('validMonth') for f in fields]==MONTHS,'valid_month_mismatch')
    for f in fields:
        rows=f.get(key)
        require(type(rows) is list and len(rows)==23,'latitude_shape')
        require(all(type(row) is list and len(row)==18 and all(v is None or finite(v) for v in row) for row in rows),'values_or_missingness_invalid')

def validate_bundle(bundle,general=False):
    require(type(bundle) is dict and set(bundle)==set(FILES),'bundle_schema')
    m,a,h,b=(bundle[k] for k in FILES)
    require(all(type(d) is dict for d in [m,a,h,b]),'source_object_required')
    if general:
        from climate_pack import validate_pair
        validate_pair(m,a)
    else:
        require(m.get('dataset')=='seasonal-monthly-single-levels' and m.get('units')=='degC' and
                m.get('centre')=='ECMWF' and m.get('system')=='51' and m.get('product')=='ensemble mean' and
                m.get('variable')=='2m temperature' and m.get('issueDate')=='2026-10-01' and m.get('gribSha256')==MEAN_HASH,'mean_source_contract')
        require(m.get('latitudes')==[-13.5-i for i in range(23)] and m.get('longitudes')==[112.5+i for i in range(18)],'native_grid_contract')
        grid_values(m.get('fields'),'valuesC')
        require(all(v is None or -90<=v<=65 for f in m['fields'] for row in f['valuesC'] for v in row),'mean_temperature_units')
        s=a.get('source',{});v=a.get('validation',{})
        require(s.get('dataset')=='seasonal-postprocessed-single-levels' and s.get('variable')=='2m_temperature_anomaly' and
                s.get('centre')=='ECMWF' and s.get('system')=='51' and s.get('product')=='ensemble_mean' and
                s.get('issueMonth')=='2026-10' and s.get('units')=='degC_difference' and s.get('rawSha256')==ANOMALY_HASH,
                'anomaly_source_contract')
        require(s.get('referencePeriod')=='1993-2016' and s.get('baselineSourceUrl','').startswith('https://confluence.ecmwf.int/') and
                v.get('preparedAdapterValidated') is True and v.get('decodedValuesVerified')==2484 and v.get('localGribSha256')==ANOMALY_HASH,
                'anomaly_provenance_contract')
        require(a.get('latitudes')==m['latitudes'] and a.get('longitudes')==m['longitudes'] and a.get('gridSpacingDegrees')==1,'anomaly_grid_mismatch')
        grid_values(a.get('fields'),'valuesAnomalyC')
        require([f.get('leadMonth') for f in a['fields']]==list(range(1,7)),'anomaly_lead_mismatch')
    points=h.get('points')
    require(h.get('baseline')=='1991–2020' and type(points) is list and len(points)==12,'history_contract')
    require(len({p.get('postcode') for p in points})==12,'history_postcodes')
    validate_business(b,points)
    for p in points:
        require(finite(p.get('lon')) and finite(p.get('lat')) and 112<=p['lon']<=130 and -36<=p['lat']<=-13,'sample_coordinate_invalid')
        require(type(p.get('sourceSha256')) is str and len(p['sourceSha256'])==64,'history_hash_missing')
        months=p.get('months',[])
        require([x.get('month') for x in months]==list(range(1,13)),'history_months_invalid')
        require(all(integer(x.get('days')) and x['days']>0 and finite(x.get('meanDailyHighC')) and finite(x.get('meanDailyLowC')) and x['meanDailyHighC']>=x['meanDailyLowC'] for x in months),'history_values_invalid')
    return bundle

def validate_business(b,points):
    require(type(b) is dict,'business_object_required')
    from geography_reference import reference_points,registry
    points=reference_points(b,points)
    if b.get('geographyRegistrySha256') is not None:require(b.get('geographySource')==registry()['source'],'business_geography_provenance')
    require(type(b) is dict and type(b.get('areas')) is list and 1<=len(b['areas'])<=len(points),'business_area_contract')
    areas=b['areas'];known={p['postcode']:p for p in points}
    require(len({a.get('postcode') for a in areas})==len(areas) and all(a.get('postcode') in known for a in areas),'area_history_join')
    try:
        start=date.fromisoformat(b['historyStart']);end=date.fromisoformat(b['historyEnd'])
        require(b['snapshotDate']==end.isoformat() and start.isoformat()==b['historyStart'] and start<=end<=datetime.now(timezone.utc).date(),'historical_snapshot_contract')
    except (ValueError,KeyError,TypeError):raise SourceError('historical_snapshot_contract') from None
    totals={'totalAccounts':'accountCount','retainedTotalAccounts':'retainedAccountCount','closedAccounts':'closedAccounts','unknownStatusAccounts':'unknownStatusAccounts','notOpenAtSnapshotAccounts':'notOpenAtSnapshotAccounts'}
    require(all(integer(b.get(k,0)) for k in totals) and integer(b.get('snapshotUsageAccounts')),'account_totals_invalid')
    require(b['totalAccounts']<=b['snapshotUsageAccounts']<=b['retainedTotalAccounts'],'snapshot_usage_count_invalid')
    require(b.get('businessClassification','').startswith('Historical synthetic') and b.get('activityRule'),'business_provenance_missing')
    require(all(type(b.get(k)) is str and len(b[k])==64 and all(c in '0123456789abcdef' for c in b[k]) for k in ['customerSourceSha256','usageSourceSha256','contextSourceSha256']),'business_source_hash_missing')
    for ar in areas:
        require(all(integer(ar.get(k,0)) for k in totals.values()) and all(integer(ar.get(k)) for k in ['prepaidAccounts','billedAccounts']),'area_counts_invalid')
        require(ar['accountCount']==ar['prepaidAccounts']+ar['billedAccounts'] and ar['retainedAccountCount']==ar['accountCount']+ar['closedAccounts']+ar['unknownStatusAccounts']+ar.get('notOpenAtSnapshotAccounts',0),'area_counts_do_not_reconcile')
        point=known[ar['postcode']]
        require(ar.get('name')==point.get('name') and ar.get('referencePoint')==[point['lon'],point['lat']],'area_reference_point_mismatch')
        income=ar.get('financialContext')
        if income is not None:
            require(type(income) is dict and finite(income.get('medianWeeklyHouseholdIncomeAUD')) and income['medianWeeklyHouseholdIncomeAUD']>=0 and
                    income.get('year')==2021 and income.get('geography')=='POA'+ar['postcode'] and
                    income.get('sourceUrl')=='https://www.abs.gov.au/census/find-census-data/quickstats/2021/POA'+ar['postcode'],'income_context_invalid')
    require(all(sum(ar.get(v,0) for ar in areas)==b.get(k,0) for k,v in totals.items()),'account_aggregation_mismatch')
    require(b.get('financialSupportUnavailableReason') in {None,'business_source_changed'},'financial_unavailable_reason')
    if 'financialSupport' in b:
        from financial_intake import validate_attachment
        require(b.get('financialSupportUnavailableReason') is None,'financial_state_conflict')
        validate_attachment(b['financialSupport'],b)
    return b

def records(manifest,raw):
    require(type(manifest) is dict and ((manifest.get('schema_version')==1 and manifest.get('bundle_version')=='q3-local-2026-10-v1') or (manifest.get('schema_version')==2 and manifest.get('bundle_version')=='q3-seasonal-v2')),'manifest_contract')
    require(set(manifest.get('files',{}))==set(FILES),'manifest_files')
    data={}
    for key,name in FILES.items():
        item=manifest['files'][key]
        require(type(item) is dict and item.get('file')==name,'manifest_path')
        require(type(raw.get(key)) is str and len(raw[key].encode())<=MAX_BYTES and digest(raw[key].encode())==item.get('sha256'),'source_hash_mismatch_'+key)
        data[key]=parse(raw[key])
    general=manifest['schema_version']==2
    validate_bundle(data,general=general)
    if general:
        from climate_pack import validate_pair
        require(manifest.get('climate')==validate_pair(data['mean'],data['anomaly']),'climate_manifest_provenance_mismatch')
    return data,digest(canonical(manifest))

class SnapshotStore:
    def __init__(self,inputs,runtime,clock=None):
        self.inputs=Path(inputs);self.runtime=Path(runtime);self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.lock=threading.RLock();self.good=None;self.cache_error=False;self._disk_depth=0;self._cache_sig=None
        try:
            cache=self._read_json(self.runtime/'last-good.json')
            data,generation=records(cache['manifest'],cache['inputs'])
            datetime.fromisoformat(cache['validated_at'])
            require(generation==cache['generation'],'cache_generation')
            self.good={**cache,'data':data}
        except FileNotFoundError:pass
        except (OSError,ValueError,KeyError,TypeError,AttributeError):self.cache_error=True

    @contextmanager
    def _disk_lock(self):
        """Re-entrant process lock for the server and one-shot local refresh tool."""
        if self._disk_depth:
            self._disk_depth+=1
            try:yield
            finally:self._disk_depth-=1
            return
        self.runtime.mkdir(parents=True,exist_ok=True)
        with (self.runtime/'.snapshot.lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);self._disk_depth=1
            try:yield
            finally:self._disk_depth=0;fcntl.flock(lock,fcntl.LOCK_UN)

    def _sync_persisted(self):
        path=self.runtime/'last-good.json'
        try:
            stat=path.stat();sig=(stat.st_ino,stat.st_mtime_ns,stat.st_size)
            if sig==self._cache_sig:return
            cache=self._read_json(path);data,generation=records(cache['manifest'],cache['inputs'])
            datetime.fromisoformat(cache['validated_at']);require(generation==cache['generation'],'cache_generation')
            failure=cache.get('climate_refresh_failure')
            if failure:
                from climate_pack import issue_date
                issue_date(failure['issueMonth']);require(failure['code'] in {'climate_source_incomplete','climate_source_invalid','climate_decode_failed','climate_storage_failed'},'cache_refresh_status')
            self.good={**cache,'data':data};self._cache_sig=sig;self.cache_error=False
        except FileNotFoundError:
            if self.good is not None:self.cache_error=True
        except (OSError,ValueError,KeyError,TypeError,AttributeError):self.cache_error=True

    def _read_text(self,path):
        with path.open('rb') as f: raw=f.read(MAX_BYTES+1)
        require(len(raw)<=MAX_BYTES,'source_too_large')
        try:return raw.decode('utf-8')
        except UnicodeError:raise SourceError('invalid_encoding') from None

    def _read_json(self,path):return parse(self._read_text(path))

    def _candidate(self):
        manifest_text=self._read_text(self.inputs/'manifest.json');manifest=parse(manifest_text)
        require(not self.cache_error,'persisted_snapshot_invalid_recovery_required')
        raw={key:self._read_text(self.inputs/name) for key,name in FILES.items()}
        override=bool(self.good and self.good.get('business_override'))
        if override:
            raw['business']=self.good['inputs']['business']
            manifest['files']['business']['sha256']=digest(raw['business'].encode())
            manifest['provenance']['business_snapshot']=self.good['data']['business']['snapshotDate']
            for key in ['business_upload','financial_support_upload','financial_support_invalidated']:
                if key in self.good['manifest']['provenance']:manifest['provenance'][key]=copy.deepcopy(self.good['manifest']['provenance'][key])
        climate_override=bool(self.good and (self.good.get('climate_override') or self.good['manifest']['schema_version']==2))
        if climate_override:
            for key in ['mean','anomaly']:
                raw[key]=self.good['inputs'][key]
                manifest['files'][key]=copy.deepcopy(self.good['manifest']['files'][key])
            manifest.update({key:copy.deepcopy(self.good['manifest'][key]) for key in ['schema_version','bundle_version','climate']})
            for key in ['mean_grib_sha256','anomaly_grib_sha256','climate_refresh']:
                manifest['provenance'][key]=copy.deepcopy(self.good['manifest']['provenance'][key])
        data,generation=records(manifest,raw)
        require(self._read_text(self.inputs/'manifest.json')==manifest_text,'inputs_changed_during_read')
        return {'manifest':manifest,'inputs':raw,'data':data,'generation':generation,'validated_at':self.clock().isoformat(),'business_override':override,'climate_override':climate_override}

    def _persist(self,candidate):
        self.runtime.mkdir(parents=True,exist_ok=True)
        payload={k:v for k,v in candidate.items() if k!='data'}
        fd,name=tempfile.mkstemp(prefix='.candidate-',dir=self.runtime)
        try:
            with os.fdopen(fd,'wb') as out:out.write(canonical(payload));out.flush();os.fsync(out.fileno())
            os.replace(name,self.runtime/'last-good.json')
            try:
                stat=(self.runtime/'last-good.json').stat();self._cache_sig=(stat.st_ino,stat.st_mtime_ns,stat.st_size)
            except OSError:self._cache_sig=None # Rename committed a validated pack; a stat failure must not report an old-data rollback.
        finally:
            try:os.unlink(name)
            except FileNotFoundError:pass

    def replace_business(self,business,expected_generation):
        with self.lock,self._disk_lock():
            packet=self.read()
            require(packet['data'] is not None and not packet['status']['last_refresh_error'],'current_source_unavailable')
            require(packet['generation']==expected_generation,'active_snapshot_changed_restage_required')
            candidate=copy.deepcopy(self.good)
            business=copy.deepcopy(business);business.pop('financialSupport',None);business.pop('financialSupportUnavailableReason',None)
            previous_support=candidate['data']['business'].get('financialSupport')
            if previous_support:
                from financial_intake import validate_attachment
                try:validate_attachment(previous_support,business)
                except SourceError:
                    business['financialSupportUnavailableReason']='business_source_changed'
                    candidate['manifest']['provenance'].pop('financial_support_upload',None)
                    candidate['manifest']['provenance']['financial_support_invalidated']={'at':self.clock().isoformat(),'reason':'business_source_changed'}
                else:business['financialSupport']=copy.deepcopy(previous_support)
            validate_business(business,candidate['data']['history']['points'])
            candidate['inputs']['business']=canonical(business).decode()
            manifest=candidate['manifest'];manifest['files']['business']['sha256']=digest(candidate['inputs']['business'].encode())
            manifest['provenance']['business_snapshot']=business['snapshotDate']
            manifest['provenance']['business_upload']={'replaced_at':self.clock().isoformat(),'customer_sha256':business['customerSourceSha256'],'usage_sha256':business['usageSourceSha256'],'raw_rows_persisted':False}
            candidate['data'],candidate['generation']=records(manifest,candidate['inputs'])
            candidate['validated_at']=self.clock().isoformat();candidate['business_override']=True
            self._persist(candidate) # No in-memory promotion until fsync + atomic replace succeeds.
            self.good=candidate
            return self.read()

    def replace_financial_support(self,support,expected_generation):
        """Explicit aggregate attachment; no raw financial/account rows are saved."""
        from financial_intake import validate_attachment
        with self.lock,self._disk_lock():
            packet=self.read()
            require(packet['data'] is not None and not packet['status']['last_refresh_error'],'current_source_unavailable')
            require(packet['generation']==expected_generation,'active_snapshot_changed_restage_required')
            candidate=copy.deepcopy(self.good);business=candidate['data']['business']
            validate_attachment(support,business)
            business['financialSupport']=copy.deepcopy(support);business.pop('financialSupportUnavailableReason',None)
            candidate['inputs']['business']=canonical(business).decode()
            require(len(candidate['inputs']['business'].encode())<=MAX_BYTES,'financial_aggregate_size_limit')
            manifest=candidate['manifest'];manifest['files']['business']['sha256']=digest(candidate['inputs']['business'].encode())
            manifest['provenance']['financial_support_upload']={'replaced_at':self.clock().isoformat(),'snapshot_date':support['snapshotDate'],'reviewed_manifest_sha256':support['reviewedManifestSha256'],'aggregate_sha256':digest(canonical(support)),'coverage_areas':len(support['areas']),'raw_rows_persisted':False}
            manifest['provenance'].pop('financial_support_invalidated',None)
            candidate['data'],candidate['generation']=records(manifest,candidate['inputs']);candidate['business_override']=True;candidate['validated_at']=self.clock().isoformat()
            self._persist(candidate);self.good=candidate
            return self.read()

    def promote_climate(self,pair,expected_generation):
        """Atomic pair replacement. Business/history remain their dated snapshots."""
        from climate_pack import validate_pair,issue_date
        receipt=validate_pair(pair.get('mean'),pair.get('anomaly'))
        with self.lock,self._disk_lock():
            packet=self.read()
            require(packet['data'] is not None and not packet['status']['last_refresh_error'],'current_source_unavailable')
            require(packet['generation']==expected_generation,'active_snapshot_changed_restage_required')
            require(receipt['issueMonth']>packet['data']['mean']['issueDate'][:7],'candidate_not_newer')
            require(issue_date(receipt['issueMonth'])<=self.clock().date(),'candidate_issue_in_future')
            candidate=copy.deepcopy(self.good)
            for key in ['mean','anomaly']:
                candidate['inputs'][key]=canonical(pair[key]).decode()
                candidate['manifest']['files'][key]={'file':FILES[key],'sha256':digest(candidate['inputs'][key].encode())}
            manifest=candidate['manifest'];manifest.update(schema_version=2,bundle_version='q3-seasonal-v2',climate=receipt)
            manifest['provenance'].update(mean_grib_sha256=receipt['meanRawSha256'],anomaly_grib_sha256=receipt['anomalyRawSha256'],climate_refresh={'issueMonth':receipt['issueMonth'],'validatedAt':self.clock().isoformat(),'decoderContract':'q3-seasonal-v2','retrievalPerformedHere':False})
            candidate['data'],candidate['generation']=records(manifest,candidate['inputs'])
            candidate['climate_override']=True;candidate['validated_at']=self.clock().isoformat();candidate.pop('climate_refresh_failure',None)
            self._persist(candidate)
            self.good=candidate
            return self.read()

    def record_climate_failure(self,issue,code):
        """Persist a bounded public error without replacing the validated pair."""
        from climate_pack import issue_date
        issue_date(issue)
        require(code in {'climate_source_incomplete','climate_source_invalid','climate_decode_failed','climate_storage_failed'},'unapproved_refresh_error_code')
        with self.lock,self._disk_lock():
            packet=self.read();require(self.good is not None,'current_source_unavailable')
            if issue<=packet['data']['mean']['issueDate'][:7]:
                return {**packet,'refreshFailureRecorded':False}
            candidate=copy.deepcopy(self.good)
            candidate['climate_refresh_failure']={'issueMonth':issue,'code':code,'checkedAt':self.clock().isoformat()}
            self._persist(candidate);self.good=candidate
            return {**self.read(),'refreshFailureRecorded':True}

    def read(self):
        with self.lock:
            error=None
            if not self.runtime.exists():
                try:self._candidate()
                except SourceError as exc:error=str(exc)
                except (OSError,ValueError,KeyError,TypeError,AttributeError):error='input_or_storage_unavailable'
            if error is None:
                try:
                    with self._disk_lock():
                        self._sync_persisted()
                        candidate=self._candidate()
                        if self.good is None or candidate['generation']!=self.good['generation']:
                            self._persist(candidate);self.good=candidate
                except SourceError as exc:error=str(exc)
                except (OSError,ValueError,KeyError,TypeError,AttributeError):error='input_or_storage_unavailable'
            now=self.clock();good=self.good
            issue=good['data']['mean']['issueDate'] if good else None
            earlier=bool(issue and now.strftime('%Y-%m')>issue[:7])
            climate_error=good.get('climate_refresh_failure') if good else None
            status={'state':'unavailable' if not good else 'stale' if error or climate_error or earlier else 'ready',
                    'checked_at':now.isoformat(),'validated_at':good['validated_at'] if good else None,
                    'last_refresh_error':error,'last_good_retained':bool(good and (error or climate_error)),'climate_refresh_error':climate_error['code'] if climate_error else None,'climate_refresh_failed_issue':climate_error['issueMonth'] if climate_error else None,
                    'climate_issue_date':issue,'earlier_forecast_issue':earlier,
                    'business_snapshot_date':good['data']['business']['snapshotDate'] if good else None,
                    'freshness_policy':'Earlier forecast issue after its issue month; failed refresh retains a labelled last-good bundle. Historical baselines/snapshots keep their own dates.'}
            return {'schema_version':1,'generation':good['generation'] if good else None,'status':status,
                    'provenance':good['manifest']['provenance'] if good else None,'data':good['data'] if good else None}
