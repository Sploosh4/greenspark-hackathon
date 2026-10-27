import {current,known,time,customerCases} from './core.mjs';

// Case openings remain source events until a resolution is known at the cutoff.
// A disclosure without such a case supplies an event on its source date only.
function reviewTriggers(activeNeeds,cases,t){
  const openCases=cases.filter(k=>!k.resolutions.length);
  const triggers=openCases.map(k=>({type:'case_opened',
    reason:activeNeeds.find(n=>n.need_id&&n.need_id===k.need_id)?.need_type||'',
    recorded:k.opened_at}));
  const linkedNeeds=new Set(openCases.map(k=>k.need_id).filter(Boolean));
  const date=new Date(t+8*3600000).toISOString().slice(0,10),start=time(date);
  for(const n of activeNeeds){
    if(n.need_type&&!linkedNeeds.has(n.need_id)&&time(n.source_event_date)>=start&&time(n.source_event_date)<=t)
      triggers.push({type:'disclosure_recorded',reason:n.need_type,recorded:n.source_event_date});
  }
  const unique=new Map();
  for(const trigger of triggers)unique.set(JSON.stringify(trigger),trigger);
  return [...unique.values()].sort((a,b)=>time(b.recorded)-time(a.recorded));
}

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
  const supportNeeds=[...new Set(activeNeeds.map(r=>r.need_type).filter(Boolean))];
  const reasons=[...supportNeeds];
  if(!reasons.length){
    if(latest)reasons.push('support_review');
    else reasons.push(...new Set(arr.map(r=>r.arrangement_type).filter(Boolean)));
  }
  return {needs,cases,arr,need,reasons,supportNeeds,triggers:reviewTriggers(activeNeeds,cases,t),reason:reasons[0]||'',
    recorded:need?.source_event_date||latest?.opened_at||arr[0]?.source_event_date,
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
