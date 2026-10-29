"""Bounded frozen Namash export; independent of the ECMWF contract and updater."""
from datetime import datetime, timezone
from pathlib import Path
import copy
import hashlib
import json
import math
import re
import threading

CONTRACT='season-ahead-statistical-outlook-v1'
SOURCE='namash-ridge-lightgbm-v1'
COMMIT='e8143867c295cac0071f6e6f90ee5e0295960a95'
EXPORT_SHA='909904199eafcefcfaaa8844ae8bf7a4b53ca55326df3a2973290f294e7dc247'
MAX_BYTES=2*1024*1024
ISSUES={'2026-10':['2026-10','2026-11','2026-12','2027-01','2027-02','2027-03'], '2026-11':['2026-11','2026-12','2027-01','2027-02','2027-03','2027-04']}
MODEL='Mean of ridge and LightGBM on anomalies from per-cell climatology + linear trend'
META={
 'model':MODEL,'source':'NASA POWER MERRA-2 T2M monthly','training_through':'2026-09','rounds':78,
 'sigma_by_lead':{'1':1.297,'2':1.347,'3':1.366,'4':1.373,'5':1.373,'6':1.376},
 'bias_correction_by_lead':{'1':0.268,'2':0.308,'3':0.335,'4':0.353,'5':0.389,'6':0.373},
 'indices_carried_forward':['nino34 2026-10 = 09 value','sam 2026-10 = 09 value'],
 'partial_month':'Oct 2026 from daily T2M 1-21 Oct','resolution':'1 degree cells, centres at x.5',
 'caveat':'Experimental statistical outlook; not a Copernicus or BoM product. Monthly means only, not heatwave counts.',
 'skill':'MSE skill vs climatology per lead, ensemble, hindcast 2006-2025','generated_from':'run_forecast.py + run_backtest.py'}
PROVENANCE={
 'sourceId':SOURCE,'commit':COMMIT,'exportSha256':EXPORT_SHA,
 'baseline':{'period':'1991-2020','dataset':'NASA POWER / MERRA-2 T2M','statistic':'calendar-month mean'},
 'units':{'temperature':'degC','anomaly':'degC_difference','probability':'fraction','range':'degC','skill':'MSE skill vs climatology'},
 'probabilityEvent':'Monthly mean temperature above the matching 1991-2020 calendar-month mean',
 'probabilityStatus':'experimental; final isotonic calibration not independently held-out verified',
 'rangeDefinition':'Published model 10th–90th percentile estimate: predicted mean ±1.2816 × hindcast error standard deviation by lead; not daily extremes',
 'skillDefinition':META['skill'],
 'inputLimitations':{'2026-10':'Complete monthly temperature and index inputs through September 2026', '2026-11':'Advance issue using October 1–21 temperatures and September Niño 3.4/SAM carried forward'},
 'publicationDate':None,'issueDatePrecision':'month only',
 'attribution':'Namash / GreenSpark; NASA Langley Research Center POWER Project (MERRA-2); NOAA CPC indices',
 'codeLicense':'MIT, copyright 2026 Sploosh4; retained in data/statistical/LICENSE',
 'sourceUrl':'https://github.com/Sploosh4/greenspark-hackathon/tree/'+COMMIT+'/q3-seasonal-ml'}

class OutlookError(ValueError):pass

def need(ok,code):
 if not ok:raise OutlookError(code)
def finite(v):return type(v) in (int,float) and math.isfinite(v)
def number(v,lo,hi,missing=True):return (v is None and missing) or (finite(v) and lo<=v<=hi)
def unique_object(pairs):
 out={}
 for k,v in pairs:
  need(k not in out,'duplicate_json_key');out[k]=v
 return out

def validate_export(d):
 need(type(d) is dict and set(d)=={'meta','issues','localities','cells'},'statistical_schema')
 need(d['meta']==META,'statistical_method_metadata')
 need(type(d['issues']) is list and len(d['issues'])==2,'statistical_issues')
 for issue,(key,months) in zip(d['issues'],ISSUES.items()):
  need(type(issue) is dict and set(issue)=={'key','label','months','uses_partial_month'} and issue['key']==key and issue['label']==('Oct 2026' if key=='2026-10' else 'Nov 2026') and issue['months']==months and type(issue['uses_partial_month']) is bool and issue['uses_partial_month']==(key=='2026-11'),'statistical_month_alignment')
 cells=d['cells'];need(type(cells) is list and len(cells)==255,'statistical_cell_count');ids=set();coords=set()
 for c in cells:
  need(type(c) is dict and set(c)=={'id','lat','lon','land','skill','f'},'statistical_cell_schema')
  la,lo=c['lat'],c['lon'];need(finite(la) and finite(lo) and -35.5<=la<=-13.5 and 112.5<=lo<=129.5 and la%1==.5 and lo%1==.5,'statistical_coordinates')
  need(c['id']==f'{la:+.1f}_{lo:.1f}' and c['id'] not in ids and (la,lo) not in coords,'statistical_cell_identity');ids.add(c['id']);coords.add((la,lo))
  need(number(c['land'],0,1,False),'statistical_land_fraction')
  need(type(c['skill']) is list and len(c['skill'])==6 and all(v is None or finite(v) and v<=1 for v in c['skill']),'statistical_skill')
  need(type(c['f']) is dict and set(c['f'])==set(ISSUES),'statistical_cell_issues')
  for f in c['f'].values():
   need(type(f) is dict and set(f)=={'t','a','p','lo','hi','n'},'statistical_measures')
   for key,lo,hi in [('t',-90,65),('n',-90,65),('lo',-90,65),('hi',-90,65),('a',-30,30),('p',0,1)]:
    need(type(f[key]) is list and len(f[key])==6 and all(number(v,lo,hi) for v in f[key]),'statistical_values_'+key)
   for i in range(6):
    t,a,n,low,high=(f[k][i] for k in ['t','a','n','lo','hi'])
    need(low is None or high is None or low<=high,'statistical_interval_order')
    need(t is None or (low is None or low<=t) and (high is None or t<=high),'statistical_interval_mean')
    need(any(v is None for v in [t,a,n]) or abs(t-n-a)<=.105,'statistical_anomaly_rounding')
 need(type(d['localities']) is list and len(d['localities'])==11,'statistical_localities')
 names=set()
 for p in d['localities']:
  need(type(p) is dict and set(p)=={'name','lat','lon','cell'} and type(p['name']) is str and 0<len(p['name'])<=80 and p['name'] not in names and finite(p['lat']) and finite(p['lon']),'statistical_locality_schema');names.add(p['name'])
  need(p['cell'] in ids and p['cell']==f'{math.floor(p["lat"])+.5:+.1f}_{math.floor(p["lon"])+.5:.1f}','statistical_locality_join')
 return d

def decode(raw):
 need(type(raw) is bytes and len(raw)<=MAX_BYTES,'statistical_size')
 need(hashlib.sha256(raw).hexdigest()==EXPORT_SHA,'statistical_hash')
 try:d=json.loads(raw,object_pairs_hook=unique_object,parse_constant=lambda _:(_ for _ in ()).throw(OutlookError('statistical_nonfinite')))
 except (UnicodeError,json.JSONDecodeError):raise OutlookError('statistical_json') from None
 return validate_export(d)

def issue_status(d,now):
 current=now.strftime('%Y-%m')
 return {i['key']:{'state':'advance' if i['key']>current else 'stale' if i['months'][-1]<current else 'available','uses_partial_month':i['uses_partial_month']} for i in d['issues']}

class StatisticalOutlook:
 def __init__(self,path,clock=None):
  self.path=Path(path);self.clock=clock or (lambda:datetime.now(timezone.utc));self._good=None;self.lock=threading.RLock()
 def read(self):
  with self.lock:
   error=None
   try:
    with self.path.open('rb') as f:raw=f.read(MAX_BYTES+1)
    self._good=decode(raw)
   except (OSError,ValueError,TypeError,KeyError):error='statistical_export_unavailable_or_invalid'
   d=self._good
   return {'schema_version':1,'contract':CONTRACT,'source_id':SOURCE,'provenance':copy.deepcopy(PROVENANCE),'data':copy.deepcopy(d),'status':{'state':'stale' if error and d else 'unavailable' if error else 'ready','last_good_retained':bool(error and d),'error':error,'checked_at':self.clock().isoformat(),'issues':issue_status(d,self.clock()) if d else {}}}
