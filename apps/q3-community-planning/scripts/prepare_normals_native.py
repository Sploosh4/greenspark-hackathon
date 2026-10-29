"""Append licensed SILO-derived 1991–2020 normals; no downloads or BoM files."""
import argparse,calendar,gzip,hashlib,json
from pathlib import Path
import numpy as np
import rasterio,xarray as xr
from rasterio.warp import transform_bounds,transform_geom,reproject,Resampling
from rasterio.transform import from_bounds
from rasterio.features import rasterize
from prepare_history_native import png,encode,sha

def main():
 p=argparse.ArgumentParser();p.add_argument('normals',type=Path);p.add_argument('wa_display_mask',type=Path);p.add_argument('output',type=Path);args=p.parse_args();r=args.normals;out=args.output
 raw=(r/'derived/q3-silo-climatology-1991-2020.json.gz').read_bytes();assert sha(raw)=='b7a340b2f084e2a0e4ea2bd558e59e5ba752e78abbcb864a8f65c33ff0cda0a7'
 q=json.loads(gzip.decompress(raw));assert q['validation_status']=='validated' and q['baseline']=='1991-2020' and q['licence']=='CC BY 4.0'
 nc=r/'derived/wa-silo-derived-monthly-normals-1991-2020.nc';assert sha(nc.read_bytes())=='fe4341348e839db1e7ed6fbcf87d8e0498fb2534267ae358e9c36ee8371eb1ef'
 verify=json.loads((r/'derived/verification.json').read_text());assert verify['source_inversion_cell_days']==585 and verify['source_objects']==21916 and verify['year_months']==360 and verify['calendar_days']==10958
 m=json.loads((out/'metadata.json').read_text());mask=json.loads(args.wa_display_mask.read_text());total_flags=0
 with xr.open_dataset(nc) as ds:
  for month in range(1,13):
   key=f'normal-{month:02d}';native=ds.sel(calendar_month=month)
   arrays=[native[k].values for k in ['tmax_climatology','tmin_climatology','dmt_climatology','dmt_valid_pair_sensitivity']]
   for a in arrays:assert a.shape==(431,323) and np.isfinite(a).sum()==91180
   # Independently read matching native COGs before producing the renderer assets.
   with rasterio.open(r/f'derived/monthly-cog/wa-silo-derived-1991-2020-{month:02d}.tif') as source:
    assert source.shape==(431,323) and source.count==4 and source.crs.to_epsg()==4326
    for i,a in enumerate(arrays):assert np.array_equal(source.read(i+1,masked=True).filled(np.nan),a,equal_nan=True)
    bounds=source.bounds;src_transform=source.transform
   flags=native['inversion_day_count'].values.astype('int32');ranges=native['out_of_point_qc_range_day_count'].values.astype('int32');total_flags+=int(flags.sum())
   fields={name:[float(v) if np.isfinite(v) else None for v in a.ravel()] for name,a in zip(['tmax','tmin','midpoint','midpointValidPairSensitivity'],arrays)}
   fields.update(qualityFlags=flags.ravel().tolist(),rangeFlags=ranges.ravel().tolist())
   source_months=[f'{year}-{month:02d}' for year in range(1991,2021)];period=f'{calendar.month_name[month]} monthly normal · 1991–2020 · SILO-derived'
   payload={'layer':key,'period':period,'sourceMonths':source_months,'statistic':'daily_tmax_tmin_midpoint','units':'degC','fields':fields};data=gzip.compress(encode(payload),mtime=0);(out/(key+'.json.gz')).write_bytes(data)
   mb=transform_bounds('EPSG:4326','EPSG:3857',*bounds);height=m['image']['height'];width=m['image']['width'];target=from_bounds(*mb,width,height)
   land=rasterize(((transform_geom('EPSG:4326','EPSG:3857',f['geometry']),1) for f in mask['features']),out_shape=(height,width),transform=target,fill=0).astype(bool)
   projected=np.full((height,width),np.nan,dtype='float32');reproject(arrays[2].astype('float32'),projected,src_transform=src_transform,src_crs='EPSG:4326',dst_transform=target,dst_crs='EPSG:3857',src_nodata=np.nan,dst_nodata=np.nan,resampling=Resampling.nearest)
   v=np.clip((np.nan_to_num(projected,nan=8)-8)/28,0,1);low=np.array([238,230,248]);high=np.array([85,33,117]);rgba=np.zeros((height,width,4),dtype='uint8');rgba[:,:,:3]=(low[None,None,:]*(1-v[:,:,None])+high[None,None,:]*v[:,:,None]).astype('uint8');rgba[:,:,3]=np.where(np.isfinite(projected)&land,255,0);image=png(rgba);(out/(key+'.png')).write_bytes(image)
   m['layers'][key]={'period':period,'sourceMonths':source_months,'dataSha256':sha(data),'imageSha256':sha(image),'qualityFlaggedCellDays':int(flags.sum()),'rangeFlaggedCellDays':int(ranges.sum()),'validNativeCells':91180}
 assert total_flags==585
 m['schema']='q3-silo-native-history-v2';m['normal']={'period':['1991-01-01','2020-12-31'],'source':'SILO-derived observational monthly normal; equal weight for each of 30 yearly complete monthly means','licence':'CC BY 4.0','licenceEvidence':q['licence_evidence'],'sourceObjects':21916,'sourceMonths':360,'sourceDays':10958,'sourceInversionCellDays':585,'validPairSensitivityMaxAbsDifferenceC':verify['max_abs_dmt_sensitivity_difference_c'] if 'max_abs_dmt_sensitivity_difference_c' in verify else q['source_quality_summary']['max_abs_dmt_sensitivity_difference_c'],'inputGzipSha256':sha(raw),'inputNativeNetcdfSha256':sha(nc.read_bytes()),'validation':'4800 independent scalar normal recomputations;264 existing locality comparisons; native COG/NetCDF equality'}
 m['excluded']='No BoM numeric climatology is included. No infilling or source-value correction. Observed midpoint normals and recent history remain separate from ECMWF mean air-temperature forecasts and the 1993–2016 model anomaly baseline.'
 (out/'metadata.json').write_bytes(encode(m));print(json.dumps({'layers':len(m['layers']),'normalSourceFlags':total_flags,'metadataSha256':sha((out/'metadata.json').read_bytes())}))
if __name__=='__main__':main()
