import {cutoff,time,current,openAt,financeFor,depletionFor,billedFor,forecastFor} from './core.mjs';

export const REVIEW_DEFAULTS={view:'review',search:'',scope:'All communities',account:'all',signal:'all',sort:'reference',direction:'asc',page:'1',months:'12'};
export const CURRENT_SUPPORT=new Set(['active']);
const COOLING=new Set(['cooling_access_need','cooling_affordability_concern','temperature_management_need']);
export function reviewFor(d,c,date,event){
  const t=cutoff(date),id=c.customer_id,prepaid=!!d.rules[id],open=openAt(c,t);
  const needs=current(d.needs.filter(r=>r.customer_id===id),t);
  const activeNeeds=needs.filter(r=>r.status==='current');
  const arrangements=current(d.arrangements.filter(r=>r.customer_id===id),t);
  const support=arrangements.filter(r=>CURRENT_SUPPORT.has(r.status));
  const preference=current(d.permissions.filter(r=>r.customer_id===id),t).sort((a,b)=>time(b.effective_from)-time(a.effective_from))[0]||null;
  const finance=prepaid?financeFor(d,id,date):null;
  const depletion=depletionFor(finance),billed=prepaid?null:billedFor(d,id,date);
  const forecast=forecastFor(d,c,event,t);
  const weatherNeeds=activeNeeds.filter(r=>COOLING.has(r.need_type)&&event.startsWith('HEAT')&&forecast&&t<=time(forecast.valid_to));
  const due=support.filter(r=>r.review_due_date&&time(r.review_due_date)<time(date));
  const reasons=[];
  if(open&&finance?.offHours>0)reasons.push('Recorded off-supply periods');
  if(open&&finance&&finance.balance<=0)reasons.push('Credit at or below $0');
  if(open&&billed?.estimate!==null&&billed?.baseline>0&&billed.estimate>billed.baseline)reasons.push('Estimated charges increase');
  if(weatherNeeds.length)reasons.push('Weather-relevant disclosed need');
  if(activeNeeds.length)reasons.push('Current disclosed need');
  if(due.length)reasons.push('Support review date passed');
  const dates=[...activeNeeds.map(r=>r.source_event_date),...due.map(r=>r.review_due_date),...(finance?.history||[]).filter(r=>+r.disconnected_hours>0).map(r=>r.date),...(reasons.includes('Estimated charges increase')?[date]:[])].filter(Boolean).sort((a,b)=>time(b)-time(a));
  const relevantDate=dates[0]||billed?.prior?.issue_date||null;
  return {customer:c,reference:id,locality:c.locality,prepaid,account:prepaid?'Prepaid':'Billed',open,needs,activeNeeds,arrangements,support,preference,finance,depletion,billed,forecast,weatherNeeds,due,reasons,relevantDate,contact:preference?.preferred_channel||'not_recorded'};
}
export function selectReviews(rows,state){
  const query=state.search.trim().toLowerCase();
  const filtered=rows.filter(r=>(state.scope==='All communities'||r.locality===state.scope)&&
    (state.account==='all'||(state.account==='prepaid')===r.prepaid)&&
    (!query||[r.reference,r.locality,...r.reasons].join(' ').toLowerCase().includes(query))&&
    (state.signal==='all'||state.signal==='financial'&&r.open&&(r.finance?.offHours>0||r.finance&&r.finance.balance<=0||r.billed?.estimate!==null&&r.billed?.baseline>0&&r.billed.estimate>r.billed.baseline)||state.signal==='weather'&&r.weatherNeeds.length||state.signal==='needs'&&r.activeNeeds.length||state.signal==='support'&&r.due.length));
  const value=r=>({reference:r.reference,community:r.locality,account:r.account,reason:r.reasons.join(', '),date:r.relevantDate,support:r.support.length,contact:r.contact})[state.sort];
  const multiplier=state.direction==='desc'?-1:1;
  return filtered.sort((a,b)=>{const av=value(a),bv=value(b);if(av===null||av===undefined)return bv==null?a.reference.localeCompare(b.reference):1;if(bv===null||bv===undefined)return -1;const order=typeof av==='number'?av-bv:String(av).localeCompare(String(bv),'en',{numeric:true});return order*multiplier||a.reference.localeCompare(b.reference);});
}
