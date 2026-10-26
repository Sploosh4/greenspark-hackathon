import {DEFAULT,time,cutoff,known,openAt,needWeatherMatch,customerCases,funnelFor,esc} from './core.mjs';
import {REVIEW_DEFAULTS,reviewFor,selectReviews} from './review.mjs';

const $=s=>document.querySelector(s);
const money=n=>Number.isFinite(n)?new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(n/100):'Unavailable';
const num=n=>Number.isFinite(Number(n))?new Intl.NumberFormat('en-AU',{maximumFractionDigits:1}).format(Number(n)):'Unavailable';
const calc=n=>new Intl.NumberFormat('en-AU',{maximumFractionDigits:6}).format(n);
const pretty=s=>{const labels={True:'Yes',False:'No',support_check_in_schedule:'Support check-in',financial_pressure_disclosed:'Financial pressure disclosed'};const value=labels[s]||String(s||'Not recorded').replaceAll('_',' ');return esc(value.charAt(0).toUpperCase()+value.slice(1));};
const dateText=s=>s&&Number.isFinite(time(s))?new Date(time(s)).toLocaleDateString('en-AU',{timeZone:'Australia/Perth',day:'numeric',month:'short',year:'numeric'}):'Not recorded';
const stamp=s=>s?esc(s.replace('T',' ').replace('+08:00','').slice(0,16))+' AWST':'Not recorded';
const empty=(title,text='')=>`<div class="empty"><strong>${esc(title)}</strong>${esc(text)}</div>`;
const badge=(text,tone='neutral')=>`<span class="badge ${tone}">${esc(text)}</span>`;
const stat=(label,value,detail='')=>`<div class="stat"><span>${esc(label)}</span><strong>${value}</strong><small>${detail}</small></div>`;
const table=(head,rows)=>`<div class="table-wrap"><table><thead><tr>${head.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
const panel=(title,body,extra='')=>`<section class="panel ${extra}"><div class="panel-heading"><h2>${title}</h2></div>${body}</section>`;
const detail=(title,body)=>`<details><summary>${title}</summary><div class="details-body">${body}</div></details>`;
const tabs=[['overview','Overview'],['credit','Financial pressure'],['needs','Disclosed needs'],['arrangements','Existing arrangements'],['journey','Support journey']];
let d,state,activeMap,resizeObserver,reviewCache,queueScroll=0;

function chart(values,{label,range=false,unit=''}={}){
  if(!values.length)return empty('No completed observations');
  const max=Math.max(...values.map(v=>v.upper??v.y),1)*1.2,w=660,h=220;
  const x=i=>45+i*(w-75)/Math.max(1,values.length-1),y=v=>h-35-v/max*(h-60);
  const band=range?`<path class="band" d="${values.map((v,i)=>`${i?'L':'M'}${x(i)},${y(v.upper)}`).join(' ')} ${values.map((v,i)=>[v,i]).reverse().map(([v,i])=>`L${x(i)},${y(v.lower)}`).join(' ')} Z"/>`:'';
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title>${[0,.5,1].map(f=>`<line class="gridline" x1="45" x2="${w-20}" y1="${y(max*f)}" y2="${y(max*f)}"/><text x="34" y="${y(max*f)+3}" text-anchor="end">${num(max*f)}</text>`).join('')}${band}<path class="line" d="${values.map((v,i)=>`${i?'L':'M'}${x(i)},${y(v.y)}`).join(' ')}"/>${values.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v.y)}" r="3.5"><title>${esc(v.label)}: ${num(v.y)}${unit}${range?` (${num(v.lower)}–${num(v.upper)})`:''}</title></circle><text x="${x(i)}" y="${h-12}" text-anchor="middle">${esc(v.label)}</text>`).join('')}</svg>`;
}
function summaries(){
  const key=state.date+'|'+state.event;
  if(reviewCache?.key!==key)reviewCache={key,rows:d.customers.map(c=>reviewFor(d,c,state.date,state.event))};
  return reviewCache.rows;
}
function customerSummary(){return summaries().find(r=>r.reference===state.customer);}
function title(text,description,actions=''){
  $('#workspace-heading').innerHTML=`<div class="page-title"><div><h1 tabindex="-1">${esc(text)}</h1><p>${description}</p></div><div class="title-actions">${actions}</div></div>`;
  document.title=`${text} · Team Connect`;
}
function options(values,selected){return values.map(([value,label])=>`<option value="${esc(value)}"${value===selected?' selected':''}>${esc(label)}</option>`).join('');}
function queue(){
  const rows=selectReviews(summaries(),state),pageSize=20,pages=Math.max(1,Math.ceil(rows.length/pageSize));
  state.page=String(Math.min(Math.max(1,+state.page||1),pages));
  const start=(+state.page-1)*pageSize,visible=rows.slice(start,start+pageSize);
  const reviewCount=summaries().filter(r=>r.reasons.length).length;
  const columns=[['reference','Customer reference'],['community','Community'],['account','Account'],['reason','Review context'],['date','Relevant date'],['support','Current support'],['contact','Preferred contact']];
  title('Customer review','Account context and recorded support, as of '+dateText(state.date)+'.',`<button class="secondary" id="prepaid-example">Prepaid example</button><button class="secondary" id="billed-example">Billed example</button>`);
  return `<div class="metrics">${stat('Accounts',String(d.customers.length),'Supplied scenario population')}${stat('With review context',String(reviewCount),'Recorded signals · no automated decisions')}${stat('Current weather matches',String(summaries().filter(r=>r.weatherNeeds.length).length),'Explicit current needs only')}</div>
  <section class="panel"><form class="filters" id="review-filters" role="search"><label class="search-label">Search customers<input id="search" type="search" value="${esc(state.search)}" placeholder="Reference, community or review context" autocomplete="off"></label><label>Community<select id="scope">${options([['All communities','All communities'],...[...new Set(d.customers.map(c=>c.locality))].sort().map(c=>[c,c])],state.scope)}</select></label><label>Account<select id="account-filter">${options([['all','All accounts'],['prepaid','Prepaid'],['billed','Billed']],state.account)}</select></label><label>Review context<select id="signal-filter">${options([['all','All contexts'],['financial','Financial context'],['weather','Weather-relevant need'],['needs','Current disclosed need'],['support','Support review date passed']],state.signal)}</select></label><button class="text-button" type="button" id="clear-filters">Clear</button></form>
  <div class="table-status" role="status">${rows.length} ${rows.length===1?'customer':'customers'}${rows.length?` · showing ${start+1}–${Math.min(start+pageSize,rows.length)}`:''}</div>
  <div class="table-wrap review-table"><table><caption class="sr-only">Customer review queue. Select a customer reference to open their workspace.</caption><thead><tr>${columns.map(([key,label])=>`<th scope="col" aria-sort="${state.sort===key?(state.direction==='asc'?'ascending':'descending'):'none'}"><button data-sort="${key}">${label}<span aria-hidden="true">${state.sort===key?(state.direction==='asc'?'↑':'↓'):'↕'}</span></button></th>`).join('')}</tr></thead><tbody>${visible.map(r=>`<tr><td><button class="customer-link" data-customer="${r.reference}">${r.reference}</button>${!r.open?'<small>Account closed</small>':''}</td><td>${esc(r.locality)}<small>${esc(r.customer.region)}</small></td><td>${badge(r.account)}</td><td>${r.reasons.length?r.reasons.slice(0,2).map(reason=>`<span class="reason">${esc(reason)}</span>`).join(''):'<span class="muted">No current review signal</span>'}</td><td>${dateText(r.relevantDate)}</td><td>${r.support.length?`${r.support.length} active`:'None recorded'}</td><td>${pretty(r.contact)}</td></tr>`).join('')}</tbody></table></div>${!rows.length?empty('No matching customers','Try another search or clear the filters.'):''}<div class="pagination"><span>Page ${state.page} of ${pages}</span><button class="secondary" data-page="${+state.page-1}" ${+state.page===1?'disabled':''}>Previous</button><button class="secondary" data-page="${+state.page+1}" ${+state.page>=pages?'disabled':''}>Next</button></div></section>`;
}
function overview(r){
  const why=r.reasons.length?r.reasons.map(s=>`<li>${esc(s)}</li>`).join(''):'<li>No current review signal recorded.</li>';
  const support=r.support.length?r.support.map(s=>`<div class="record"><strong>${pretty(s.arrangement_type)}</strong>${badge('Active','positive')}<p>Review due ${dateText(s.review_due_date)}</p></div>`).join(''):empty('No active support recorded');
  const latest=customerCases(d,r.reference,cutoff(state.date)).sort((a,b)=>time(b.opened_at)-time(a.opened_at))[0];
  return `<div class="overview-grid"><div>${panel('Why this account is in review',`<div class="pad"><ul class="reason-list">${why}</ul><dl class="facts"><div><dt>Relevant record date</dt><dd>${dateText(r.relevantDate)}</dd></div><div><dt>Account</dt><dd>${r.account} · ${r.open?'Open':'Closed'}</dd></div></dl><button class="text-button" data-jump="credit">Inspect financial context →</button></div>`)}${panel('Current support',support+`<div class="panel-foot"><button class="text-button" data-jump="arrangements">View arrangements →</button></div>`)}${panel('Preferred contact',preference(r))}</div><div>${panel('Financial context',`<div class="pad">${r.prepaid?`<p class="kicker">Recorded credit · 12:00 AWST</p><strong class="large-value">${r.finance?money(r.finance.balance):'Unavailable'}</strong><p class="sub">${r.depletion?num(r.depletion.coverage)+' days illustrative coverage':'Coverage estimate unavailable'}</p>`:`<p class="kicker">${r.billed.formula?.kind==='monthly'?'Estimated current-month bill':'Estimated 30-day gross charges'}</p><strong class="large-value">${money(r.billed.estimate)}</strong><p class="sub">${r.billed.baseline!==null?'Comparison '+money(r.billed.baseline):'Comparison unavailable'}</p>`}<button class="text-button" data-jump="credit">View calculation →</button></div>`)}${panel('Latest support progression',`<div class="pad">${latest?`<p>${badge(latest.stage,latest.resolutions.length?'positive':'neutral')}</p><p class="sub">Opened ${dateText(latest.opened_at)} · ${esc(latest.case_id)}</p>`:empty('No case recorded as of this date')}<button class="text-button" data-jump="journey">View support journey →</button></div>`)}</div></div>`;
}
function preference(r){
  const p=r.preference;
  return p?`<div class="pad"><dl class="facts"><div><dt>Preferred channel</dt><dd>${pretty(p.preferred_channel)}</dd></div><div><dt>Effective</dt><dd>${dateText(p.effective_from)}</dd></div><div><dt>Proactive support consent</dt><dd>${pretty(p.consent_proactive_support_contact)}</dd></div><div><dt>Do not call</dt><dd>${p.do_not_call==='True'?'Yes':p.do_not_call==='False'?'No':pretty(p.do_not_call)}</dd></div></dl><p class="sub">Preference record only · no messages are sent.</p>${detail('Contact preference details',table(['Field','Recorded value'],[['SMS opt-in',pretty(p.sms_opt_in)],['Email opt-in',pretty(p.email_opt_in)],['Authorised representative',pretty(p.authorised_representative)],['Interpreter required',pretty(p.interpreter_required)]]))}</div>`:empty('Contact preference not recorded');
}
function weather(r){
  const f=r.forecast;
  if(!f)return panel('Weather context',`<div class="pad"><p>No matching issued forecast.</p><p class="sub">${eventLabel()} · ${dateText(state.date)}</p></div>`);
  const unit=f.magnitude_unit==='daily_max_temperature_c'?'°C':f.magnitude_unit==='maximum_gust_kmh'?'km/h':'mm';
  return panel('Issued weather scenario',`<div class="pad"><p>${badge(cutoff(state.date)>time(f.valid_to)?'Historical · validity ended':'Issued forecast')}</p><strong class="large-value">${num(+f.magnitude_central)} <small>${unit}</small></strong><p class="sub">${num(+f.magnitude_lower)}–${num(+f.magnitude_upper)} ${unit} · ${Math.round(+f.probability*100)}% event probability</p><dl class="facts"><div><dt>Valid</dt><dd>${dateText(f.valid_from)}–${dateText(f.valid_to)}</dd></div><div><dt>Issued</dt><dd>${dateText(f.issued_at)}</dd></div></dl><p class="sub">Fixed synthetic scenario · ${esc(f.forecast_id)}</p></div>`);
}
function financial(r){
  return r.prepaid?prepaid(r):billed(r);
}
function prepaid(r){
  const f=r.finance,e=r.depletion,rule=d.rules[r.reference];
  if(!f)return empty('Credit snapshot unavailable');
  return `<div class="grid"><div>${panel('Prepaid account',`<div class="metrics inner">${stat('Credit at 12:00 AWST',money(f.balance),esc(f.state))}${stat('Delivered use · past '+f.days+' days',num(f.kwh)+' kWh',money(f.cost)+' charged')}${stat('Emergency credit limit',money(+rule.emergency_credit_limit_cents),'Separate from balance')}</div><div class="chart"><h3>Completed daily delivered energy</h3>${chart(f.history.map(row=>({label:dateText(row.date).replace(' 2025',''),y:+row.import_kwh})),{label:'Delivered energy for completed days before the selected date',unit:' kWh'})}<p class="sub">${num(f.offHours)} recorded off-supply hours · completed AWST days only</p></div><div class="pad border-top"><h3>Illustrative credit coverage</h3>${e?`<strong class="large-value">${num(e.coverage)} days to $0</strong><p class="sub">${money(Math.max(0,f.balance))} ÷ ${money(e.average)} per day · ${e.days} complete on-supply days.</p>`:'<p class="sub">Unavailable · fewer than three complete on-supply days with positive spend.</p>'}<p class="sub">Recent charged spend held constant. No future top-ups or heat multiplier.</p></div>`)}${panel('Recorded top-ups · past 7 days',f.topups.length?table(['Posted','Amount','Source'],f.topups.map(row=>[stamp(row.datetime),money(+row.amount_cents),esc(row.topup_id)])):empty('No top-up recorded in this window'))}</div><div>${weather(r)}${panel('Current support',`<div class="pad"><p>${r.support.length} active arrangements</p><button class="text-button" data-jump="arrangements">Review arrangements →</button></div>`)}</div></div>`;
}
function billed(r){
  const b=r.billed,f=b.formula,change=b.estimate!==null&&b.baseline>0?(b.estimate/b.baseline-1)*100:null;
  const formula=!f?'Calculation unavailable: at least three completed usage days and documented rates required.':f.kind==='monthly'?`Recent mean: ${calc(f.dailyKwh)} kWh/day across ${f.days} complete days.<br>Projected month: ${calc(f.accrued)} kWh recorded + ${f.remaining} remaining days × ${calc(f.dailyKwh)} kWh/day = ${calc(f.projected)} kWh.<br>Estimated net bill: ${calc(f.projected)} × ${f.usageRate}¢ + ${f.last} days × (${f.supply}¢ supply − ${f.concession}¢ concession). Rounded to cents.`:`Recent mean: ${calc(f.dailyKwh)} kWh/day across ${f.days} complete days.<br>30-day gross charges: ${calc(f.dailyKwh)} × 30 × ${calc(f.usageRate)}¢/kWh + 30 × ${calc(f.supply)}¢ supply/day.<br>Comparison: latest bill's gross usage and supply charges normalised from ${f.periodDays} days to 30 days. Credits and future billing dates are not forecast.`;
  return `<div class="grid"><div>${panel('Billed account',`<div class="metrics inner">${stat(f?.kind==='monthly'?'Estimated current-month bill':'Estimated next 30-day gross',money(b.estimate),f?.kind==='monthly'?esc(state.date.slice(0,7))+' · scenario tariff':'Prior rates carried forward')}${stat(f?.kind==='monthly'?'Latest issued net bill':'Prior bill · 30-day gross',money(b.baseline),b.prior?'Issued '+dateText(b.prior.issue_date):'No prior issued bill')}${stat('Estimated change',change===null?'Unavailable':(change>0?'+':'')+num(change)+'%','Change does not establish affordability')}</div><div class="chart"><h3>Completed daily imported energy</h3>${chart(b.recent.map(row=>({label:dateText(row[0]).replace(' 2025',''),y:row[1]})),{label:'Measured daily usage used in billed estimate',unit:' kWh'})}</div>${detail('Inspect the calculation',`<p class="sub">${formula}</p><p class="sub">${b.override?'Canonical eight-account financial override.':'Retained base financial records.'} Weather is separate from this calculation.</p>`)}`)}${panel('Issued bills',b.bills.length?table(['Issued / due','Amount','Reference'],b.bills.slice(0,4).map(row=>[dateText(row.issue_date)+'<small>Due '+dateText(row.due_date)+'</small>',money(+row.amount_due_cents),esc(row.bill_id)])):empty('No bill issued as of this date'))}${panel('Cleared payments · past 90 days',`<div class="pad"><p>${b.payments.length} payments · ${money(b.payments.reduce((s,row)=>s+Number(row.amount_cents),0))}</p></div>`+(b.payments.length?table(['Payment date','Amount','Reference'],b.payments.slice().sort((a,b)=>time(b.date)-time(a.date)).slice(0,8).map(row=>[dateText(row.date),money(+row.amount_cents),esc(row.payment_id)])):empty('No cleared payments recorded')))}</div><div>${weather(r)}${panel('Already-issued account balance',`<div class="pad"><strong class="large-value">${money(b.outstanding)}</strong><p class="sub">${b.outstanding===null?'Bill-level allocation evidence unavailable.':'Issued bills less dated cleared payment allocations.'}</p></div>`)}</div></div>`;
}
function needs(r){
  const card=n=>`<article class="record"><div class="record-top"><h3>${pretty(n.need_type)}</h3>${badge(n.status,n.status==='current'?'attention':'neutral')}</div><p class="disclosure">${esc(n.support_summary)}</p><dl class="facts"><div><dt>Disclosed</dt><dd>${dateText(n.source_event_date)}</dd></div><div><dt>Review due</dt><dd>${dateText(n.review_due_date)}</dd></div></dl><p class="match">${esc(needWeatherMatch(d,r.customer,n,state.event,cutoff(state.date)))}</p><small class="muted">${esc(n.need_id)}</small></article>`;
  return `<div class="grid"><div>${panel('Current disclosed needs',r.activeNeeds.length?r.activeNeeds.map(card).join(''):empty('No current disclosed need recorded'))}${r.needs.some(n=>n.status!=='current')?panel('Retained history',r.needs.filter(n=>n.status!=='current').map(card).join('')):''}</div><div>${weather(r)}${panel('Preferred contact',preference(r))}</div></div>`;
}
function arrangements(r){
  const records=known(d.arrangements.filter(row=>row.customer_id===r.reference),'effective_from',cutoff(state.date)).sort((a,b)=>time(b.effective_from)-time(a.effective_from));
  const card=row=>`<article class="record"><div class="record-top"><h3>${pretty(row.arrangement_type)}</h3>${badge(row.status,row.status==='active'?'positive':'neutral')}</div><dl class="facts"><div><dt>Effective</dt><dd>${stamp(row.effective_from)}</dd></div><div><dt>Review due</dt><dd>${dateText(row.review_due_date)}${row.review_due_date&&time(row.review_due_date)<time(state.date)?' · date passed':''}</dd></div></dl><small class="muted">${esc(row.arrangement_id)}</small></article>`;
  return `<div class="grid"><div>${panel('Arrangement status at case date',r.arrangements.length?r.arrangements.map(card).join(''):empty('No arrangement recorded as of this date'))}${panel('Dated arrangement history',records.length?table(['Effective','Arrangement','Recorded state'],records.map(row=>[stamp(row.effective_from),pretty(row.arrangement_type),pretty(row.status)])):empty('No history recorded'))}</div><div>${panel('Review only',`<div class="pad"><p>Review dates and recorded plan states.</p><p class="sub">Agreed instalment amounts and schedules are not supplied. No missed-payment judgement is made.</p><button class="text-button" data-jump="credit">View financial context →</button></div>`)}</div></div>`;
}
function journey(r){
  const cases=customerCases(d,r.reference,cutoff(state.date));
  return panel('Recorded support progression',cases.length?cases.map(k=>{
    const latestDecision=k.decisions.slice().sort((a,b)=>time(b.decided_at)-time(a.decided_at))[0];
    const steps=[['Contact',k.contacts.some(row=>row.outcome==='reached')?'Reached':k.contacts.length?'Not reached':'Not recorded'],['Offer',k.offers.length?'Offered':'Not recorded'],['Acceptance',latestDecision?pretty(latestDecision.decision):'Not recorded'],['Delivery',k.deliveries.length?'Delivered':'Not recorded'],['Resolution',k.resolutions.length?'Customer confirmed':'Not recorded']];
    const events=[...k.contacts.map(row=>({at:row.occurred_at,title:`${row.direction==='inbound'?'Customer-initiated':'Outbound'} ${row.channel} contact`,value:row.outcome,id:row.contact_id})),...k.offers.map(row=>({at:row.offered_at,title:'Support offered',value:row.offer_type,id:row.offer_id})),...k.decisions.map(row=>({at:row.decided_at,title:'Customer decision',value:row.decision,id:row.decision_id})),...k.deliveries.map(row=>({at:row.delivered_at,title:'Support delivered',value:row.delivery_type,id:row.delivery_id})),...k.resolutions.map(row=>({at:row.resolved_at,title:'Resolution',value:row.resolution,id:row.resolution_id}))].sort((a,b)=>time(a.at)-time(b.at));
    return `<article class="record"><div class="record-top"><h3>${esc(k.case_id)}</h3>${badge(k.stage,k.resolutions.length?'positive':'neutral')}</div><p class="sub">${k.campaign_id?'Campaign '+esc(k.campaign_id):'Customer-initiated case'}</p><ol class="journey-steps">${steps.map(([label,status])=>`<li class="${status==='Not recorded'?'unknown':'recorded'}"><span>${label}</span><strong>${status}</strong></li>`).join('')}</ol><div class="timeline">${events.map(row=>`<div class="timeline-item"><h3>${esc(row.title)}</h3><p>${pretty(row.value)} · ${stamp(row.at)}</p><small>${esc(row.id)}</small></div>`).join('')}</div></article>`;
  }).join(''):empty('No support case recorded as of this date','Progression is unknown.'));
}
function campaign(){
  const f=funnelFor(d,state),count=Object.keys(f.groups).length;
  if(!f.campaign)return panel('Community campaign progression',empty('Campaign not created as of this date'));
  return panel('Community campaign progression',`<div class="pad"><p class="sub">${eventLabel()} · ${count} geographic audience accounts</p></div>`+(count?table(['Latest recorded stage','Distinct accounts'],f.rank.map(stage=>[esc(stage),String(Object.values(f.groups).filter(value=>value===stage).length)])):empty('No audience for this community')));
}
function eventLabel(){return $('#event').selectedOptions[0]?.textContent||state.event;}
function planning(){
  const t=cutoff(state.date),customers=d.customers.filter(c=>c.locality===state.community),c=customers[0];
  const plans=d.capacity.filter(row=>row.region===c.region&&time(row.issued_at)<=t).slice(0,+state.months);
  const outlook=d.outlook.filter(row=>row.locality===state.community&&time(row.issued_at)<=t),ctx=d.context.find(row=>row.postcode===c.postcode);
  const ids=new Set(customers.filter(row=>openAt(row,t)).map(row=>row.customer_id));
  const bills=known(d.bills.filter(row=>ids.has(row.customer_id)),'issue_date',t).filter(row=>time(row.issue_date)>=t-90*86400000);
  const contacts=known(d.contacts.filter(row=>ids.has(row.customer_id)),'occurred_at',t);
  const resolutions=known(d.resolutions.filter(row=>ids.has(row.customer_id)),'resolved_at',t);
  title('Community planning','Area context and issued seasonal assumptions · '+esc(state.community));
  return `<div class="planning-controls"><label>Community<select id="planning-community">${options([...new Set(d.customers.map(row=>row.locality))].sort().map(value=>[value,value]),state.community)}</select></label><label>Planning horizon<select id="planning-months">${options([['6','6 months'],['12','12 months']],state.months)}</select></label><span class="muted">January–${state.months==='6'?'June':'December'} 2025 · issued 1 January</span></div>
  <div class="planning-grid">${panel('Area map',`<div class="map"><div id="map-status" role="status">MapTiler basemap not configured</div><div id="map-live" hidden></div><div class="offline-map" aria-label="Area basemap unavailable" role="img"><span>Basemap unavailable</span></div><div class="map-caption">${esc(state.community)} · postcode ${esc(c.postcode)}</div></div>`)}${panel('Area context',`<div class="pad"><dl class="facts"><div><dt>Open scenario accounts</dt><dd>${ids.size}</dd></div><div><dt>Issued bills · 90 days</dt><dd>${bills.length} · ${money(bills.reduce((s,row)=>s+Number(row.amount_due_cents),0))}</dd></div><div><dt>Contact attempts since January</dt><dd>${contacts.length} · ${new Set(contacts.map(row=>row.customer_id)).size} accounts</dd></div><div><dt>Confirmed resolutions since January</dt><dd>${resolutions.length}</dd></div></dl></div>`)}</div>
  <div class="grid">${panel('Support review volume · '+esc(c.region),`<div class="chart"><p class="sub">Issued planning assumptions · central and lower–upper range</p>${chart(plans.map(row=>({label:new Date(time(row.valid_month+'-01')).toLocaleDateString('en-AU',{month:'short',timeZone:'Australia/Perth'}),y:+row.scenario_support_reviews_central,lower:+row.scenario_support_reviews_lower,upper:+row.scenario_support_reviews_upper})),{label:'Regional support review planning scenarios',range:true})}</div>${detail('Capacity assumptions',table(['Month','Reviews · lower / central / upper','Available minutes'],plans.map(row=>[esc(row.valid_month),`${row.scenario_support_reviews_lower} / ${row.scenario_support_reviews_central} / ${row.scenario_support_reviews_upper}`,num(+row.available_support_minutes_assumption)])))}<div class="panel-foot muted">${plans[0]?num(+plans[0].staff_fte_assumption)+' regional FTE · '+num(+plans[0].review_duration_minutes_assumption)+' minutes per review':'Capacity unavailable'}</div>`)}
  ${panel('2021 Census · postcode '+esc(c.postcode),ctx?`<div class="pad"><p class="sub">ABS POA2021 · real area statistics</p><dl class="facts"><div><dt>Population</dt><dd>${num(+ctx.population)}</dd></div><div><dt>Median weekly household income</dt><dd>${money(+ctx.Median_tot_hhd_inc_weekly*100)}</dd></div><div><dt>Average household size</dt><dd>${esc(ctx.Average_household_size)}</dd></div><div><dt>IRSD national decile</dt><dd>${esc(ctx.irsd_decile_australia)} / 10</dd></div></dl><p class="sub">Area measures describe the postcode population.</p></div>`:empty('Area context unavailable'))}</div>
  ${panel('Seasonal scenario · '+esc(state.community),`<div class="pad"><p class="sub">Probability of at least one event · issued assumptions and ranges. Historical climate observations unavailable.</p></div>`+table(['Month','Heatwave','Cyclone','Flood'],[...new Set(outlook.map(row=>row.valid_month))].slice(0,+state.months).map(month=>[esc(month),...['heatwave','cyclone','flood'].map(hazard=>{const row=outlook.find(row=>row.valid_month===month&&row.hazard_type===hazard);return row?`${Math.round(+row.probability_at_least_one_event*100)}%<small>${Math.round(+row.probability_lower*100)}–${Math.round(+row.probability_upper*100)}%</small>`:'Unavailable';})])))}${campaign()} `;
}
function initMap(){
  const host=$('#map-live'),fallback=$('.offline-map'),status=$('#map-status');
  if(!host||!window.maplibregl)return;
  const accounts=d.customers.filter(c=>c.locality===state.community);
  // Area viewport only; no individual customer marker or synthetic footprint layer.
  const center=[accounts.reduce((s,c)=>s+c.longitude,0)/accounts.length,accounts.reduce((s,c)=>s+c.latitude,0)/accounts.length];
  try{
    const map=new window.maplibregl.Map({container:host,center,zoom:11,style:{version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':'#edf2e6'}}]},attributionControl:false});
    activeMap=map;host.hidden=false;
    map.addControl(new window.maplibregl.NavigationControl({showCompass:false}),'top-right');
    map.addControl(new window.maplibregl.AttributionControl({compact:false}));
    map.on('load',()=>{if(activeMap!==map)return;map.resize();fallback.hidden=true;status.textContent='MapTiler basemap not configured';});
    map.on('error',()=>{if(activeMap!==map)return;host.hidden=true;fallback.hidden=false;status.textContent='Map unavailable';});
    resizeObserver=new ResizeObserver(()=>{if(activeMap===map)map.resize();});resizeObserver.observe(host);
  }catch{host.hidden=true;fallback.hidden=false;status.textContent='Map unavailable';}
}
function readState(){
  const q=new URLSearchParams(location.hash.slice(1));
  state={...DEFAULT,...REVIEW_DEFAULTS,...Object.fromEntries(q)};
  const communities=[...new Set(d.customers.map(c=>c.locality))];
  if(!communities.includes(state.community))state.community=DEFAULT.community;
  const c=d.customers.find(c=>c.customer_id===state.customer);
  if(!c)state.customer=DEFAULT.customer;
  if(!/^2025-(01|02|03)-\d\d$/.test(state.date)||!Number.isFinite(time(state.date))||new Date(time(state.date)+8*3600000).toISOString().slice(0,10)!==state.date||state.date>'2025-03-31')state.date=DEFAULT.date;
  if(!['review','overview','credit','needs','planning','arrangements','journey'].includes(state.view))state.view='review';
  if(!['HEAT01','HEAT02','CYCLONE01','FLOOD01'].includes(state.event))state.event='HEAT01';
  if(!['All communities',...communities].includes(state.scope))state.scope='All communities';
  if(!['all','prepaid','billed'].includes(state.account))state.account='all';
  if(!['all','financial','weather','needs','support'].includes(state.signal))state.signal='all';
  if(!['reference','community','account','reason','date','support','contact'].includes(state.sort))state.sort='reference';
  if(!['asc','desc'].includes(state.direction))state.direction='asc';
  if(!['6','12'].includes(state.months))state.months='12';
  state.page=String(Number.isFinite(+state.page)?Math.max(1,Math.floor(+state.page)):1);
}
function update(patch,{replace=false,focus=true}={}){
  const next={...state,...patch};
  if(Object.keys(next).every(key=>next[key]===state[key]))return;
  const changedView=next.view!==state.view;
  if(state.view==='review'&&changedView)queueScroll=window.scrollY;
  state=next;
  history[replace?'replaceState':'pushState'](null,'','#'+new URLSearchParams(state));
  render(focus);
  if(changedView)window.scrollTo(0,state.view==='review'?queueScroll:0);
}
function render(focus=false){
  resizeObserver?.disconnect();resizeObserver=null;if(activeMap){activeMap.remove();activeMap=null;}
  const detailView=!['review','planning'].includes(state.view),r=customerSummary();
  $('#date').value=state.date;$('#event').value=state.event;
  $('#breadcrumb').textContent='Customer support / '+(state.view==='planning'?'Community planning':detailView?'Customer review / '+r.reference:'Customer review');
  document.querySelectorAll('[data-workspace]').forEach(el=>el.setAttribute('aria-current',el.dataset.workspace===(state.view==='planning'?'planning':'review')?'page':'false'));
  $('#customer-tabs').hidden=!detailView;
  $('#customer-tabs').innerHTML=detailView?tabs.map(([id,label])=>`<button data-view="${id}"${state.view===id?' aria-current="page"':''}>${label}</button>`).join(''):'';
  $('#notice').innerHTML=detailView&&!r.open?'<div class="notice">Account closed at case time · historical records shown.</div>':'';
  if(detailView){
    const label=tabs.find(([id])=>id===state.view)[1];
    title(r.reference+' · '+label,`${esc(r.locality)} / ${esc(r.customer.region)} · ${r.account} · ${dateText(state.date)}`,`<button class="secondary" id="back-review">← Back to review</button>`);
    $('#content').innerHTML=({overview,credit:financial,needs,arrangements,journey}[state.view])(r);
  }else $('#content').innerHTML=state.view==='planning'?planning():queue();
  if(state.view==='planning')initMap();
  bindContent();
  if(focus)$('h1').focus({preventScroll:true});
}
function bindContent(){
  document.querySelectorAll('[data-customer]').forEach(el=>el.addEventListener('click',()=>{const c=d.customers.find(c=>c.customer_id===el.dataset.customer);update({customer:c.customer_id,community:c.locality,view:'overview'});}));
  document.querySelectorAll('[data-view],[data-jump]').forEach(el=>el.addEventListener('click',()=>update({view:el.dataset.view||el.dataset.jump})));
  document.querySelectorAll('[data-sort]').forEach(el=>el.addEventListener('click',()=>update({sort:el.dataset.sort,direction:state.sort===el.dataset.sort&&state.direction==='asc'?'desc':'asc',page:'1'},{focus:false})));
  document.querySelectorAll('[data-page]').forEach(el=>el.addEventListener('click',()=>update({page:el.dataset.page})));
  $('#review-filters')?.addEventListener('submit',e=>e.preventDefault());
  $('#search')?.addEventListener('input',e=>{const cursor=e.target.selectionStart;update({search:e.target.value,page:'1'},{replace:true,focus:false});$('#search').focus();$('#search').setSelectionRange(cursor,cursor);});
  for(const [selector,key] of [['#scope','scope'],['#account-filter','account'],['#signal-filter','signal']])$(selector)?.addEventListener('change',e=>update({[key]:e.target.value,page:'1'},{focus:false}));
  $('#clear-filters')?.addEventListener('click',()=>update({search:'',scope:'All communities',account:'all',signal:'all',page:'1'}));
  $('#back-review')?.addEventListener('click',()=>update({view:'review'}));
  $('#prepaid-example')?.addEventListener('click',()=>update({...DEFAULT,view:'overview'}));
  $('#billed-example')?.addEventListener('click',()=>update({community:'Halls Creek',customer:'C105019',date:'2025-03-07',event:'HEAT02',view:'credit'}));
  $('#planning-community')?.addEventListener('change',e=>update({community:e.target.value},{focus:false}));
  $('#planning-months')?.addEventListener('change',e=>update({months:e.target.value},{focus:false}));
}
async function init(){
  try{
    const response=await fetch('./scenario.json');if(!response.ok)throw Error('Scenario unavailable');d=await response.json();readState();render();
    $('#date').addEventListener('change',e=>{if(e.target.validity.valid&&e.target.value)update({date:e.target.value,page:'1'},{focus:false});else{e.target.value=state.date;$('#notice').innerHTML='<div class="notice">Choose a valid date from 1 January to 31 March 2025.</div>';}});
    $('#event').addEventListener('change',e=>update({event:e.target.value,page:'1'},{focus:false}));
    document.querySelectorAll('[data-workspace]').forEach(el=>el.addEventListener('click',()=>update({view:el.dataset.workspace})));
    $('#brand').addEventListener('click',e=>{e.preventDefault();update({view:'review'});});
    window.addEventListener('popstate',()=>{readState();render();});
  }catch{
    document.querySelectorAll('select,input,button').forEach(el=>el.disabled=true);
    $('#content').innerHTML='<div class="panel empty"><strong>Scenario data unavailable</strong>Start the local server and retry.<p><button class="secondary" id="retry">Retry loading data</button></p></div>';
    $('#retry').addEventListener('click',()=>location.reload());
  }
}
init();
