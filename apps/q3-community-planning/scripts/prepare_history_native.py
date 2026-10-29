"""Build SILO-only native-value lookup and nearest-cell purple PNG assets.

Run once using the existing data worker's rasterio/numpy environment. Runtime
serving uses only Python's standard library. No downloads or BoM numeric export.
"""
import argparse,calendar,gzip,hashlib,json,struct,zlib
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import transform_bounds,reproject,Resampling,transform_geom
from rasterio.transform import from_bounds
from rasterio.features import rasterize

EXPECTED='aeb06e0ac349ecfc84c08081702375e29bef7c0e0a6c1e8ee3edf30f5a7015b5'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return json.dumps(value,separators=(',',':'),allow_nan=False).encode()
def png(rgba):
 h,w,_=rgba.shape
 def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 raw=b''.join(b'\0'+rgba[row].tobytes() for row in range(h))
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,6))+chunk(b'IEND',b'')
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);args=p.parse_args();r=args.source;out=args.output;out.mkdir(parents=True,exist_ok=True)
 provenance=json.loads((r/'provenance.json').read_text());hashes={a['path']:a['sha256'] for a in provenance['all_files']}
 assert sha((r/'derived/q3-wa-temperature-overlay.json.gz').read_bytes())==EXPECTED
 def verified(name):
  raw=(r/name).read_bytes();assert sha(raw)==hashes[name],name;return raw
 mask=json.loads(verified('derived/wa-display-mask.geojson'))
 quality=json.loads(verified('derived/source-tmin-above-tmax.json'))
 layers={};all_data={};all_flags={};src_transform=None
 for year in range(2021,2027):
  for month in range(1,13):
   ym=f'{year}-{month:02d}'
   if not '2021-10'<=ym<='2026-09':continue
   name=f'derived/monthly/wa-silo-{ym}.tif';verified(name)
   with rasterio.open(r/name) as s:
    assert s.shape==(431,323) and s.count==3 and s.crs.to_epsg()==4326 and s.nodata==-32767
    a=s.read().astype('float64');a[a==s.nodata]=np.nan
    assert np.isfinite(a[2]).sum()==91180
    all_data[ym]=a;src_transform=s.transform;bounds=s.bounds
   flags=np.zeros((431,323),dtype='int32')
   for flag in quality['records']:
    if flag['date'].startswith(ym):flags[flag['row'],flag['column']]+=1
   all_flags[ym]=flags
 assert sum(int(f.sum()) for f in all_flags.values())==2623
 west,south,east,north=bounds;mb=transform_bounds('EPSG:4326','EPSG:3857',*bounds)
 height=900;width=round(height*(mb[2]-mb[0])/(mb[3]-mb[1]));dest_transform=from_bounds(*mb,width,height)
 geometries=[transform_geom('EPSG:4326','EPSG:3857',f['geometry']) for f in mask['features']]
 land=rasterize(((g,1) for g in geometries),out_shape=(height,width),transform=dest_transform,fill=0).astype(bool)
 def write(key,a,flags,period,months,minimum=None,maximum=None):
  fields={}
  for name,values in zip(['tmax','tmin','midpoint'],a):
   fields[name]=[float(v) if np.isfinite(v) else None for v in values.ravel()]
  fields['qualityFlags']=flags.ravel().tolist()
  if minimum is not None:
   fields['midpointMin']=[float(v) if np.isfinite(v) else None for v in minimum.ravel()];fields['midpointMax']=[float(v) if np.isfinite(v) else None for v in maximum.ravel()]
  payload={'layer':key,'period':period,'sourceMonths':months,'statistic':'daily_tmax_tmin_midpoint','units':'degC','fields':fields}
  data=gzip.compress(encode(payload),mtime=0);(out/(key+'.json.gz')).write_bytes(data)
  projected=np.full((height,width),np.nan,dtype='float32')
  reproject(a[2].astype('float32'),projected,src_transform=src_transform,src_crs='EPSG:4326',dst_transform=dest_transform,dst_crs='EPSG:3857',src_nodata=np.nan,dst_nodata=np.nan,resampling=Resampling.nearest)
  v=np.clip((np.nan_to_num(projected,nan=8)-8)/28,0,1)
  low=np.array([238,230,248]);high=np.array([85,33,117]);rgba=np.zeros((height,width,4),dtype='uint8');rgba[:,:,:3]=(low[None,None,:]*(1-v[:,:,None])+high[None,None,:]*v[:,:,None]).astype('uint8');rgba[:,:,3]=np.where(np.isfinite(projected)&land,255,0)
  image=png(rgba);(out/(key+'.png')).write_bytes(image)
  layers[key]={'period':period,'sourceMonths':months,'dataSha256':sha(data),'imageSha256':sha(image),'qualityFlaggedCellDays':int(flags.sum()),'validNativeCells':int(np.isfinite(a[2]).sum())}
 for ym,a in all_data.items():
  if ym>='2024-10':write(ym,a,all_flags[ym],ym,[ym])
 for month in range(1,13):
  keys=[k for k in all_data if int(k[-2:])==month];stack=np.stack([all_data[k] for k in keys]);valid=np.isfinite(stack).all(axis=0)
  a=np.where(valid,np.nan_to_num(stack).sum(axis=0)/5,np.nan)
  d=stack[:,2];minimum=np.where(valid[2],np.nan_to_num(d,nan=np.inf).min(axis=0),np.nan);maximum=np.where(valid[2],np.nan_to_num(d,nan=-np.inf).max(axis=0),np.nan)
  write(f'average-{month:02d}',a,sum(all_flags[k] for k in keys),f'{calendar.month_name[month]} monthly average · Oct 2021–Sep 2026',keys,minimum,maximum)
 metadata={'schema':'q3-silo-native-history-v1','source':'Queensland Government SILO; underlying Bureau of Meteorology and other observation providers','sourceUrl':'https://www.longpaddock.qld.gov.au/silo/','licence':'CC BY 4.0','maskSource':'ABS ASGS2021 state boundary, WA, CC BY 4.0','inputBundleSha256':EXPECTED,'period':['2021-10-01','2026-09-30'],'recentPeriod':['2024-10-01','2026-09-30'],'units':'degC','statistic':'Monthly mean of daily Tmax/Tmin midpoint','sourceClassification':'spatially interpolated observations','grid':{'width':323,'height':431,'west':west,'north':north,'dx':0.05,'dy':-0.05,'noData':None},'image':{'width':width,'height':height,'crs':'EPSG:3857','resampling':'nearest native cell; clipped to genuine ABS WA display boundary','coordinates':[[west,north],[east,north],[east,south],[west,south]]},'coverage':{'waNativeCellCentres':91198,'populatedNativeCells':91180,'missingCoastalIslandCells':18},'quality':{'sourceTminAboveTmaxCellDays':2623,'policy':quality['policy']},'scale':{'minC':8,'maxC':36,'colours':['#eee6f8','#552175']},'layers':layers,'excluded':'No BoM numeric climatology is included. No infilling. Five-year range describes five monthly means, not daily extremes or forecast uncertainty.'}
 (out/'metadata.json').write_bytes(encode(metadata));print(json.dumps({'layers':len(layers),'bytes':sum(p.stat().st_size for p in out.iterdir()),'metadataSha256':sha((out/'metadata.json').read_bytes()),'bomNumericFilesExported':0,'qualityCellDays':2623}))
if __name__=='__main__':main()
