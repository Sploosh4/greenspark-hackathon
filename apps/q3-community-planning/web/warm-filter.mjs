import {validateClimateAnomaly} from './modules/climate-contract.mjs';
// Native monthly anomalies only. No interpolation, network or temperature conversion.
export const ANOMALY_HASH='5ddc6a8adf1feaca185983895e8160b9b8e989a74fc47145ea257aee4a84d9f5';
export function validateAnomaly(payload,mean){
  if(mean?.fields?.some(f=>f.gribMetadata))return validateClimateAnomaly(payload,mean);
  const s=payload?.source,v=payload?.validation;
  if(s?.dataset!=='seasonal-postprocessed-single-levels'||s.variable!=='2m_temperature_anomaly'||s.product!=='ensemble_mean'||s.centre!=='ECMWF'||s.system!=='51'||s.issueMonth!=='2026-10'||s.units!=='degC_difference'||s.referencePeriod!=='1993-2016'||!s.baselineSourceUrl?.startsWith('https://')||s.rawSha256!==ANOMALY_HASH||v?.localGribSha256!==ANOMALY_HASH||v.preparedAdapterValidated!==true||v.decodedValuesVerified!==2484)throw Error('Anomaly source or validation metadata does not match the verified local handoff');
  if(payload.gridSpacingDegrees!==1||JSON.stringify(payload.latitudes)!==JSON.stringify(mean.latitudes)||JSON.stringify(payload.longitudes)!==JSON.stringify(mean.longitudes)||payload.fields?.length!==6)throw Error('Anomaly grid does not align with monthly mean source cells');
  for(const [i,f] of payload.fields.entries())if(f.leadMonth!==i+1||f.validMonth!==mean.fields[i].validMonth||f.valuesAnomalyC?.length!==23||f.valuesAnomalyC.some(row=>!Array.isArray(row)||row.length!==18||row.some(value=>value!==null&&(typeof value!=='number'||!Number.isFinite(value)))))throw Error('Invalid anomaly months, missingness or values');
  return payload;
}
export function validatePolicy(indices,threshold,minimum){
  if(!Array.isArray(indices)||!indices.length||indices.some(i=>!Number.isInteger(i)||i<0||i>5)||new Set(indices).size!==indices.length)throw Error('Choose one or more distinct forecast months');
  if(typeof threshold!=='number'||!Number.isFinite(threshold)||threshold<0)throw Error('Choose a non-negative Δ°C');
  if(!Number.isInteger(minimum)||minimum<1||minimum>indices.length)throw Error(`Choose X from 1 to ${indices.length}`);
  return {indices:[...indices].sort((a,b)=>a-b),threshold,minimum};
}
export function countMonths(values,indices,threshold,minimum){
  const policy=validatePolicy(indices,threshold,minimum);
  if(!Array.isArray(values)||values.length!==6||values.some(value=>value!==null&&(typeof value!=='number'||!Number.isFinite(value))))throw Error('Six finite anomaly values or explicit nulls are required');
  const selected=policy.indices.map(i=>values[i]);
  if(selected.some(value=>value===null))return {status:'unavailable_missing_months',count:null,meets:null,available:selected.filter(v=>v!==null).length,required:selected.length};
  const count=selected.filter(value=>value>=threshold).length;
  return {status:'complete',count,meets:count>=minimum,available:selected.length,required:selected.length};
}
export function countGrid(payload,policy){
  return payload.latitudes.flatMap((lat,y)=>payload.longitudes.map((lon,x)=>({lat,lon,...countMonths(payload.fields.map(f=>f.valuesAnomalyC[y][x]),policy.indices,policy.threshold,policy.minimum)})));
}
export function outlineMatches(results){
  // Cancel shared edges of matching native cells. This outlines contiguous
  // matches without drawing heavy borders around every matching tile.
  const edges=new Map();
  for(const r of results.filter(r=>r.meets===true)){
    const p=[[r.lon-.5,r.lat-.5],[r.lon+.5,r.lat-.5],[r.lon+.5,r.lat+.5],[r.lon-.5,r.lat+.5]];
    for(let i=0;i<4;i++){const edge=[p[i],p[(i+1)%4]],key=edge.map(p=>p.join(',')).sort().join('|');if(edges.has(key))edges.delete(key);else edges.set(key,edge);}
  }
  return {type:'FeatureCollection',features:edges.size?[{type:'Feature',properties:{meaning:'Matching native climate cells'},geometry:{type:'MultiLineString',coordinates:[...edges.values()]}}]:[]};
}
