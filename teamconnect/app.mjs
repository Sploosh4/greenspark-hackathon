import {joinPoa2021Contexts} from './area-boundaries.mjs';
import {mlOutlookShell,initMlOutlook} from './ml-outlook-panel.mjs';
import {reviewInfo as customerReviewInfo,matchesReviewReason} from './review-reasons.mjs';
import {DEFAULT,time,cutoff,current,known,openAt,issuedForecasts,forecastFor,financeFor,depletionFor,billedFor,needWeatherMatch,customerCases,funnelFor,esc} from './core.mjs';

const HOME={...DEFAULT,view:'review'};
const VIEWS=['review','overview','credit','needs','arrangements','journey','planning'];
let d,state={...HOME},activeMap,activeMl;
let filters={search:'',reason:'',type:'',area:'',page:0};
const $=s=>document.querySelector(s);
const money=n=>new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(n/100);
const num=n=>new Intl.NumberFormat('en-AU',{maximumFractionDigits:1}).format(n);
const calc=n=>new Intl.NumberFormat('en-AU',{maximumFractionDigits:6}).format(n);
const pretty=s=>esc((String(s||'Not recorded')==='False'?'No':String(s)==='True'?'Yes':String(s||'Not recorded')).replaceAll('_',' '));
const dateText=s=>s?new Date(time(s)).toLocaleDateString('en-AU',{timeZone:'Australia/Perth',day:'numeric',month:'short',year:'numeric'}):'Not recorded';
const stamp=s=>s?esc(s.replace('T',' ').replace('+08:00','').slice(0,16))+' AWST':'Not recorded';
const empty=(title)=>`<div class="empty">${esc(title)}</div>`;
const typeFor=c=>d.rules[c.customer_id]?'Prepaid':'Billed';
const badge=(text,tone='')=>`<span class="status ${tone}">${pretty(text)}</span>`;
const status=s=>badge(s,['current','active','completed','resolved','Customer confirmed resolution','On supply'].includes(s)?'good':/awaiting|ongoing|undecided|Off supply/i.test(s)?'warn':'');
const dataList=rows=>`<dl class="data-list">${rows.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
const panel=(title,body,extra='')=>`<section class="panel pad ${extra}"><h2>${esc(title)}</h2>${body}</section>`;
function table(head,rows,extra=''){return `<div class="table-wrap ${extra}"><table><thead><tr>${head.map(h=>`<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
function needsAt(c,t){return current(d.needs.filter(r=>r.customer_id===c.customer_id),t).sort((a,b)=>time(b.source_event_date)-time(a.source_event_date));}
const permissionAt=(c,t)=>current(d.permissions.filter(r=>r.customer_id===c.customer_id),t)[0];
const supportAt=(c,t)=>current(d.arrangements.filter(r=>r.customer_id===c.customer_id),t).filter(r=>r.status==='active');
const reviewInfo=(c,t)=>customerReviewInfo(d,c,t);
const reviewNeedValues=info=>info.supportNeeds.length?info.supportNeeds.map(reason=>`<div>${pretty(reason)}</div>`).join(''):'Not recorded';
const reviewTriggerValues=info=>info.triggers.length?info.triggers.map(trigger=>`<div>${trigger.type==='case_opened'?`Support case opened${trigger.reason?' for '+pretty(trigger.reason):''}`:pretty(trigger.reason)+(trigger.type==='arrangement_review_due'?' review due':' recorded')} · ${dateText(trigger.recorded)}</div>`).join(''):'Not recorded';
const reviewReasonValues=info=>`<div><small>Review trigger</small>${reviewTriggerValues(info)}</div><div><small>Relevant support needs</small>${reviewNeedValues(info)}</div>`;
function shortWeather(c,need,t){
  const match=needWeatherMatch(d,c,need,state.event,t);
  if(match.startsWith('Heat-related'))return badge(match.includes('ended')?'Heat · historical forecast':'Heat · matched',match.includes('ended')?'':'warn');
  if(match.startsWith('Retained'))return badge('Retained history');
  if(match.startsWith('No matching'))return 'No matching forecast';
  return 'No specific match';
}
function weather(c,t){
  const f=forecastFor(d,c,state.event,t),v=issuedForecasts(d,state.event,t);
  if(!f)return panel('Weather context',badge(!openAt(c,t)?'Account closed':!v.length?'No forecast issued':'Outside forecast footprint')+`<div class="notice">${esc(c.locality)} · ${esc(state.event)}</div>`);
  const unit=f.magnitude_unit==='daily_max_temperature_c'?'°C':f.magnitude_unit==='maximum_gust_kmh'?'km/h':'mm';
  const label=t>time(f.valid_to)?'Historical forecast':t<time(f.valid_from)?'Before event':'Event window';
  return panel('Weather context',`<div class="weather-value">${num(+f.magnitude_central)} <small>${unit}</small></div><div class="weather-grid"><div><label>Scenario range</label><strong>${num(+f.magnitude_lower)}–${num(+f.magnitude_upper)} ${unit}</strong></div><div><label>Event probability</label><strong>${Math.round(+f.probability*100)}%</strong></div><div><label>Valid from</label><strong>${dateText(f.valid_from)}</strong></div><div><label>Valid to</label><strong>${dateText(f.valid_to)}</strong></div><div><label>Issued</label><strong>${dateText(f.issued_at)}</strong></div><div><label>Area</label><strong>${esc(c.locality)}</strong></div></div><div class="weather-status">${badge(label,t>time(f.valid_to)?'':'warn')}${badge('Synthetic forecast')}</div>`);
}
function reasonPanel(c,t){
  const info=reviewInfo(c,t);
  return panel('Reason for review',`<div class="record-context"><div><h3>Review trigger</h3><div class="record-value">${reviewTriggerValues(info)}</div></div><div><h3>Relevant support needs</h3><div class="record-value">${reviewNeedValues(info)}</div>${info.need?`<div class="notice">${status(info.need.status)}</div>`:''}</div></div>`);
}
function supportContextPanel(info){
  if(!info.reasons.length)return '';
  return panel('Recorded support context',`<div class="record-context">${info.reasons.map(reason=>{
    const records=info.needs.filter(r=>r.status==='current'&&r.need_type===reason);
    return `<div><h3>${pretty(reason)}</h3><div class="record-context">${records.length?records.map(r=>`<div><div class="record-value">${esc(r.support_summary?.trim()||'Not recorded')}</div><div class="sub">Recorded ${dateText(r.source_event_date)}</div></div>`).join(''):'<div class="record-value">Not recorded</div>'}</div></div>`;
  }).join('')}</div>`);
}
function review(){return `<div class="filters" role="search" aria-label="Review filters"><input id="review-search" class="search" type="search" aria-label="Search customer reference" placeholder="Search customer reference" value="${esc(filters.search)}"><select id="review-reason" aria-label="Review reason"><option value="">All review reasons</option><option value="financial">Financial disclosure</option><option value="needs">Other disclosed needs</option><option value="support">Support records</option></select><select id="review-type" aria-label="Account type"><option value="">All account types</option><option>Prepaid</option><option>Billed</option></select><select id="review-area" aria-label="Review area"><option value="">All areas</option>${[...new Set(d.customers.map(c=>c.locality))].sort().map(a=>`<option>${esc(a)}</option>`).join('')}</select></div><section class="panel"><div id="review-results"></div></section>`;}
function renderQueue(){
  const t=cutoff(state.date),items=d.customers.map(c=>({c,i:reviewInfo(c,t)})).filter(({c,i})=>i.inReview&&openAt(c,t)&&c.customer_id.toLowerCase().includes(filters.search.trim().toLowerCase())&&(!filters.area||c.locality===filters.area)&&(!filters.type||typeFor(c)===filters.type)&&matchesReviewReason(i,filters.reason))
    .sort((a,b)=>time(b.i.recorded)-time(a.i.recorded)||a.c.customer_id.localeCompare(b.c.customer_id));
  const pages=Math.max(1,Math.ceil(items.length/10));filters.page=Math.min(filters.page,pages-1);
  const rows=items.slice(filters.page*10,filters.page*10+10).map(({c,i})=>[
    `<button class="reference" data-customer="${esc(c.customer_id)}">${esc(c.customer_id)}</button><small>${esc(c.locality)} · ${typeFor(c)}</small>`,reviewReasonValues(i),dateText(i.recorded),i.arr.length?i.arr.map(r=>pretty(r.arrangement_type)+' '+status(r.status)).join('<br>'):i.stage?status(i.stage):'Not recorded',pretty(i.permission?.preferred_channel)
  ]);
  $('#review-results').innerHTML=(rows.length?table(['Customer reference','Reason for review','Recorded date','Current support','Contact method'],rows,'review-table'):empty('No matching review records'))+`<div class="pagination"><span>${items.length?`${filters.page*10+1}–${Math.min(items.length,filters.page*10+10)} of ${items.length}`:'0'} records</span><button id="queue-prev" ${filters.page===0?'disabled':''} aria-label="Previous page">Previous</button><span>${filters.page+1} / ${pages}</span><button id="queue-next" ${filters.page>=pages-1?'disabled':''} aria-label="Next page">Next</button></div>`;
  document.querySelectorAll('[data-customer]').forEach(el=>el.addEventListener('click',()=>{const c=d.customers.find(c=>c.customer_id===el.dataset.customer);update({customer:c.customer_id,community:c.locality,view:'overview'});}));
  $('#queue-prev').onclick=()=>{filters.page--;renderQueue();};$('#queue-next').onclick=()=>{filters.page++;renderQueue();};
}
function overview(c,t){
  const i=reviewInfo(c,t),p=i.permission;
  const support=i.arr.length?i.arr.map(r=>pretty(r.arrangement_type)+' '+status(r.status)).join('<br>'):i.stage?status(i.stage):'Not recorded';
  return `<div class="stack">${reasonPanel(c,t)}<div class="overview-grid">${panel('Recorded date',`<div class="record-value">${dateText(i.recorded)}</div>`)}${panel('Current support',support)}${panel('Preferred contact',`<div class="record-value">${pretty(p?.preferred_channel)}</div>${p?`<div class="notice">Effective ${dateText(p.effective_from)}</div>`:''}`)}</div>${panel('Supporting context',`<div class="grid">${dataList([['Area',esc(c.locality)],['Region',esc(c.region)],['Postcode',esc(c.postcode)],['Account opened',dateText(c.account_open_date)],['Account status',openAt(c,t)?status('Open'):status('Closed')]])}${dataList([['Proactive support consent',pretty(p?.consent_proactive_support_contact)],['Do not call',pretty(p?.do_not_call)],['Preference review',dateText(p?.review_due_date)],['Current disclosed needs',num(i.needs.filter(r=>r.status==='current').length)],['Known support cases',num(i.cases.length)]])}</div>`)}${supportContextPanel(i)}</div>`;
}
function accountHistory(c,t){
  const f=financeFor(d,c.customer_id,state.date);
  if(f)return panel('Account history',f.topups.length?table(['Top-up · AWST','Amount'],f.topups.map(r=>[stamp(r.datetime),money(+r.amount_cents)])):`${empty('No top-ups in the past 7 days')}`);
  const b=billedFor(d,c.customer_id,state.date);
  return panel('Account history',`<h3>Issued bills</h3>${b.bills.length?table(['Issued / due','Amount'],b.bills.slice(0,3).map(r=>[dateText(r.issue_date)+`<small>Due ${dateText(r.due_date)}</small>`,money(+r.amount_due_cents)])):empty('No issued bills')}<hr class="divider"><h3>Cleared payments · 90 days</h3>${b.payments.length?table(['Payment date','Amount'],b.payments.slice().sort((a,b)=>time(b.date)-time(a.date)).slice(0,8).map(r=>[dateText(r.date),money(+r.amount_cents)])):empty('No cleared payments recorded')}${b.outstanding!==null?`<div class="notice">Issued balance · ${money(b.outstanding)}</div>`:''}`);
}
function metric(label,value,detail=''){return `<div class="stat"><label>${esc(label)}</label><strong>${value}</strong><small>${detail}</small></div>`;}
function prepaid(c){
  const f=financeFor(d,c.customer_id,state.date),rule=d.rules[c.customer_id];
  if(!f)return panel('Payments and electricity use',empty('Credit snapshot unavailable'));
  const e=depletionFor(f);
  return panel('Payments and electricity use',`<div class="stat-grid">${metric('Credit · 12:00 AWST',money(f.balance),status(f.state))}${metric('Delivered use · 7 days',num(f.kwh)+' <small>kWh</small>',money(f.cost)+' charged')}${metric('Emergency credit',money(+rule.emergency_credit_limit_cents),'Separate limit')}</div><div class="chart">${chart(f.history.map(r=>({label:r.date.slice(8)+' '+new Date(time(r.date)).toLocaleDateString('en-AU',{month:'short',timeZone:'Australia/Perth'}),y:+r.import_kwh})),{label:'Delivered energy in completed days before the selected case date',unit:' kWh'})}</div><div class="legend"><span><i></i>Delivered energy · kWh</span><span>${num(f.offHours)} hours off supply</span><span>${f.days} complete days</span></div><hr class="divider">${dataList([['Illustrative days to $0',e?num(e.coverage)+' days':badge('Unavailable · insufficient on-supply days')]])}<details class="calculation"><summary>Calculation</summary>${e?dataList([['Recorded credit',money(Math.max(0,f.balance))],['Mean daily charged spend',money(e.average)],['Complete on-supply days',num(e.days)],['Days to $0',`${money(Math.max(0,f.balance))} ÷ ${money(e.average)} = ${num(e.coverage)}`]]):dataList([['Minimum on-supply observations','3 complete days'],['Available',num(f.history.filter(r=>+r.disconnected_hours===0).length)]])}<div class="notice">Recent spend · no further top-ups · no weather multiplier</div></details>`);
}
function billed(c){
  const b=billedFor(d,c.customer_id,state.date),f=b.formula,change=b.estimate!==null&&b.baseline>0?(b.estimate/b.baseline-1)*100:null;
  const formula=f?f.kind==='monthly'?[['Mean daily use',`${calc(f.dailyKwh)} kWh · ${f.days} days`],['Recorded month-to-date',`${calc(f.accrued)} kWh · ${f.completed} days`],['Remaining days',num(f.remaining)],['Projected use',`${calc(f.accrued)} + ${f.remaining} × ${calc(f.dailyKwh)} = ${calc(f.projected)} kWh`],['Usage rate',`${f.usageRate}¢/kWh`],['Supply / concession',`${f.supply}¢ / ${f.concession}¢ per day`],['Estimated bill',money(b.estimate)]]:[['Mean daily use',`${calc(f.dailyKwh)} kWh · ${f.days} days`],['Projected 30-day use',`${calc(f.projected)} kWh`],['Usage rate',`${calc(f.usageRate)}¢/kWh`],['Daily supply',`${calc(f.supply)}¢`],['Prior bill period',`${f.periodDays} days`],['Gross estimate',money(b.estimate)],['Prior 30-day gross',money(b.baseline)]]:[];
  return panel('Payments and electricity use',`<div class="stat-grid">${metric(f?.kind==='monthly'?'Estimated month bill':'30-day gross estimate',b.estimate===null?'Unavailable':money(b.estimate),f?.kind==='monthly'?state.date.slice(0,7):'Before credits')}${metric(f?.kind==='monthly'?'Latest issued bill':'Prior 30-day gross',b.baseline===null?'Unavailable':money(b.baseline),b.prior?'Issued '+dateText(b.prior.issue_date):'No issued bill')}${metric('Estimated change',change===null?'Unavailable':(change>0?'+':'')+num(change)+'%','Not an affordability assessment')}</div><div class="chart">${chart(b.recent.map(r=>({label:r[0].slice(8),y:r[1]})),{label:'Completed billed-customer usage used in the transparent estimate',unit:' kWh'})}</div><div class="legend"><span><i></i>Imported energy · kWh</span><span>${b.recent.length} completed days</span></div><details class="calculation"><summary>Calculation</summary>${f?dataList(formula):empty('At least 3 usage days and rate inputs required')}<div class="notice">${b.override?'Demonstration tariff':'Prior bill rates · gross charges'} · no weather multiplier</div></details>`);
}
function credit(c,t){return `<div class="segmented" aria-label="Financial examples"><button id="prepaid-example" aria-pressed="${!!d.rules[c.customer_id]}">Prepaid</button><button id="billed-example" aria-pressed="${!d.rules[c.customer_id]}">Billed</button></div><div class="grid"><div class="stack">${d.rules[c.customer_id]?prepaid(c):billed(c)}${reasonPanel(c,t)}</div><div class="stack">${weather(c,t)}${accountHistory(c,t)}</div></div>`;}
function needs(c,t){
  const active=needsAt(c,t),p=permissionAt(c,t);
  return `<div class="stack"><section class="panel">${active.length?table(['Disclosed need','Recorded date','Current status','Relevant weather'],active.map(r=>[pretty(r.need_type),dateText(r.source_event_date),status(r.status),shortWeather(c,r,t)])):empty('No disclosed need recorded as of this date')}</section>${panel('Recorded support context',active.length?`<div class="record-context">${active.map(r=>`<div><div class="record-value">${esc(r.support_summary)}</div><div class="sub">${esc(r.need_id)} · Review ${dateText(r.review_due_date)}${r.review_due_date&&time(r.review_due_date)<time(state.date)?' · '+badge('Review overdue','warn'):''}</div></div>`).join('')}</div>`:empty('No recorded support context'))}<div class="grid">${panel('Current support',supportAt(c,t).length?dataList(supportAt(c,t).map(r=>[r.arrangement_type.replaceAll('_',' '),status(r.status)])):empty('No arrangement recorded'))}${panel('Contact preferences',dataList([['Preferred channel',pretty(p?.preferred_channel)],['Proactive support consent',pretty(p?.consent_proactive_support_contact)],['Do not call',pretty(p?.do_not_call)],['Effective',dateText(p?.effective_from)],['Review due',dateText(p?.review_due_date)]]))}</div></div>`;
}
function arrangements(c,t){
  const all=known(d.arrangements.filter(r=>r.customer_id===c.customer_id),'effective_from',t).sort((a,b)=>time(b.effective_from)-time(a.effective_from)),active=current(all,t);
  return `<div class="stack"><section class="panel">${active.length?table(['Arrangement','Status','Last reviewed','Review due'],active.map(r=>[pretty(r.arrangement_type),status(r.status),dateText(r.last_review_date),dateText(r.review_due_date)+(r.review_due_date&&time(r.review_due_date)<time(state.date)?`<small>${badge('Review overdue','warn')}</small>`:'')])):empty('No arrangement recorded as of this date')}</section><div class="grid">${panel('Recent account activity',all.length?table(['Effective · AWST','Arrangement','Status'],all.map(r=>[stamp(r.effective_from),pretty(r.arrangement_type),status(r.status)])):empty('No arrangement history'))}${weather(c,t)}</div>${accountHistory(c,t)}</div>`;
}
function journey(c,t){
  const cases=customerCases(d,c.customer_id,t);
  if(!cases.length)return `<section class="panel">${empty('No support case opened as of this date')}</section>`;
  return `<div class="stack">${cases.map(k=>{
    const events=[...k.contacts.map(r=>({at:r.occurred_at,title:r.direction==='inbound'?'Customer contact':'Outbound contact',outcome:pretty(r.outcome)+' · '+pretty(r.channel),id:r.contact_id})),...k.offers.map(r=>({at:r.offered_at,title:'Offer to help',outcome:pretty(r.offer_type),id:r.offer_id})),...k.decisions.map(r=>({at:r.decided_at,title:'Customer decision',outcome:pretty(r.decision),id:r.decision_id})),...k.deliveries.map(r=>({at:r.delivered_at,title:'Delivered',outcome:pretty(r.delivery_type),id:r.delivery_id})),...k.resolutions.map(r=>({at:r.resolved_at,title:'Resolved',outcome:'Customer confirmed',id:r.resolution_id}))].sort((a,b)=>time(a.at)-time(b.at));
    const steps=[['Contacted',k.contacts.some(r=>r.outcome==='reached')],['Offer to help',k.offers.length],['Accepted',k.decisions.some(r=>r.decision==='accepted')],['Delivered',k.deliveries.length],['Resolved',k.resolutions.length]];
    return `<section class="panel pad"><div class="section-head"><h2>Support journey</h2>${status(k.stage)}</div><div class="case-id">${esc(k.case_id)} · ${k.campaign_id?esc(k.campaign_id):'Customer initiated'}</div><div class="journey-steps">${steps.map(([l,done])=>`<div class="step ${done?'done':''}">${esc(l)}<small>${done?'Recorded':'Not recorded'}</small></div>`).join('')}</div></section><section class="panel">${table(['Stage','Date · AWST','Outcome','Follow-up'],events.map(r=>[esc(r.title),stamp(r.at),r.outcome, r.title==='Delivered'?supportAt(c,t).map(a=>dateText(a.review_due_date)).join('<br>')||'Not recorded':'—']))}</section>`;
  }).join('')}</div>`;
}
function campaign(c,t){
  const f=funnelFor(d,state),count=Object.keys(f.groups).length;
  return panel('Community support',!f.campaign?empty('Campaign not created as of this date'):!count?empty('No campaign audience in this area'):`${dataList([['Geographic audience',num(count)],['Campaign',esc(f.campaign.campaign_id)]])}${f.rank.map(stage=>{const n=Object.values(f.groups).filter(s=>s===stage).length;return `<div class="funnel-row"><span>${esc(stage)}</span><div class="funnel-bar"><i style="width:${n/count*100}%"></i></div><span>${n}</span></div>`;}).join('')}<div class="notice">Distinct customers · latest known stage</div>`);
}
function planning(c,t){
  const period=state.period==='q1'?'q1':'annual',hazard=['heatwave','cyclone','flood'].includes(state.hazard)?state.hazard:'all';
  const plans=d.capacity.filter(r=>r.region===c.region&&time(r.issued_at)<=t&&(period==='annual'||r.valid_month<='2025-03'));
  const outlook=d.outlook.filter(r=>r.locality===c.locality&&time(r.issued_at)<=t&&(period==='annual'||r.valid_month<='2025-03'));
  const ctx=d.context.find(r=>r.postcode===c.postcode),hazards=hazard==='all'?['heatwave','cyclone','flood']:[hazard];
  const ids=new Set(d.customers.filter(r=>r.locality===c.locality).map(r=>r.customer_id));
  const bills=known(d.bills.filter(r=>ids.has(r.customer_id)),'issue_date',t).filter(r=>time(r.issue_date)>=t-90*86400000),contacts=known(d.contacts.filter(r=>ids.has(r.customer_id)),'occurred_at',t),resolved=known(d.resolutions.filter(r=>ids.has(r.customer_id)),'resolved_at',t);
  return `<div class="planning-filters"><label>Planning period<select id="planning-period"><option value="annual" ${period==='annual'?'selected':''}>2025 · annual</option><option value="q1" ${period==='q1'?'selected':''}>2025 · January–March</option></select></label><label>Climate hazard<select id="planning-hazard"><option value="all">All hazards</option>${['heatwave','cyclone','flood'].map(h=>`<option value="${h}" ${hazard===h?'selected':''}>${pretty(h)}</option>`).join('')}</select></label><label>View<select id="planning-view"><option value="map">Area map</option><option value="ml">Temperature outlook (ML)</option><option value="capacity">Monthly planning</option></select></label></div><div class="stack"><div class="planning-grid">${panel('Area view',map(c))}<div class="stack">${panel('Postcode context',ctx?dataList([['Selected community',esc(c.locality)],['Postcode',esc(c.postcode)],['Population',num(+ctx.population)],['Household size',esc(ctx.Average_household_size)],['Weekly household income',money(+ctx.Median_tot_hhd_inc_weekly*100)],['IRSD national decile',esc(ctx.irsd_decile_australia)+' / 10']])+`<div class="notice">ABS 2021 · ${esc(ctx.context_geography)} · area statistics</div>`:empty('Area context unavailable'))}${panel('Seasonal outlook',table(['Month',...hazards.map(h=>h[0].toUpperCase()+h.slice(1))],[...new Set(outlook.map(r=>r.valid_month))].map(month=>[esc(month),...hazards.map(h=>{const r=outlook.find(r=>r.valid_month===month&&r.hazard_type===h);return r?`${Math.round(+r.probability_at_least_one_event*100)}%<small>${Math.round(+r.probability_lower*100)}–${Math.round(+r.probability_upper*100)}%</small>`:'Unavailable';})]))+`<div class="notice">Issued scenario · 1 Jan 2025 · no historical observations</div>`,'seasonal-outlook')}</div></div>${mlOutlookShell(c)}<div id="monthly-planning" class="grid">${panel('Monthly support reviews',`<div class="chart">${chart(plans.map(r=>({label:new Date(time(r.valid_month+'-01')).toLocaleDateString('en-AU',{month:'short',timeZone:'Australia/Perth'}),y:+r.scenario_support_reviews_central,lower:+r.scenario_support_reviews_lower,upper:+r.scenario_support_reviews_upper})),{label:'Monthly review volume scenario with lower and upper ranges',range:true})}</div><div class="legend"><span><i></i>Central scenario</span><span><i class="light"></i>Lower–upper range</span></div><div class="capacity-meta"><span>${esc(c.region)}</span><span>Staff assumption · <strong>${plans[0]?num(+plans[0].staff_fte_assumption)+' FTE':'Unavailable'}</strong></span><span>Review · <strong>${plans[0]?num(+plans[0].review_duration_minutes_assumption)+' min':'Unavailable'}</strong></span></div>${table(['Month','Lower / central / upper','Available min'],plans.map(r=>[esc(r.valid_month),`${r.scenario_support_reviews_lower} / ${r.scenario_support_reviews_central} / ${r.scenario_support_reviews_upper}`,num(+r.available_support_minutes_assumption)]))}`)}<div class="stack">${panel('Community account history',dataList([['Issued bills · last 90 days',num(bills.length)],['Billed customers',num(new Set(bills.map(r=>r.customer_id)).size)],['Total issued',money(bills.reduce((s,r)=>s+Number(r.amount_due_cents),0))],['Contact attempts · year to date',num(contacts.length)],['Customers contacted',num(new Set(contacts.map(r=>r.customer_id)).size)],['Confirmed resolutions',num(resolved.length)]]))}${campaign(c,t)}</div></div></div>`;
}
function readState(){
  const q=new URLSearchParams(location.hash.slice(1));state={...HOME,...Object.fromEntries(q)};
  const communities=[...new Set(d.customers.map(c=>c.locality))];
  if(!communities.includes(state.community))state.community=HOME.community;
  if(!d.customers.some(c=>c.customer_id===state.customer&&c.locality===state.community))state.customer=d.customers.find(c=>c.locality===state.community).customer_id;
  if(!/^2025-(01|02|03)-\d\d$/.test(state.date)||!Number.isFinite(time(state.date))||new Date(time(state.date)+8*3600000).toISOString().slice(0,10)!==state.date||state.date>'2025-03-31')state.date=HOME.date;
  if(!VIEWS.includes(state.view))state.view='review';
  if(!['HEAT01','HEAT02','CYCLONE01','FLOOD01'].includes(state.event))state.event='HEAT01';
}
function update(patch,replace=false){state={...state,...patch};history[replace?'replaceState':'pushState'](null,'','#'+new URLSearchParams(state).toString());render();}
function render(){
  const c=d.customers.find(c=>c.customer_id===state.customer),t=cutoff(state.date),detail=!['review','planning'].includes(state.view);
  $('#page-title').textContent=detail?'Customer details':state.view==='review'?'Customer review':'Community planning';
  document.title= (detail?({overview:'Customer overview',credit:'Financial pressure',needs:'Disclosed needs',arrangements:'Arrangements',journey:'Support journey'}[state.view]):$('#page-title').textContent)+' · Team Connect';
  $('#community').innerHTML=[...new Set(d.customers.map(c=>c.locality))].sort().map(v=>`<option ${v===state.community?'selected':''}>${esc(v)}</option>`).join('');
  $('#customer').innerHTML=d.customers.filter(c=>c.locality===state.community).map(c=>`<option value="${c.customer_id}" ${c.customer_id===state.customer?'selected':''}>${c.customer_id} · ${typeFor(c)}</option>`).join('');
  $('#date').value=state.date;$('#event').value=state.event;
  $('#area-control').hidden=state.view==='review';$('#customer-control').hidden=!detail;
  $('.context').classList.toggle('compact',state.view==='review');
  $('#account-meta').hidden=!detail;$('#account-meta').innerHTML=`<span>Customer reference<strong>${esc(c.customer_id)}</strong></span><span>Account type<strong>${typeFor(c)}</strong></span><span>Area<strong>${esc(c.locality)}</strong></span>`;
  $('#back-review').hidden=!detail;$('.tabs').hidden=!detail;
  document.querySelectorAll('[data-view]').forEach(el=>el.setAttribute('aria-current',el.dataset.view===state.view?'page':'false'));
  document.querySelectorAll('[data-section]').forEach(el=>el.setAttribute('aria-current',(el.dataset.section==='planning'?state.view==='planning':state.view!=='planning')?'page':'false'));
  if(activeMap){activeMap.remove();activeMap=null;}
  if(activeMl){activeMl.remove();activeMl=null;}
  $('#notice').innerHTML=detail&&!openAt(c,t)?'<div class="banner">Account closed at this date · historical records</div>':'';
  $('#content').innerHTML=({review,overview,credit,needs,arrangements,journey,planning}[state.view])(c,t);$('#content').setAttribute('aria-busy','false');
  if(state.view==='planning'){
    initMap(c,t);
    // ML outlook controls change only that panel: keep them in the URL without re-rendering both maps
    activeMl=initMlOutlook(c,state,patch=>{state={...state,...patch};history.replaceState(null,'','#'+new URLSearchParams(state).toString());});
    $('#planning-period').onchange=e=>update({period:e.target.value});
    $('#planning-hazard').onchange=e=>update({hazard:e.target.value});
    $('#planning-view').onchange=e=>{const target={capacity:'#monthly-planning',ml:'#ml-outlook'}[e.target.value];(target?$(target):$('#map-live').closest('.panel')).scrollIntoView({block:'start',behavior:'instant'});};
  }
  if(state.view==='review'){
    for(const [selector,key,event] of [['#review-search','search','input'],['#review-reason','reason','change'],['#review-type','type','change'],['#review-area','area','change']]){
      $(selector).value=filters[key];$(selector).addEventListener(event,e=>{filters[key]=e.target.value;filters.page=0;renderQueue();});
    }
    renderQueue();
  }
  const prepaidButton=$('#prepaid-example'),billedButton=$('#billed-example');
  if(prepaidButton)prepaidButton.onclick=()=>{if(!d.rules[c.customer_id])update({...DEFAULT,view:'credit'});};
  if(billedButton)billedButton.onclick=()=>{if(d.rules[c.customer_id])update({community:'Halls Creek',customer:'C105019',date:'2025-03-07',event:'HEAT02',view:'credit'});};
}
async function init(){
  try{
    const response=await fetch('./scenario.json');if(!response.ok)throw Error('Scenario unavailable');d=await response.json();readState();render();
    $('#community').addEventListener('change',e=>{const community=e.target.value;update({community,customer:d.customers.find(c=>c.locality===community).customer_id});});
    $('#customer').addEventListener('change',e=>update({customer:e.target.value}));
    $('#date').addEventListener('change',e=>{if(e.target.validity.valid&&e.target.value)update({date:e.target.value});else{e.target.value=state.date;$('#notice').innerHTML='<div class="banner">Select 1 January–31 March 2025</div>';}});
    $('#event').addEventListener('change',e=>update({event:e.target.value}));
    document.querySelectorAll('[data-view]').forEach(el=>el.addEventListener('click',()=>{if(state.view!==el.dataset.view)update({view:el.dataset.view});}));
    document.querySelectorAll('[data-section]').forEach(el=>el.addEventListener('click',()=>{if(state.view!==el.dataset.section)update({view:el.dataset.section});}));
    $('#back-review').onclick=()=>update({view:'review'});
    const reset=()=>{filters={search:'',reason:'',type:'',area:'',page:0};state={...HOME};update({});};
    $('#reset').onclick=reset;$('#brand').onclick=e=>{e.preventDefault();reset();};
    window.addEventListener('popstate',()=>{readState();render();});
  }catch(error){
    console.error('Demo initialisation failed',error);
    document.querySelectorAll('select,input,nav button,#reset').forEach(el=>el.disabled=true);
    $('#content').setAttribute('aria-busy','false');$('#content').innerHTML='<div class="panel empty"><strong>Scenario data unavailable</strong><button class="secondary" id="retry">Retry</button></div>';
    $('#retry').onclick=()=>location.reload();
  }
}
function chart(values,{label,range=false,unit='',dates=null}={}){if(!values.length)return empty('No completed observations','The selected date has no completed days in this window.');const max=Math.max(...values.map(v=>v.upper??v.y),1)*1.2,w=660,h=220,x=i=>45+i*(w-75)/Math.max(1,values.length-1),y=v=>h-35-v/max*(h-60),path=values.map((v,i)=>`${i?'L':'M'}${x(i)},${y(v.y)}`).join(' ');let band=range?`<path class="band" d="${values.map((v,i)=>`${i?'L':'M'}${x(i)},${y(v.upper)}`).join(' ')} ${values.map((v,i)=>[v,i]).reverse().map(([v,i])=>`L${x(i)},${y(v.lower)}`).join(' ')} Z"/>`:'';return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title>${[0,.5,1].map(f=>`<line class="gridline" x1="45" x2="${w-20}" y1="${y(max*f)}" y2="${y(max*f)}"/><text x="34" y="${y(max*f)+3}" text-anchor="end">${num(max*f)}</text>`).join('')}${band}<path class="line" d="${path}"/>${values.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v.y)}" r="3.5" fill="#317b76"><title>${esc(v.label)}: ${num(v.y)}${unit}${range?` (${num(v.lower)}–${num(v.upper)})`:''}</title></circle><text x="${x(i)}" y="${h-12}" text-anchor="middle">${esc(v.label)}</text>`).join('')}</svg>`;}
function map(c){
  return `<div class="map"><div class="map-toolbar"><span id="map-status" role="status">Loading basemap…</span><button class="secondary" id="map-centre" type="button">Centre area</button></div><div class="map-error" id="map-error" role="alert" hidden><span id="map-error-message">Basemap unavailable</span><button class="secondary" id="map-retry" type="button">Retry map</button></div><div id="map-live" data-map-state="loading" aria-label="Map of ${esc(c.locality)}"></div><div class="map-legend" aria-label="Map layers"><label><input type="checkbox" id="map-area-layer" checked><i class="real-area"></i><span id="map-area-label">ABS postcode · POA 2021</span></label></div></div>`;
}
let boundaryDataPromise;
function getAreaBoundaries(){
  if(!boundaryDataPromise)boundaryDataPromise=fetch('./geography/poa2021.geojson').then(response=>{
    if(!response.ok)throw Error('Area unavailable');return response.json();
  }).catch(error=>{boundaryDataPromise=null;throw error;});
  return boundaryDataPromise;
}
function initMap(c,t){
  const host=$('#map-live');if(!host)return;
  const errorBox=$('#map-error'),message=$('#map-error-message'),retry=$('#map-retry'),label=$('#map-status');
  const fail=()=>{
    if(!host.isConnected)return;
    host.dataset.mapState='error';label.textContent='Basemap unavailable';
    errorBox.hidden=false;message.textContent='Map could not load';
  };
  retry.onclick=()=>{if(activeMap){activeMap.remove();activeMap=null;}if(window.maplibregl)initMap(c,t);else location.reload();};
  if(!window.maplibregl){fail();return;}
  errorBox.hidden=true;delete host.dataset.mapError;host.dataset.mapState='loading';label.textContent='Loading basemap…';
  let m,resizeObserver,timeout,hasError=false,overlaysReady=false,matchedBoundaryCount=0;
  try{
    const centre=[Number(c.longitude),Number(c.latitude)],zoom=c.locality==='South Hedland'?10.5:12;
    m=new window.maplibregl.Map({container:host,center:centre,zoom,style:'/maptiler/maps/streets-v4/style.json?demo_v=1',attributionControl:false,renderWorldCopies:false});
    activeMap=m;
    m.addControl(new window.maplibregl.NavigationControl({showCompass:false}),'top-right');
    m.addControl(new window.maplibregl.AttributionControl({compact:false}),'bottom-right');
    m.addControl({onAdd(){
      const link=document.createElement('a');link.className='maplibregl-ctrl maptiler-logo';link.href='https://www.maptiler.com/';link.target='_blank';link.rel='noopener';
      const logo=document.createElement('img');logo.src='vendor/maptiler-logo.svg';logo.alt='MapTiler';logo.width=67;logo.height=20;link.append(logo);return link;
    },onRemove(){}},'bottom-left');
    $('#map-centre').onclick=()=>{m.resize();m.easeTo({center:centre,zoom,duration:250});};
    const layers=[['#map-area-layer',['real-area-fill','real-area-line']]];
    const applyVisibility=()=>{
      for(const [control,ids] of layers)for(const id of ids)if(m.getLayer(id))m.setLayoutProperty(id,'visibility',$(control).checked?'visible':'none');
    };
    for(const [control] of layers)$(control).onchange=applyVisibility;
    resizeObserver=new ResizeObserver(()=>{if(activeMap===m&&host.clientWidth&&host.clientHeight)m.resize();});resizeObserver.observe(host);
    requestAnimationFrame(()=>{if(activeMap===m)m.resize();});
    timeout=setTimeout(()=>{if(activeMap===m&&host.dataset.mapState!=='ready'){hasError=true;fail();}},30000);
    m.on('remove',()=>{resizeObserver?.disconnect();clearTimeout(timeout);});
    m.on('error',event=>{if(activeMap===m){host.dataset.mapError=String(event.error?.message||'Map resource failed').replace(/key=[^&\s]+/g,'key=redacted').slice(0,240);hasError=true;fail();}});
    m.on('load',async()=>{
      if(activeMap!==m)return;
      const before=m.getStyle().layers.find(layer=>layer.type==='symbol')?.id;
      try{
        const data=await getAreaBoundaries();if(activeMap!==m)return;
        const matches=joinPoa2021Contexts(d.context,data).filter(match=>match.context.postcode===c.postcode);
        if(matches.length===1){
          const {context,boundary}=matches[0];matchedBoundaryCount=1;
          m.addSource('real-area',{type:'geojson',data:{type:'FeatureCollection',features:[boundary]},attribution:'© Commonwealth of Australia (<a href="https://www.abs.gov.au/">ABS</a>) · POA 2021 · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>'});
          m.addLayer({id:'real-area-fill',type:'fill',source:'real-area',paint:{'fill-color':'#326a9e','fill-opacity':.045}},before);
          m.addLayer({id:'real-area-line',type:'line',source:'real-area',paint:{'line-color':'#326a9e','line-width':2}},before);
          $('#map-area-label').textContent='Postcode '+context.postcode+' · ABS POA 2021';
          host.dataset.boundaryCode=context.postcode;host.dataset.boundaryGeography=data.geography;
          host.dataset.statisticsGeography=context.context_geography;host.dataset.boundaryYear=String(data.reference_year);
        }else{
          $('#map-area-label').textContent='Postcode boundary unavailable';$('#map-area-layer').checked=false;$('#map-area-layer').disabled=true;
        }
      }catch(error){if(activeMap===m)$('#map-area-label').textContent='ABS area unavailable';}
      if(activeMap!==m)return;
      applyVisibility();overlaysReady=true;m.resize();
    });
    m.on('idle',()=>{
      if(activeMap!==m||hasError||!overlaysReady||!m.isStyleLoaded()||!m.areTilesLoaded())return;
      const features=m.queryRenderedFeatures(),base=features.filter(feature=>feature.source!=='real-area');
      if(!base.length)return;
      clearTimeout(timeout);host.dataset.mapState='ready';label.textContent='MapTiler Streets · '+c.locality;
      host.dataset.basemapFeatures=String(base.length);
      host.dataset.renderedRoads=String(base.filter(feature=>/road|street|transport/i.test(feature.sourceLayer||feature.layer.id)).length);
      host.dataset.renderedLabels=String(base.filter(feature=>feature.layer.type==='symbol').length);
      host.dataset.centre=JSON.stringify(m.getCenter().toArray());host.dataset.zoom=String(m.getZoom());
      host.dataset.boundaryFeatures=String(matchedBoundaryCount);
      host.dataset.canvasSize=JSON.stringify([m.getCanvas().clientWidth,m.getCanvas().clientHeight]);
      host.dataset.overlaySources=JSON.stringify(Object.keys(m.getStyle().sources).filter(source=>source==='real-area'||/synthetic|scenario|customer/.test(source)));
      host.dataset.overlayLayers=JSON.stringify(m.getStyle().layers.filter(layer=>layer.source==='real-area'||/synthetic|scenario|customer/.test(layer.id)).map(layer=>layer.id));
    });
  }catch(error){hasError=true;resizeObserver?.disconnect();clearTimeout(timeout);fail();}
}

init();
