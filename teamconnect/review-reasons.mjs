import {current,known,time,customerCases} from './core.mjs';

// Review reasons are disclosures that are current at the selected case date.
// Keep the existing support fallback when there is no current disclosure.
export function reviewInfo(d,c,t){
  const needs=current(d.needs.filter(r=>r.customer_id===c.customer_id),t)
    .sort((a,b)=>time(b.source_event_date)-time(a.source_event_date));
  const activeNeeds=needs.filter(r=>r.status==='current');
  const cases=customerCases(d,c.customer_id,t);
  const arr=current(d.arrangements.filter(r=>r.customer_id===c.customer_id),t)
    .filter(r=>r.status==='active');
  const need=activeNeeds[0];
  const latest=cases.slice().sort((a,b)=>time(b.opened_at)-time(a.opened_at))[0];
  const reasons=[...new Set(activeNeeds.map(r=>r.need_type).filter(Boolean))];
  if(!reasons.length){
    if(latest)reasons.push('support_review');
    else reasons.push(...new Set(arr.map(r=>r.arrangement_type).filter(Boolean)));
  }
  return {needs,cases,arr,need,reasons,reason:reasons[0]||'',
    flagged:need?.source_event_date||latest?.opened_at||arr[0]?.source_event_date,
    stage:latest?.stage,
    hasSupport:cases.length>0||known(d.arrangements.filter(r=>r.customer_id===c.customer_id),'effective_from',t).length>0,
    permission:current(d.permissions.filter(r=>r.customer_id===c.customer_id),t)[0]};
}

export function matchesReviewReason(info,filter){
  if(!filter)return true;
  if(filter==='support')return info.hasSupport;
  const financial=reason=>/financial|budget|affordability/.test(reason);
  return info.needs.some(r=>r.status==='current'&&r.need_type&&
    (filter==='financial'?financial(r.need_type):filter==='needs'&&!financial(r.need_type)));
}
