import {validateFinancialSupport} from './financial-support.mjs';
import {validateClimateMean} from './climate-contract.mjs';
import {GEOGRAPHY,GEOGRAPHY_SHA} from './geography-reference.mjs';
import {validateAnomaly} from '../warm-filter.mjs';
export function validateMean(d){
 if(d?.fields?.some(f=>f.gribMetadata))return validateClimateMean(d);
 if(d?.dataset!=='seasonal-monthly-single-levels'||d.units!=='degC'||d.product!=='ensemble mean'||d.centre!=='ECMWF'||String(d.system)!=='51'||d.issueDate!=='2026-10-01'||d.gribSha256!=='490c6f4118e41008eed3528804265f376a72d2a0355b91d324a19fabce2a33b9')throw Error('Mean source contract');
 if(JSON.stringify(d.latitudes)!==JSON.stringify(Array.from({length:23},(_,i)=>-13.5-i))||JSON.stringify(d.longitudes)!==JSON.stringify(Array.from({length:18},(_,i)=>112.5+i))||d.fields?.length!==6)throw Error('Native grid contract');
 const months=['2026-10','2026-11','2026-12','2027-01','2027-02','2027-03'];
 for(const [i,f] of d.fields.entries())if(f.validMonth!==months[i]||f.valuesC?.length!==23||f.valuesC.some(row=>!Array.isArray(row)||row.length!==18||row.some(v=>v!==null&&(typeof v!=='number'||!Number.isFinite(v)||v< -90||v>65))))throw Error('Mean values or months');
 return d;
}
export function validateSnapshot(p){
 if(p?.schema_version!==1||!['ready','stale','unavailable'].includes(p.status?.state))throw Error('Snapshot envelope');
 if(p.data===null){if(p.status.state!=='unavailable')throw Error('Missing snapshot');return p;}
 if(!p.data||Object.keys(p.data).sort().join(',')!=='anomaly,business,history,mean'||typeof p.generation!=='string'||!/^[0-9a-f]{64}$/.test(p.generation))throw Error('Snapshot bundle');
 const {mean,anomaly,history,business}=p.data;validateMean(mean);validateAnomaly(anomaly,mean);
 if(history.baseline!=='1991–2020'||history.points?.length!==12||new Set(history.points.map(x=>x.postcode)).size!==12||history.points.some(p=>!Number.isFinite(p.lat)||!Number.isFinite(p.lon)||p.months?.length!==12||p.months.some((m,i)=>m.month!==i+1||!Number.isFinite(m.meanDailyHighC)||!Number.isFinite(m.meanDailyLowC)||m.meanDailyHighC<m.meanDailyLowC||!Number.isInteger(m.days)||m.days<=0)))throw Error('Historical source contract');
 const businessPoints=business.geographyRegistrySha256===undefined?history.points:business.geographyRegistrySha256===GEOGRAPHY_SHA?GEOGRAPHY.areas.map(a=>({postcode:a.postcode,name:a.name,lon:a.referencePoint[0],lat:a.referencePoint[1]})):null;
 if(!businessPoints||business.geographyRegistrySha256&&(!business.geographySource||Object.keys(business.geographySource).length!==Object.keys(GEOGRAPHY.source).length||Object.entries(GEOGRAPHY.source).some(([k,v])=>business.geographySource[k]!==v)))throw Error('Trusted geography version');
 const count=v=>Number.isInteger(v)&&v>=0;
 const validDate=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v;
 const totals={totalAccounts:'accountCount',retainedTotalAccounts:'retainedAccountCount',closedAccounts:'closedAccounts',unknownStatusAccounts:'unknownStatusAccounts',notOpenAtSnapshotAccounts:'notOpenAtSnapshotAccounts'};
 if(!validDate(business.snapshotDate)||!validDate(business.historyStart)||business.historyEnd!==business.snapshotDate||business.historyStart>business.snapshotDate||business.snapshotDate>new Date().toISOString().slice(0,10)||business.areas?.length<1||business.areas?.length>businessPoints.length||new Set(business.areas.map(a=>a.postcode)).size!==business.areas.length||!count(business.snapshotUsageAccounts)||business.snapshotUsageAccounts<business.totalAccounts||business.snapshotUsageAccounts>business.retainedTotalAccounts||!business.businessClassification?.startsWith('Historical synthetic')||!business.activityRule)throw Error('Historical account contract');
 for(const [total,key] of Object.entries(totals))if(!count(business[total]??(total==='notOpenAtSnapshotAccounts'?0:undefined))||business.areas.some(a=>!count(a[key]??(key==='notOpenAtSnapshotAccounts'?0:undefined)))||business.areas.reduce((n,a)=>n+(a[key]??0),0)!==(business[total]??0))throw Error('Account totals');
 if(business.areas.some(a=>!count(a.prepaidAccounts)||!count(a.billedAccounts)||a.accountCount!==a.prepaidAccounts+a.billedAccounts||a.retainedAccountCount!==a.accountCount+a.closedAccounts+a.unknownStatusAccounts+(a.notOpenAtSnapshotAccounts??0)||!businessPoints.some(p=>p.postcode===a.postcode&&p.name===a.name&&p.lon===a.referencePoint?.[0]&&p.lat===a.referencePoint?.[1])))throw Error('Account area reconciliation');
 for(const area of business.areas){const f=area.financialContext;if(f&&(f.year!==2021||f.geography!=='POA'+area.postcode||!Number.isFinite(f.medianWeeklyHouseholdIncomeAUD)||f.medianWeeklyHouseholdIncomeAUD<0||f.sourceUrl!=='https://www.abs.gov.au/census/find-census-data/quickstats/2021/POA'+area.postcode))throw Error('Income context contract');}
 if(![undefined,'business_source_changed'].includes(business.financialSupportUnavailableReason))throw Error('Financial unavailable reason');
 if(business.financialSupport){if(business.financialSupportUnavailableReason)throw Error('Financial state conflict');validateFinancialSupport(business.financialSupport,business);}
 return p;
}
export function createSnapshotReader(fetcher=fetch,{timeoutMs=8000}={}){
 let lastGood=null;
 return {async read(){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{const response=await fetcher('/api/q3/snapshot',{cache:'no-store',signal:controller.signal});if(!response.ok)throw Error('Snapshot request failed');const packet=validateSnapshot(await response.json());
   if(!packet.data&&lastGood)throw Error('Snapshot unavailable');if(packet.data)lastGood=packet;return packet;
  }catch(error){const status={state:lastGood?'stale':'unavailable',checked_at:new Date().toISOString(),last_refresh_error:'snapshot_request_or_validation_failed',last_good_retained:!!lastGood};return lastGood?{...lastGood,status:{...lastGood.status,...status}}:{schema_version:1,generation:null,data:null,provenance:null,status};}
  finally{clearTimeout(timer);}
 }};
}
