"""Read-only, SILO-only assets. Native lookup is separate from rendered PNGs."""
from collections import OrderedDict
import gzip,io,json,math,threading
from pathlib import Path
from source_adapter import SourceError,require,digest,parse,finite

METADATA_SHA='975430c8434f59930c92c0098f5a69ead4284cc134a42248f7a1486c23334ce4'
class HistoryArchive:
 def __init__(self,root):
  self.root=Path(root);self.lock=threading.RLock();self.cache=OrderedDict();self.images={}
  raw=(self.root/'metadata.json').read_bytes();require(digest(raw)==METADATA_SHA,'history_metadata_hash')
  self.metadata=parse(raw.decode());m=self.metadata;g=m.get('grid',{})
  require(m.get('schema')=='q3-silo-native-history-v2' and m.get('licence')=='CC BY 4.0' and m.get('units')=='degC' and m.get('period')==['2021-10-01','2026-09-30'],'history_source_contract')
  require(g=={'width':323,'height':431,'west':112.875,'north':-13.675,'dx':.05,'dy':-.05,'noData':None},'history_native_grid_contract')
  require(len(m.get('layers',{}))==48 and m.get('coverage',{}).get('populatedNativeCells')==91180 and m.get('quality',{}).get('sourceTminAboveTmaxCellDays')==2623,'history_coverage_contract')
  require(m.get('normal',{}).get('inputGzipSha256')=='b7a340b2f084e2a0e4ea2bd558e59e5ba752e78abbcb864a8f65c33ff0cda0a7' and m['normal'].get('sourceInversionCellDays')==585 and m['normal'].get('sourceObjects')==21916,'history_normal_contract')
 def image(self,key):
  with self.lock:
   require(key in self.metadata['layers'],'unknown_history_layer')
   if key not in self.images:
    raw=(self.root/(key+'.png')).read_bytes();require(len(raw)<2*1024*1024 and digest(raw)==self.metadata['layers'][key]['imageSha256'],'history_image_hash');self.images[key]=raw
   return self.images[key]
 def layer(self,key):
  with self.lock:
   require(key in self.metadata['layers'],'unknown_history_layer')
   if key not in self.cache:
    raw=(self.root/(key+'.json.gz')).read_bytes();require(len(raw)<8*1024*1024 and digest(raw)==self.metadata['layers'][key]['dataSha256'],'history_values_hash')
    decoded=gzip.GzipFile(fileobj=io.BytesIO(raw)).read(32*1024*1024+1);require(len(decoded)<=32*1024*1024,'history_values_size')
    d=parse(decoded.decode());require(d.get('layer')==key and d.get('units')=='degC' and d.get('statistic')=='daily_tmax_tmin_midpoint','history_layer_contract')
    fields=d['fields'];size=323*431
    expected={'tmax','tmin','midpoint','qualityFlags'}
    if key.startswith('average-'):expected|={'midpointMin','midpointMax'}
    elif key.startswith('normal-'):expected|={'midpointValidPairSensitivity','rangeFlags'}
    require(set(fields)==expected,'history_fields')
    require(all(type(a) is list and len(a)==size for a in fields.values()),'history_shape')
    require(all(v is None or finite(v) and -90<=v<=65 for k,a in fields.items() if k not in {'qualityFlags','rangeFlags'} for v in a),'history_units_values')
    require(all(type(v) is int and v>=0 for k,a in fields.items() if k in {'qualityFlags','rangeFlags'} for v in a),'history_quality_flags')
    require(all((fields['tmax'][i] is None)==(fields['tmin'][i] is None)==(fields['midpoint'][i] is None) for i in range(size)),'history_missingness')
    require(sum(v is not None for v in fields['midpoint'])==91180,'history_native_coverage')
    self.cache[key]=d
    if len(self.cache)>3:self.cache.popitem(last=False)
   self.cache.move_to_end(key);return self.cache[key]
 def cell(self,key,lon,lat):
  require(finite(lon) and finite(lat),'history_coordinate_invalid');g=self.metadata['grid']
  x=math.floor((lon-g['west'])/g['dx']);y=math.floor((lat-g['north'])/g['dy'])
  if not 0<=x<g['width'] or not 0<=y<g['height']:return {'available':False,'reason':'outside_native_coverage','layer':key}
  d=self.layer(key);i=y*g['width']+x;f=d['fields'];value=f['midpoint'][i]
  return {'available':value is not None,'reason':None if value is not None else 'no_native_land_value','layer':key,'period':d['period'],'sourceMonths':d['sourceMonths'],'statistic':'Monthly mean of daily Tmax/Tmin midpoint','units':'degC','nativeCentre':[g['west']+(x+.5)*g['dx'],g['north']+(y+.5)*g['dy']],'values':{k:a[i] for k,a in f.items()}}
