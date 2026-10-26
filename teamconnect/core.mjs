export const DEFAULT={community:'South Hedland',customer:'C105011',date:'2025-01-17',event:'HEAT01',view:'credit'};
export const time = s => s ? Date.parse(s.includes('T') ? s : s.replace(' ','T')+(s.length===10?'T00:00:00':'')+'+08:00') : NaN;
export const cutoff = date => time(date+' 12:00:00');
export const current = (rows,t) => rows.filter(r=>time(r.effective_from)<=t&&(!r.effective_to||t<time(r.effective_to)));
export const known = (rows,key,t) => rows.filter(r=>time(r[key])<=t);
export const openAt=(c,t)=>time(c.account_open_date)<=t&&(!c.account_close_date||t<time(c.account_close_date));
export function pointInPolygon(x,y,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){let [xi,yi]=ring[i],[xj,yj]=ring[j];if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi))inside=!inside;}return inside;}
export function issuedForecasts(d,event,t){const latest=new Map();for(const r of d.forecasts){if(r.event_id!==event||time(r.issued_at)>t)continue;const prev=latest.get(r.geometry_id);if(!prev||time(prev.issued_at)<time(r.issued_at))latest.set(r.geometry_id,r);}return [...latest.values()];}
export function forecastFor(d,c,event,t){if(!openAt(c,t))return null;return issuedForecasts(d,event,t).find(r=>{const g=d.footprints.features.find(f=>f.properties.geometry_id===r.geometry_id);return g&&pointInPolygon(c.longitude,c.latitude,g.geometry.coordinates[0]);})||null;}
export function financeFor(d,id,date){const t=cutoff(date),snapshot=(d.credit[id]||[]).find(r=>r[0]===date);if(!snapshot)return null;const start=time(date)-7*86400000,days=(d.daily[id]||[]).filter(r=>time(r.date)>=start&&time(r.date)<time(date));const cost=days.reduce((s,r)=>s+Number(r.usage_cost_cents),0),kwh=days.reduce((s,r)=>s+Number(r.import_kwh),0);const supply=known(d.supply.filter(r=>r.customer_id===id),'datetime',t).sort((a,b)=>time(a.datetime)-time(b.datetime)).at(-1);return {balance:snapshot[1],days:days.length,cost,kwh,history:days,offHours:days.reduce((s,r)=>s+Number(r.disconnected_hours),0),state:supply?.event_type==='disconnection'?'Off supply':supply?.event_type==='reconnection'?'On supply':'No disconnection recorded',topups:known(d.topups.filter(r=>r.customer_id===id),'datetime',t).filter(r=>time(r.datetime)>=t-7*86400000).sort((a,b)=>time(b.datetime)-time(a.datetime))};}
export function caseStage(d,k,t){
  const contacts=known(d.contacts.filter(r=>r.case_id===k.case_id),'occurred_at',t);
  const offers=known(d.offers.filter(r=>r.case_id===k.case_id),'offered_at',t),ids=new Set(offers.map(r=>r.offer_id));
  const decisions=known(d.decisions.filter(r=>ids.has(r.offer_id)),'decided_at',t);
  const deliveries=known(d.deliveries.filter(r=>r.case_id===k.case_id),'delivered_at',t);
  const resolutions=known(d.resolutions.filter(r=>r.case_id===k.case_id),'resolved_at',t);
  const decision=decisions.slice().sort((a,b)=>time(b.decided_at)-time(a.decided_at))[0];
  let stage='Contact not recorded';
  if(contacts.some(r=>r.outcome==='not_reached'))stage='Not reached';
  if(contacts.some(r=>r.outcome==='reached'))stage='Reached · no offer';
  if(offers.length)stage='Offer undecided';
  if(decision?.decision==='declined')stage='Offer declined';
  if(decision?.decision==='accepted')stage='Accepted · awaiting delivery';
  if(deliveries.length)stage='Delivered · concern ongoing';
  if(resolutions.length)stage='Customer confirmed resolution';
  return {stage,contacts,offers,decisions,deliveries,resolutions};
}
export function customerCases(d,id,t){return known(d.cases.filter(r=>r.customer_id===id),'opened_at',t).map(k=>({...k,...caseStage(d,k,t)}));}
export function funnelFor(d,state){
  const t=cutoff(state.date),customers=d.customers.filter(c=>c.locality===state.community),ids=new Set(customers.map(c=>c.customer_id));
  const campaign=d.campaigns.find(r=>r.event_id===state.event&&time(r.created_at)<=t);
  const audience=campaign?d.audience.filter(r=>r.campaign_id===campaign.campaign_id&&ids.has(r.customer_id)&&time(r.eligibility_at)<=t):[];
  const audienceIds=new Set(audience.map(r=>r.customer_id));
  const cases=campaign?known(d.cases.filter(r=>r.campaign_id===campaign.campaign_id&&audienceIds.has(r.customer_id)),'opened_at',t):[];
  const groups={},rank=['Contact not recorded','Not reached','Reached · no offer','Offer undecided','Offer declined','Accepted · awaiting delivery','Delivered · concern ongoing','Customer confirmed resolution'];
  for(const a of audience)groups[a.customer_id]='Contact not recorded';
  for(const k of cases){const stage=caseStage(d,k,t).stage;if(rank.indexOf(stage)>rank.indexOf(groups[k.customer_id]))groups[k.customer_id]=stage;}
  return {campaign,audience,groups,rank};
}
export const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function depletionFor(finance){if(!finance)return null;const days=finance.history.filter(r=>+r.disconnected_hours===0),average=days.reduce((s,r)=>s+Number(r.usage_cost_cents),0)/days.length;return days.length>=3&&average>0?{average,days:days.length,coverage:Math.max(0,finance.balance)/average}:null;}
export function billedFor(d,id,date){
  const t=cutoff(date),all=(d.billed_usage[id]||[]).filter(r=>time(r[0])<time(date));
  const recent=all.filter(r=>time(r[0])>=time(date)-14*86400000);
  const bills=known(d.bills.filter(r=>r.customer_id===id),'issue_date',t).sort((a,b)=>time(b.issue_date)-time(a.issue_date));
  const payments=known(d.billed_payments.filter(r=>r.customer_id===id),'date',t).filter(r=>r.status==='cleared');
  const rule=d.billed_rules[id],prior=bills[0];
  const nonnegative=n=>n!==''&&n!==null&&n!==undefined&&Number.isFinite(Number(n))&&Number(n)>=0;
  const canonicalRate=rule&&[rule.usage_cents_per_kwh,rule.supply_cents_per_day,rule.concession_cents_per_day].every(nonnegative);
  const baseRate=!rule&&prior&&+prior.kwh>0&&nonnegative(prior.usage_charge_cents)&&+prior.usage_charge_cents>0&&nonnegative(prior.supply_charge_cents)&&time(prior.period_end)>=time(prior.period_start);
  const periodDays=baseRate?Math.round((time(prior.period_end)-time(prior.period_start))/86400000)+1:null;
  let estimate=null,baseline=rule&&prior&&nonnegative(prior.amount_due_cents)?+prior.amount_due_cents:null,formula=null;
  if(baseRate)baseline=Math.round((+prior.usage_charge_cents + +prior.supply_charge_cents)/periodDays*30);
  if(recent.length>=3&&recent.every(r=>nonnegative(r[1]))){
    const dailyKwh=recent.reduce((s,r)=>s+Number(r[1]),0)/recent.length;
    if(canonicalRate){
      const month=date.slice(0,7),last=new Date(Date.UTC(+date.slice(0,4),+date.slice(5,7),0)).getUTCDate();
      const completed=all.filter(r=>r[0].startsWith(month));
      // Missing or duplicated elapsed days cannot be counted as remaining days.
      if(completed.length===+date.slice(8)-1&&new Set(completed.map(r=>r[0])).size===completed.length&&completed.every(r=>nonnegative(r[1]))){
        const accrued=completed.reduce((s,r)=>s+Number(r[1]),0),remaining=last-completed.length,projected=accrued+remaining*dailyKwh;
        estimate=Math.round(projected*rule.usage_cents_per_kwh+last*(rule.supply_cents_per_day-rule.concession_cents_per_day));
        formula={kind:'monthly',dailyKwh,days:recent.length,last,accrued,completed:completed.length,remaining,projected,usageRate:rule.usage_cents_per_kwh,supply:rule.supply_cents_per_day,concession:rule.concession_cents_per_day};
      }
    }else if(baseRate){
      const rate=+prior.usage_charge_cents/+prior.kwh,supply=+prior.supply_charge_cents/periodDays;
      estimate=Math.round(dailyKwh*30*rate+supply*30);
      formula={kind:'gross30',dailyKwh,days:recent.length,usageRate:rate,supply,periodDays,projected:dailyKwh*30};
    }
  }
  const paymentIds=new Set(payments.map(r=>r.payment_id)),billIds=new Set(bills.map(r=>r.bill_id));
  const allocated=d.allocations.filter(r=>paymentIds.has(r.payment_id)&&billIds.has(r.bill_id)).reduce((s,r)=>s+Number(r.allocated_cents),0);
  return {recent,bills,payments:payments.filter(r=>time(r.date)>=t-90*86400000),prior,estimate,baseline,formula,override:!!rule,outstanding:rule?bills.reduce((s,r)=>s+Number(r.amount_due_cents),0)-allocated:null};
}
export function needWeatherMatch(d,c,need,event,t){const f=forecastFor(d,c,event,t);if(!f)return 'No matching issued forecast for this account';if(need.status!=='current')return 'Retained history · not a current disclosed need';if(['cooling_access_need','cooling_affordability_concern','temperature_management_need'].includes(need.need_type)&&event.startsWith('HEAT'))return t>time(f.valid_to)?'Heat-related disclosure · forecast validity ended':'Heat-related disclosure in the issued forecast footprint';return 'Recorded need and weather shown together · no specific need/weather match asserted';}
