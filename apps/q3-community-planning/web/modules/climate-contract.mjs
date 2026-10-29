// The bounded v2 contract supports future issue months, never a new grid/model.
const hash=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
export function issueMonths(issue){
 if(typeof issue!=='string'||!/^\d{4}-(0[1-9]|1[0-2])$/.test(issue))throw Error('Issue month contract');
 const [year,month]=issue.split('-').map(Number);
 return Array.from({length:7},(_,i)=>{const m=year*12+month-1+i;return `${Math.floor(m/12).toString().padStart(4,'0')}-${(m%12+1).toString().padStart(2,'0')}`;});
}
export function validateClimateFields(d,kind,issue){
 const months=issueMonths(issue),lat=Array.from({length:23},(_,i)=>-13.5-i),lon=Array.from({length:18},(_,i)=>112.5+i);
 if(JSON.stringify(d.latitudes)!==JSON.stringify(lat)||JSON.stringify(d.longitudes)!==JSON.stringify(lon)||d.gridSpacingDegrees!==1||d.fields?.length!==6)throw Error('Native grid contract');
 for(const [i,f]of d.fields.entries()){
  const info=f.gribMetadata,values=f[kind==='mean'?'valuesC':'valuesAnomalyC'];
  if(!info||f.leadMonth!==i+1||f.validMonth!==months[i]||f.gribValidityDate!==Number(months[i+1].replace('-','')+'01'))throw Error('Verifying month contract');
  const expected={centre:'ecmf',systemNumber:51,dataDate:Number(issue.replace('-','')+'01'),dataTime:0,shortName:kind==='mean'?'2t':'2ta',paramId:kind==='mean'?167:171167,units:'K',typeOfLevel:'surface',level:0,dataType:'em',marsStream:kind==='mean'?'msmm':'mmsa',forecastMonth:i+1,verifyingMonth:Number(months[i].replace('-','')),validityDate:f.gribValidityDate,validityTime:0,gridType:'regular_ll',Ni:18,Nj:23,numberOfDataPoints:414,iDirectionIncrementInDegrees:1,jDirectionIncrementInDegrees:1};
  if(![1,2].includes(info.edition)||Object.entries(expected).some(([k,v])=>info[k]!==v)||!Number.isInteger(info.numberOfMissing)||info.numberOfMissing<0||info.numberOfMissing>414)throw Error('GRIB metadata contract');
  if(!Array.isArray(values)||values.length!==23||values.some(r=>!Array.isArray(r)||r.length!==18))throw Error('Climate value shape');
  const flat=values.flat();if(flat.some(v=>v!==null&&(typeof v!=='number'||!Number.isFinite(v)||(kind==='mean'?(v< -90||v>65):(v< -50||v>50))))||flat.filter(v=>v===null).length!==info.numberOfMissing)throw Error('Climate missingness or units');
 }
 return d;
}
export function validateClimateMean(d){
 const issue=d?.issueDate?.slice(0,7);
 if(d?.issueDate!==issue+'-01'||d.dataset!=='seasonal-monthly-single-levels'||d.units!=='degC'||d.product!=='ensemble mean'||d.centre!=='ECMWF'||d.system!=='51'||d.variable!=='2m temperature'||!hash(d.gribSha256))throw Error('Mean source contract');
 return validateClimateFields(d,'mean',issue);
}
export function validateClimateAnomaly(a,m){
 const s=a?.source,v=a?.validation,issue=m.issueDate?.slice(0,7);
 if(s?.dataset!=='seasonal-postprocessed-single-levels'||s.variable!=='2m_temperature_anomaly'||s.product!=='ensemble_mean'||s.centre!=='ECMWF'||s.system!=='51'||s.issueMonth!==issue||s.units!=='degC_difference'||s.sourceUnits!=='K'||s.referencePeriod!=='1993-2016'||s.baselineSourceUrl!=='https://confluence.ecmwf.int/spaces/CKB/pages/340775655/C3S+seasonal+forecast+product+descriptions'||!hash(s.rawSha256)||v?.localGribSha256!==s.rawSha256||v.preparedAdapterValidated!==true||v.decodedValuesVerified!==2484)throw Error('Anomaly source contract');
 return validateClimateFields(a,'anomaly',issue);
}
