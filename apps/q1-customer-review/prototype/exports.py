"""CSV from the same immutable review snapshot used by table and PDF."""
import csv
from io import StringIO
from math import isfinite
from .uploads import UploadError
MAX_CSV_CUSTOMERS=50000
MAX_CSV_BYTES=64*1024*1024

def selected_rows(review,ids,limit=100):
    if not isinstance(ids,list) or not 1<=len(ids)<=limit or any(not isinstance(x,str) or not 1<=len(x)<=128 for x in ids):raise UploadError(f'Select between 1 and {limit} customer references of at most128characters')
    mapping={r['customer']['customer_id']:r for r in review['customers']}
    if any(x not in mapping for x in ids):raise UploadError('Selected customer is unavailable in this data version',409)
    return [mapping[x] for x in dict.fromkeys(ids)]

def iter_csv_chunks(review,ids):
    rows=selected_rows(review,ids,limit=MAX_CSV_CUSTOMERS);out=StringIO(newline='');writer=csv.writer(out,lineterminator='\r\n')
    yield b'\xef\xbb\xbf'
    head=['customer_id','account_type','locality','event_id','event_start','event_end','event_days','expected_increase_percent','baseline_daily_import_kwh','estimated_daily_import_kwh','past_comparison_percent','method_id','batch_revision','batch_id','data_mode','provenance']
    if review.get('replay') or review.get('current_demo'):head+=['estimated_event_import_kwh','S1_daily_import_kwh','S1_increase_percent','past_event_id','past_observed_daily_import_kwh','past_baseline_daily_import_kwh','percentage_policy','model_manifest_sha256','snapshot_id','availability_mode']
    if review.get('current_demo'):head+=['application_received_at','inference_as_of','latest_reported_usage_date','reporting_lag_days','weather_retrieved_at','provider_issue_at','weather_snapshot_sha256','estimator_lane']
    writer.writerow(head)
    def safe(v):
        if isinstance(v,(int,float)):return v
        text='' if v is None else str(v)
        return "'"+text if text[:1] in ('=','+','-','@','\t','\r') else text
    provenance='synthetic performance fixture; authored estimates; no prediction-quality claim' if review.get('performance_fixture') else 'calculated historical replay; synthetic business; unvalidated estimate'
    if review.get('replay') or review.get('current_demo'):provenance='simulated historical replay; synthetic accounts; frozen M5 with S1 comparison; historical oracle weather; original availability unknown'
    if review.get('current_demo'):provenance='current-date synthetic demo; frozen M5/S1; external modelled weather; current accuracy unvalidated'
    for row in rows:
        c=row['customer'];predictions={p['event_id']:p for p in row['predictions']}
        values=[e['increase_percent'] for e in row['episodes'] if e.get('linked') and e['start']>=review['history_window_start'] and e['end']<=review['history_cutoff'] and e.get('increase_percent') is not None and isfinite(e['increase_percent'])]
        threshold=min(values) if values else None
        past=next((episode for episode in row['episodes'] if episode.get('linked') and episode.get('increase_percent')==threshold),{}) if threshold is not None else {}
        for e in review['events']:
            p=predictions.get(e['id'],{})
            cells=[c['customer_id'],'Prepaid' if c['prepayment_meter']=='True' else 'Billed',c['locality'],e['id'],e['start'],e['end'],p.get('duration'),p.get('increase'),p.get('baseline'),p.get('predicted'),threshold,p.get('method_id'),review['batch_revision'],review['batch_id'],review['data_mode'],provenance]
            if review.get('replay') or review.get('current_demo'):
                meta=review.get('current_demo') or review['replay'];comparison=p.get('comparison',{})
                cells += [p.get('event_total'),comparison.get('predicted'),comparison.get('increase'),past.get('id'),past.get('actual_mean'),past.get('denominator'),meta['denominator_policy'],meta['model_manifest_sha256'],review['snapshot_id'],meta['mode']]
            if review.get('current_demo'):
                meta=review['current_demo'];cells += [meta['business_received_at'],meta['inference_as_of'],row.get('latest_reported_usage_date'),row.get('reporting_lag_days'),meta.get('weather_retrieved_at'),meta.get('provider_issue_at'),meta.get('weather_snapshot_sha256'),meta['estimator_lane']]
            writer.writerow(map(safe,cells))
            if out.tell()>=65536:yield out.getvalue().encode('utf-8');out.seek(0);out.truncate(0)
    if out.tell():yield out.getvalue().encode('utf-8')

def csv_bytes(review,ids):
    result=bytearray()
    for chunk in iter_csv_chunks(review,ids):
        if len(result)+len(chunk)>MAX_CSV_BYTES:raise UploadError('CSV exceeds its64MiBoutput limit',413)
        result.extend(chunk)
    return bytes(result)
