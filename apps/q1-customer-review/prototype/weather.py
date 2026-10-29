"""Retrospective EHF windows, separate from the usage predictor."""
import csv
import hashlib
import json
from datetime import date,timedelta
from pathlib import Path
from .inputs import DEFAULT_SOURCE,InputError,iso,number
from .vendor.ehf.core import Source,calculate
from .vendor.ehf.adapters import silo_rows,SILO_ADAPTER

WEATHER_NAME='Fitzroy-Crossing-6765-observed-interpolated-SILO-2023-07-01_to_2025-06-30.csv'
CALIBRATION=Path(__file__).parent/'vendor/ehf/calibration-v1.json'

def load_weather(root=DEFAULT_SOURCE):
    folder=Path(root)/'Fitzroy-Crossing-6765-HISTORICAL-INPUTS'
    provenance=json.loads((folder/'PROVENANCE-AND-COVERAGE.json').read_text())
    path=folder/WEATHER_NAME; digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=provenance['weather_sha256']: raise InputError('weather: source hash mismatch')
    with path.open(newline='') as stream: rows=list(csv.DictReader(stream))
    if not rows or list(rows[0])!=provenance['weather_headers']: raise InputError('weather: source headers changed')
    seen=set()
    for row in rows:
        d=iso(row['date'],field='weather.date',required=True)
        if row['date']!=row['YYYY-MM-DD'] or d in seen: raise InputError('weather: date alias mismatch or duplicate')
        seen.add(d)
        if row['postcode']!='6765' or (float(row['latitude']),float(row['longitude']))!=(-18.2,125.55): raise InputError('weather: locality/grid mismatch')
        hi=number(row['max_temp'],field='weather.max_temp',required=True)
        lo=number(row['min_temp'],field='weather.min_temp',required=True)
        if lo>hi: raise InputError('weather: minimum exceeds maximum')
    if len(rows)!=731: raise InputError('weather: unexpected retained row count')
    return rows,{'file':str(path),'sha256':digest,'classification':'historical_interpolated_observations','grid':[-18.2,125.55],'attribution':'Queensland Government SILO and underlying Bureau of Meteorology observations','official_bom_match':False}

def derive(rows,provenance,start,end,*,weather_cutoff):
    bounded=[r for r in rows if r['date']<=weather_cutoff]
    source=Source(source_id='q1-fitzroy-historical-candidates',provider='Queensland Government SILO',dataset=WEATHER_NAME,classification='REAL_HISTORICAL_INTERPOLATED_CLIMATE',latitude=-18.2,longitude=125.55,adapter_reference_version=SILO_ADAPTER,input_sha256=provenance['sha256'])
    series=silo_rows(bounded,source)
    calibration=json.loads(CALIBRATION.read_text())
    result=calculate(series,calibration,start,end)
    return result

def event_windows(rows,provenance,review_date):
    review=date.fromisoformat(review_date); cutoff=(review-timedelta(days=1)).isoformat()
    horizon_start=(review+timedelta(days=1)).isoformat(); horizon_end=(review+timedelta(days=7)).isoformat()
    history_start=review.replace(year=review.year-2).isoformat()
    # Past classifications are bounded independently; no future observations can
    # retroactively establish a known past comparison at this review date.
    past=derive(rows,provenance,max(history_start,rows[0]['date']),cutoff,weather_cutoff=cutoff)
    replay_cutoff=(date.fromisoformat(horizon_end)+timedelta(days=3)).isoformat()
    replay=derive(rows,provenance,horizon_start,horizon_end,weather_cutoff=replay_cutoff)
    return past,replay,{'review_date':review_date,'history_cutoff':cutoff,'horizon_start':horizon_start,'horizon_end':horizon_end,'history_window_start':history_start,'history_available_start':rows[0]['date'],'replay_weather_cutoff':replay_cutoff,'hindsight_weather':True}
