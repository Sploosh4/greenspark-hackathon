"""Deterministic, offline ECMWF51 monthly mean/anomaly decoder and contract.

No credential access or retrieval. ecCodes is imported only by decode_grib.
The accepted grid/model are deliberately bounded; schema drift fails closed.
"""
from datetime import date
from pathlib import Path
import hashlib,math,re
from tempfile import TemporaryFile
from source_adapter import SourceError,require,finite,canonical,digest

BASELINE_URL='https://confluence.ecmwf.int/spaces/CKB/pages/340775655/C3S+seasonal+forecast+product+descriptions'
LATS=[-13.5-i for i in range(23)];LONS=[112.5+i for i in range(18)]
MAX_GRIB=8*1024*1024
KEYS='edition centre systemNumber dataDate dataTime shortName paramId units typeOfLevel level dataType marsStream forecastMonth verifyingMonth validityDate validityTime gridType Ni Nj numberOfDataPoints numberOfMissing iDirectionIncrementInDegrees jDirectionIncrementInDegrees'.split()

def issue_date(issue):
    require(type(issue) is str and re.fullmatch(r'\d{4}-\d{2}',issue),'invalid_issue_month')
    try:return date.fromisoformat(issue+'-01')
    except ValueError:raise SourceError('invalid_issue_month') from None

def month_at(issue,offset):
    d=issue_date(issue);m=d.year*12+d.month-1+offset
    return f'{m//12:04d}-{m%12+1:02d}'

def months(issue):return [month_at(issue,i) for i in range(6)]
def valid_hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None

def metadata_contract(info,kind,issue,lead):
    require(type(info) is dict,'grib_metadata_required')
    expected={'centre':'ecmf','systemNumber':51,'dataDate':int(issue.replace('-','')+'01'),'dataTime':0,'shortName':'2t' if kind=='mean' else '2ta','paramId':167 if kind=='mean' else 171167,'units':'K','typeOfLevel':'surface','level':0,'dataType':'em','marsStream':'msmm' if kind=='mean' else 'mmsa','forecastMonth':lead,'verifyingMonth':int(month_at(issue,lead-1).replace('-','')),'validityDate':int(month_at(issue,lead).replace('-','')+'01'),'validityTime':0,'gridType':'regular_ll','Ni':18,'Nj':23,'numberOfDataPoints':414,'iDirectionIncrementInDegrees':1,'jDirectionIncrementInDegrees':1}
    require(info.get('edition') in (1,2),'grib_edition')
    require(all(info.get(k)==v for k,v in expected.items()),'grib_model_units_dates_or_grid_mismatch')
    require(type(info.get('numberOfMissing')) is int and 0<=info['numberOfMissing']<=414,'grib_missingness_metadata')

def decode_messages(messages,kind,issue,raw_hash):
    """Pure entry point used by fixture tests; each message includes coordinates.

    Fixtures are synthetic decoder tests only and are never served as forecasts.
    """
    issue_date(issue);require(kind in {'mean','anomaly'} and valid_hash(raw_hash),'decoder_request_contract')
    require(type(messages) is list and len(messages)==6,'six_complete_grib_messages_required')
    fields=[]
    for i,message in enumerate(messages):
        require(type(message) is dict,'grib_message_object')
        info=message.get('metadata');metadata_contract(info,kind,issue,i+1)
        require(message.get('latitudes')==LATS and message.get('longitudes')==LONS,'grib_coordinate_mismatch')
        values=message.get('valuesK');require(type(values) is list and len(values)==414,'grib_values_shape')
        require(all(x is None or finite(x) for x in values),'grib_nonfinite_values')
        require(sum(x is None for x in values)==info['numberOfMissing'],'grib_missingness_disagrees')
        converted=[None if x is None else x-273.15 if kind=='mean' else x for x in values]
        require(all(x is None or (-90<=x<=65 if kind=='mean' else -50<=x<=50) for x in converted),'grib_value_units_sanity')
        field={'leadMonth':i+1,'validMonth':month_at(issue,i),'gribValidityDate':info['validityDate'],'gribMetadata':info.copy()}
        field['valuesC' if kind=='mean' else 'valuesAnomalyC']=[converted[y*18:(y+1)*18] for y in range(23)]
        fields.append(field)
    common={'latitudes':LATS.copy(),'longitudes':LONS.copy(),'gridSpacingDegrees':1,'fields':fields}
    if kind=='mean':return {**common,'dataset':'seasonal-monthly-single-levels','units':'degC','centre':'ECMWF','system':'51','product':'ensemble mean','variable':'2m temperature','issueDate':issue+'-01','gribSha256':raw_hash,'conversion':'Decoded kelvin minus273.15; native values retained without display rounding.'}
    return {**common,'source':{'dataset':'seasonal-postprocessed-single-levels','datasetUrl':'https://cds.climate.copernicus.eu/datasets/seasonal-postprocessed-single-levels','doi':'10.24381/cds.7e37c951','centre':'ECMWF','system':'51','issueMonth':issue,'variable':'2m_temperature_anomaly','product':'ensemble_mean','sourceUnits':'K','units':'degC_difference','rawSha256':raw_hash,'referencePeriod':'1993-2016','baselineSourceUrl':BASELINE_URL,'baselineProvenance':'Matching-model hindcast mean; documentation provenance, not independently recomputed.','conversion':'Identity for kelvin anomaly to Celsius difference; no offset.'},'validation':{'preparedAdapterValidated':True,'decodedValuesVerified':2484,'localGribSha256':raw_hash}}

def decode_grib(path,kind,issue,expected_sha256,ec=None):
    issue_date(issue);require(kind in {'mean','anomaly'},'decoder_request_contract')
    path=Path(path);require(valid_hash(expected_sha256),'raw_hash_required')
    with path.open('rb') as f:raw=f.read(MAX_GRIB+1)
    require(0<len(raw)<=MAX_GRIB and digest(raw)==expected_sha256,'raw_grib_hash_or_size_mismatch')
    require(raw.startswith(b'GRIB') and raw.endswith(b'7777'),'incomplete_grib_file')
    if ec is None:
        try:import eccodes as ec
        except ImportError:raise SourceError('eccodes_decoder_dependency_unavailable') from None
    messages=[];encoded=[]
    # Decode only the bounded bytes already checked above. A private unnamed
    # file preserves the ecCodes FILE interface without reopening the inbox.
    with TemporaryFile('w+b') as f:
        f.write(raw);f.seek(0)
        while True:
            try:handle=ec.codes_grib_new_from_file(f)
            except Exception:raise SourceError('grib_decode_failed') from None
            if handle is None:break
            try:
                require(len(messages)<6,'six_complete_grib_messages_required')
                info={k:ec.codes_get(handle,k) for k in KEYS}
                metadata_contract(info,kind,issue,len(messages)+1)
                encoded.append(ec.codes_get_message(handle))
                values=[float(x) for x in ec.codes_get_values(handle)];lat=list(ec.codes_get_array(handle,'latitudes'));lon=list(ec.codes_get_array(handle,'longitudes'))
                require(len(values)==len(lat)==len(lon)==414,'grib_coordinate_shape')
                require(lat==[y for y in LATS for _ in LONS] and lon==LONS*len(LATS),'grib_scan_order_or_grid_mismatch')
                if info['numberOfMissing']:
                    require(ec.codes_get(handle,'bitmapPresent')==1,'missing_grid_bitmap_required')
                    bitmap=list(ec.codes_get_array(handle,'bitmap'));require(len(bitmap)==414 and all(x in (0,1) for x in bitmap),'invalid_missing_grid_bitmap')
                    values=[v if bitmap[i] else None for i,v in enumerate(values)]
                messages.append({'metadata':info,'latitudes':LATS.copy(),'longitudes':LONS.copy(),'valuesK':values})
            except SourceError:raise
            except Exception:raise SourceError('grib_decode_failed') from None
            finally:ec.codes_release(handle)
    # Reject leading/trailing garbage and bytes skipped by a permissive decoder.
    require(b''.join(encoded)==raw,'grib_unparsed_or_changed_bytes')
    return decode_messages(messages,kind,issue,expected_sha256)

def validate_pair(mean,anomaly):
    require(type(mean) is dict and type(anomaly) is dict,'climate_pair_required')
    issue=mean.get('issueDate','')[:7];require(mean.get('issueDate')==issue+'-01','issue_first_day_required');issue_date(issue)
    require(mean.get('dataset')=='seasonal-monthly-single-levels' and mean.get('units')=='degC' and mean.get('centre')=='ECMWF' and mean.get('system')=='51' and mean.get('product')=='ensemble mean' and mean.get('variable')=='2m temperature' and valid_hash(mean.get('gribSha256')),'mean_source_contract')
    s=anomaly.get('source',{});v=anomaly.get('validation',{})
    require(s.get('dataset')=='seasonal-postprocessed-single-levels' and s.get('variable')=='2m_temperature_anomaly' and s.get('product')=='ensemble_mean' and s.get('centre')=='ECMWF' and s.get('system')=='51' and s.get('issueMonth')==issue and s.get('units')=='degC_difference' and s.get('sourceUnits')=='K' and s.get('referencePeriod')=='1993-2016' and s.get('baselineSourceUrl')==BASELINE_URL and valid_hash(s.get('rawSha256')),'anomaly_source_contract')
    require(v.get('preparedAdapterValidated') is True and v.get('decodedValuesVerified')==2484 and v.get('localGribSha256')==s['rawSha256'],'anomaly_provenance_contract')
    for kind,data,key in [('mean',mean,'valuesC'),('anomaly',anomaly,'valuesAnomalyC')]:
        require(data.get('latitudes')==LATS and data.get('longitudes')==LONS and data.get('gridSpacingDegrees')==1,'native_grid_contract')
        fields=data.get('fields');require(type(fields) is list and len(fields)==6,'six_months_required')
        for i,f in enumerate(fields):
            require(type(f) is dict and f.get('leadMonth')==i+1 and f.get('validMonth')==month_at(issue,i) and f.get('gribValidityDate')==int(month_at(issue,i+1).replace('-','')+'01'),'verifying_month_mismatch')
            metadata_contract(f.get('gribMetadata'),kind,issue,i+1)
            rows=f.get(key);require(type(rows) is list and len(rows)==23 and all(type(r) is list and len(r)==18 for r in rows),'values_shape')
            flat=[x for row in rows for x in row]
            require(all(x is None or finite(x) and (-90<=x<=65 if kind=='mean' else -50<=x<=50) for x in flat),'values_or_units_invalid')
            require(sum(x is None for x in flat)==f['gribMetadata']['numberOfMissing'],'missingness_disagrees')
    return {'issueMonth':issue,'meanRawSha256':mean['gribSha256'],'anomalyRawSha256':s['rawSha256'],'validMonths':months(issue),'model':'ECMWF51','contract':'q3-seasonal-v2'}

def decode_pair(mean_path,anomaly_path,issue,mean_hash,anomaly_hash,ec=None):
    mean=decode_grib(mean_path,'mean',issue,mean_hash,ec);anomaly=decode_grib(anomaly_path,'anomaly',issue,anomaly_hash,ec)
    return {'mean':mean,'anomaly':anomaly,'receipt':validate_pair(mean,anomaly)}
