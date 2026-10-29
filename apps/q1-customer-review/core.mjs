export const DEFAULT_FILTERS={search:'',type:'',history:'linked',increase:'past',sort:'increase',direction:'desc'};
export const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const days=(a,b)=>Math.round((Date.parse(b)-Date.parse(a))/86400000)+1;
export const dateLabel=s=>new Date(s+'T12:00:00Z').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
export const windowLabel=(start,end)=>start.slice(0,7)===end.slice(0,7)?`${Number(start.slice(8))}–${new Date(end+'T12:00:00Z').toLocaleDateString('en-AU',{day:'numeric',month:'short',timeZone:'UTC'})}`:`${dateLabel(start)}–${dateLabel(end)}`;
export const pct=n=>n===null?'Unavailable':`${n>0?'+':''}${Number(n.toFixed(1))}%`;
export const average=xs=>xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null;
export function summary(row,d){
  const calculated=Array.isArray(row.predictions);
  const recent=calculated?[]:row.usage.filter(r=>r.date>= '2024-12-19' && r.date<=d.history_cutoff);
  const baseline=calculated?(row.predictions[0]?.baseline??null):(recent.length===14?average(recent.map(r=>+r.import_kwh)):null);
  const episodes=row.episodes.filter(e=>e.linked&&e.start>=d.history_window_start&&e.end<=d.history_cutoff);
  const estimates=d.events.map((event,i)=>{
    if(calculated){const p=row.predictions.find(p=>p.event_id===event.id);return {...event,...p,increase:p?.increase??null,predicted:p?.predicted??null,baseline:p?.baseline??null,duration:p?.duration??days(event.start,event.end)};}
    const increase=row.expected_percent_fixture[i];
    return {...event,increase,baseline,predicted:increase===null||baseline===null?null:baseline*(1+increase/100),duration:days(event.start,event.end)};
  });
  const nums=estimates.map(e=>e.increase).filter(x=>x!==null);
  const comparable=episodes.filter(e=>Number.isFinite(e.increase_percent));
  return {row,customer:row.customer,episodes,estimates,baseline,calculated,method:d.method,version:d.version,highest:nums.length?Math.max(...nums):null,threshold:comparable.length?Math.min(...comparable.map(e=>e.increase_percent)):null};
}
export const prepareQuery=d=>d.customers.map(r=>summary(r,d));
export function pageRows(rows,page=0,size=100){
  if(!Number.isInteger(size)||size<1||size>100)throw Error('Page size must be between1and100');
  const pages=Math.max(1,Math.ceil(rows.length/size)),index=Math.max(0,Math.min(Number.isInteger(page)?page:0,pages-1));
  return {rows:rows.slice(index*size,(index+1)*size),page:index,pages,total:rows.length,first:rows.length?index*size+1:0,last:Math.min(rows.length,(index+1)*size)};
}
export function query(d,filters={},prepared=null){
  const f={...DEFAULT_FILTERS,...filters};
  const rows=(prepared??prepareQuery(d)).filter(x=>{
    const c=x.customer;
    if(c.account_open_date>d.review_date||(c.account_close_date&&c.account_close_date<=d.review_date))return false;
    if(f.search&&!`${c.customer_id} ${c.locality} ${c.postcode}`.toLowerCase().includes(f.search.trim().toLowerCase()))return false;
    if(f.type&&((c.prepayment_meter==='True'?'Prepaid':'Billed')!==f.type))return false;
    if(f.history==='linked'&&!x.episodes.length)return false;
    if(f.increase==='past'&&!(x.highest!==null&&x.threshold!==null&&x.highest>=x.threshold))return false;
    if(f.increase==='available'&&x.highest===null)return false;
    if(f.increase==='unavailable'&&!x.estimates.some(e=>e.increase===null))return false;
    return true;
  });
  const dir=f.direction==='asc'?1:-1;
  return rows.sort((a,b)=>{
    if(f.sort==='customer')return dir*a.customer.customer_id.localeCompare(b.customer.customer_id);
    // Missing results remain at the end in both directions. A real zero stays numeric.
    if(a.highest===null&&b.highest!==null)return 1;
    if(b.highest===null&&a.highest!==null)return -1;
    return dir*((a.highest??0)-(b.highest??0))||a.customer.customer_id.localeCompare(b.customer.customer_id);
  });
}
export function explanation(x){
  const high=x.highest;
  if(!x.estimates.length)return 'No heat period was detected in this seven-day historical replay. The customer’s recorded use and account history remain available below.';
  if(high===null)return (x.estimates.length===1?'No electricity-use estimate is available for this heat period.':'No electricity-use estimate is available for either upcoming event.')+' The customer’s recorded use and account history are shown below.';
  const e=x.estimates.find(e=>e.increase===high);
  const end=new Date(e.end+'T12:00:00Z').toLocaleDateString('en-AU',{day:'numeric',month:'short',timeZone:'UTC'});
  const window=windowLabel(e.start,e.end);
  if(x.calculated){
    const value=Math.abs(Number(high.toFixed(1)));
    let text=high===0?`Daily electricity use from the grid is expected to stay at the recent level during ${window}.`:`We estimate ${value}% ${high>0?'more':'less'} electricity from the grid per day on average during ${window}.`;
    if(x.threshold!==null)text+=` Grid use was ${Math.abs(Number(x.threshold.toFixed(1)))}% ${x.threshold<0?'lower':'higher'} during a past heat period when difficulty was recorded.`;
    else text+=' No comparable past heat period with recorded help or difficulty is available.';
    if(x.estimates.some(e=>e.increase===null))text+=' Another heat period has no estimate.';
    return text;
  }
  let text=high===0?`In this demo, daily electricity use from the grid stays at the usual level on average during ${window}.`:`This demo estimates ${Math.abs(high)}% ${high>0?'more':'less'} electricity from the grid per day on average during ${window}.`;
  if(x.threshold!==null){
    const past=x.episodes.find(p=>p.increase_percent===x.threshold);
    const context={ 'Bill extension':'bill extension', 'Financial difficulty':'financial difficulty', 'Payment plan':'payment plan', 'Cooling cost difficulty':'difficulty paying cooling costs' }[past.label]??'support episode';
    text+=high<x.threshold?` That is below the lowest past rise linked to heat-related support in this demo (${x.threshold}%).`:` That is ${high===x.threshold?'the same as':'above'} the ${x.threshold}% rise shown for a past heat-related ${context}.`;
  }else text+=' No past heat-related help or difficulty is recorded in this demo.';
  if(x.estimates.some(e=>e.increase===null))text+=' The other event has no estimate.';
  return text;
}
export function csvCell(v){const s=String(v??'');return '"'+(/^[=+@\-\t\r]/.test(s)?"'"+s:s).replaceAll('"','""')+'"';}
export function exportRows(rows){
  if(rows.some(x=>x.calculated)){
    const head=['customer_id','account_type','locality','event_id','event_start','event_end','event_days','expected_increase_percent','baseline_daily_import_kwh','estimated_daily_import_kwh','past_comparison_percent','method_id','provenance'];
    return [head,...rows.flatMap(x=>x.estimates.map(e=>[x.customer.customer_id,x.customer.prepayment_meter==='True'?'Prepaid':'Billed',x.customer.locality,e.id,e.start,e.end,e.duration,e.increase,e.baseline,e.predicted,x.threshold,e.method_id,'calculated historical replay; synthetic business; unvalidated baseline; no live forecast']))].map(r=>r.map(csvCell).join(',')).join('\r\n');
  }
  const head=['customer_id','account_type','locality','event_id','event_start','event_end','event_days','expected_increase_percent_FIXTURE','baseline_daily_import_kwh_ILLUSTRATION','predicted_daily_import_kwh_FIXTURE','past_episode_min_percent_FIXTURE','provenance'];
  return [head,...rows.flatMap(x=>x.estimates.map(e=>[x.customer.customer_id,x.customer.prepayment_meter==='True'?'Prepaid':'Billed',x.customer.locality,e.id,e.start,e.end,e.duration,e.increase,e.baseline,e.predicted,x.threshold,'q1-ui-review-v1; authored review estimates and links; no live prediction']))].map(r=>r.map(csvCell).join(',')).join('\r\n');
}
