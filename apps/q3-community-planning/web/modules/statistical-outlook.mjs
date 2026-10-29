// Separate frozen statistical-source contract. No ECMWF validation bypass.
export const CONTRACT='season-ahead-statistical-outlook-v1';
export const SOURCE='namash-ridge-lightgbm-v1';
export const COMMIT='e8143867c295cac0071f6e6f90ee5e0295960a95';
export const EXPORT_SHA='909904199eafcefcfaaa8844ae8bf7a4b53ca55326df3a2973290f294e7dc247';
const ISSUES={'2026-10':['2026-10','2026-11','2026-12','2027-01','2027-02','2027-03'],'2026-11':['2026-11','2026-12','2027-01','2027-02','2027-03','2027-04']};
const exact=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const keys=(o,n)=>o&&typeof o==='object'&&!Array.isArray(o)&&exact(Object.keys(o).sort(),n.slice().sort());
const numeric=(v,lo,hi,missing=true)=>v===null&&missing||typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
const check=(ok,message)=>{if(!ok)throw Error(message);};
export function validateStatistical(p){
 check(p?.schema_version===1&&p.contract===CONTRACT&&p.source_id===SOURCE&&['ready','stale','unavailable'].includes(p.status?.state),'Statistical envelope');
 const pr=p.provenance;check(pr?.sourceId===SOURCE&&pr.commit===COMMIT&&pr.exportSha256===EXPORT_SHA&&pr.baseline?.period==='1991-2020'&&pr.baseline.dataset==='NASA POWER / MERRA-2 T2M'&&pr.baseline.statistic==='calendar-month mean'&&exact(pr.units,{temperature:'degC',anomaly:'degC_difference',probability:'fraction',range:'degC',skill:'MSE skill vs climatology'})&&pr.publicationDate===null&&pr.issueDatePrecision==='month only','Statistical provenance');
 if(p.data===null){check(p.status.state==='unavailable','Statistical unavailable state');return p;}
 const d=p.data;check(keys(d,['meta','issues','cells','localities'])&&d.meta?.training_through==='2026-09'&&d.meta.source==='NASA POWER MERRA-2 T2M monthly'&&d.meta.model==='Mean of ridge and LightGBM on anomalies from per-cell climatology + linear trend'&&d.meta.partial_month==='Oct 2026 from daily T2M 1-21 Oct'&&exact(d.meta.indices_carried_forward,['nino34 2026-10 = 09 value','sam 2026-10 = 09 value']),'Statistical method');
 check(Array.isArray(d.issues)&&d.issues.length===2,'Statistical issue count');
 d.issues.forEach((i,n)=>{const k=Object.keys(ISSUES)[n];check(i.key===k&&exact(i.months,ISSUES[k])&&i.uses_partial_month===(k==='2026-11')&&['available','advance','stale'].includes(p.status.issues?.[k]?.state)&&p.status.issues[k].uses_partial_month===i.uses_partial_month,'Statistical month alignment');});
 check(Array.isArray(d.cells)&&d.cells.length===255,'Statistical cell count');const seen=new Set();
 for(const c of d.cells){
  check(keys(c,['id','lat','lon','land','skill','f'])&&numeric(c.lat,-35.5,-13.5,false)&&numeric(c.lon,112.5,129.5,false)&&Math.abs(c.lat)%1===.5&&c.lon%1===.5&&c.id===`${c.lat.toFixed(1)}_${c.lon.toFixed(1)}`&&!seen.has(c.id),'Statistical coordinates');seen.add(c.id);
  check(numeric(c.land,0,1,false)&&Array.isArray(c.skill)&&c.skill.length===6&&c.skill.every(v=>v===null||typeof v==='number'&&Number.isFinite(v)&&v<=1)&&keys(c.f,Object.keys(ISSUES)),'Statistical skill/issues');
  for(const f of Object.values(c.f)){
   check(keys(f,['t','a','p','lo','hi','n']),'Statistical measures');
   for(const [k,lo,hi] of [['t',-90,65],['n',-90,65],['lo',-90,65],['hi',-90,65],['a',-30,30],['p',0,1]])check(Array.isArray(f[k])&&f[k].length===6&&f[k].every(v=>numeric(v,lo,hi)),`Statistical values ${k}`);
   for(let i=0;i<6;i++){const [t,a,n,lo,hi]=['t','a','n','lo','hi'].map(k=>f[k][i]);check((lo===null||hi===null||lo<=hi)&&(t===null||(lo===null||lo<=t)&&(hi===null||t<=hi))&&([t,a,n].includes(null)||Math.abs(t-n-a)<=.105),'Statistical interval/anomaly');}
  }
 }
 check(Array.isArray(d.localities)&&d.localities.length===11&&new Set(d.localities.map(l=>l.name)).size===11,'Statistical localities');
 for(const l of d.localities)check(typeof l.name==='string'&&l.name.length>0&&l.name.length<=80&&numeric(l.lat,-36,-13,false)&&numeric(l.lon,112,130,false)&&seen.has(l.cell)&&l.cell===`${(Math.floor(l.lat)+.5).toFixed(1)}_${(Math.floor(l.lon)+.5).toFixed(1)}`,'Statistical locality join');
 return p;
}
// Missing source cells remain explicit nulls on the shared display grid.
export function projectStatistical(packet,issue){
 validateStatistical(packet);const d=packet.data,iss=d?.issues.find(i=>i.key===issue);check(iss,'Unknown statistical issue');
 const latitudes=Array.from({length:23},(_,i)=>-13.5-i),longitudes=Array.from({length:18},(_,i)=>112.5+i),byId=new Map(d.cells.map(c=>[c.id,c]));
 const grid=(k,i)=>latitudes.map(la=>longitudes.map(lo=>byId.get(`${la.toFixed(1)}_${lo.toFixed(1)}`)?.f[issue][k][i]??null));
 const fields=iss.months.map((validMonth,i)=>({validMonth,leadMonth:i+1,valuesC:grid('t',i),valuesAnomalyC:grid('a',i),probability:grid('p',i)}));
 return {sourceId:SOURCE,issueMonth:issue,issueDate:issue+'-01',issueDatePrecision:'month only',latitudes,longitudes,fields,sourceCellCount:255,baseline:'1991–2020 NASA POWER / MERRA-2',partial:iss.uses_partial_month,issueState:packet.status.issues[issue].state};
}
export function statisticalCell(packet,issue,lon,lat,index){
 const c=packet?.data?.cells.find(c=>c.lon===lon&&c.lat===lat),f=c?.f[issue];
 return f?{temperature:f.t[index],anomaly:f.a[index],probability:f.p[index],normal:f.n[index],low:f.lo[index],high:f.hi[index],skill:c.skill[index]}:null;
}
export async function readStatistical(fetcher=fetch,{timeoutMs=8000}={}){
 const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeoutMs);
 try{const r=await fetcher('/api/q3/statistical-outlook',{cache:'no-store',signal:ctl.signal});if(!r.ok)throw Error('Statistical request failed');return validateStatistical(await r.json());}
 finally{clearTimeout(timer);}
}
export const MEASURES={
 temperature:{label:'Monthly mean',unit:'°C',domain:[14,36],stops:[14,'#679fc8',20,'#c0d9d6',26,'#f6dea2',32,'#e77645',36,'#b51f36'],ticks:['14','20','26','32','36']},
 anomaly:{label:'Difference from source average',unit:'°C',domain:[-3,3],stops:[-3,'#184f95',-1.5,'#86b6ef',0,'#f0efec',1.5,'#ef9a86',3,'#a8231f'],ticks:['−3','−1.5','0','+1.5','+3']},
 probability:{label:'Chance warmer · experimental',unit:'%',domain:[0,1],stops:[0,'#184f95',.3,'#86b6ef',.5,'#f0efec',.7,'#ef9a86',1,'#a8231f'],ticks:['0','25','50','75','100']}
};
export function measureReading(v,measure){return v===null||!Number.isFinite(v)?'No data':measure==='probability'?`${Math.round(v*100)}%`:measure==='anomaly'?`${v>=0?'+':''}${v.toFixed(2)} °C`:`${v.toFixed(1)} °C`;}
