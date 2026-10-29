"""Retrospective temperature chart context, separate from inference weather."""
from functools import lru_cache
from pathlib import Path
import copy,hashlib,json

DATA=Path(__file__).with_name('data')/'silo-6765-history.json'
EXPECTED='aa37fb09627b5ec31d3447d75a8f957da7c90d735751e72e6447619773167a45'

@lru_cache(maxsize=1)
def archive():
    raw=DATA.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('Historical weather context fingerprint differs')
    return json.loads(raw)

def attach_history(review):
    if not review.get('current_demo'):return review
    try:data=archive()
    except (OSError,ValueError):
        review['timeline_weather']=[];review['timeline_weather_context']={'status':'unavailable','reason':'The retained historical weather could not be verified.'};return review
    start,end=review['history_available_start'],review['history_cutoff']
    rows=[copy.copy(r) for r in data['rows'] if start<=r['date']<=end]
    review['timeline_weather']=rows
    review['timeline_weather_context']={'status':'available','version':data['version'],'sha256':EXPECTED,'source':data['source'],'licence':data['licence'],'source_url':'https://www.longpaddock.qld.gov.au/silo/','date_convention':'Original SILO nominal dates, no date shift','original_available_at':None,'scope':'Retrospective chart only; excluded from prediction inputs','latitude':data['latitude'],'longitude':data['longitude']}
    return review
