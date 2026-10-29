import {DEFAULT_FILTERS,esc,dateLabel,pct,summary,query,prepareQuery,pageRows,explanation,exportRows,days,windowLabel} from './core.mjs';
const $=s=>document.querySelector(s);
const fmt=n=>n===null?'Unavailable':Number(n.toFixed(1)).toLocaleString('en-AU');
const money=n=>n===null||n===''||n===undefined?'Unavailable':new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(+n);
const badge=(s,t='')=>`<span class="status ${t}">${esc(s)}</span>`;
let demo,uploaded=null,mode='demo',view='review',selected=null,filters={...DEFAULT_FILTERS},range='recent',previewState='normal',role='Officer',staged=false;
let selectedCustomers=new Set();
let uploadState={revision:'none',active_batch:null},requestToken='',uploadBusy=false,uploadError='',pendingUpload=null,uploadAbort=null,uploadOperation=null;
let uploadRefreshGeneration=0;
let liveWeather=null,liveWeatherError='',liveWeatherGeneration=0;
let sessionCsrf='',realSession=null;
let managerSettings=null,settingsError='';
let uploadJobPending=false,uploadAttemptGeneration=0;
const preparedSummaries=new WeakMap();let queuePage=0;
const performanceMode=new URLSearchParams(location.search).get('performance_fixture')==='50000',performanceSamples=[];
let performanceDetailTemplate=null;
let customerOpenGeneration=0;
function measureUI(name,action){
  const start=performance.now();action();
  if(performanceMode)requestAnimationFrame(()=>requestAnimationFrame(()=>{performanceSamples.push({name,seconds:(performance.now()-start)/1000});$('#performance-metrics').textContent=JSON.stringify(performanceSamples);}));
}
async function openCustomer(id){
  const start=performance.now(),generation=++customerOpenGeneration,d=data(),row=d.customers.find(r=>r.customer.customer_id===id);
  if(!row){toast('Customer unavailable in this data version');return;}
  if(performanceMode&&!row.detail_loaded){
    if(!performanceDetailTemplate){const response=await fetch('tests/performance-detail-template.json');if(!response.ok){toast('Performance history fixture unavailable');return;}performanceDetailTemplate=await response.json();}
    row.usage=performanceDetailTemplate.usage;row.records=performanceDetailTemplate.records;
    const expected=days(d.history_window_start,d.history_cutoff);row.history_coverage={available_days:row.usage.length,expected_days:expected,missing_days:expected-row.usage.length,status:'partial'};
    row.financial=Number(id.slice(-2))%3?[]:[{kind:'Bill issued',date:'2024-10-30',amount:42.5,source:'performance_fixture'}];row.detail_loaded=true;
  }
  if(generation!==customerOpenGeneration||data()!==d||view!=='review')return;
  selected=id;view='detail';range='recent';render();window.scrollTo({top:0});
  if(performanceMode)requestAnimationFrame(()=>requestAnimationFrame(()=>{performanceSamples.push({name:'detail',seconds:(performance.now()-start)/1000});$('#performance-metrics').textContent=JSON.stringify(performanceSamples);}));
}
const data=()=>mode==='demo'?demo:uploaded;
function toast(s){$('#notice').innerHTML=s?`<div class="toast">${esc(s)}</div>`:'';}
function setView(v){customerOpenGeneration++;view=v;selected=null;toast('');render();}
function render(){
  const d=data();
  for(const id of ['nav-review','nav-live','nav-upload'])$('#'+id).disabled=false;
  $('#role').disabled=!!realSession;
  $('#content').setAttribute('aria-busy','false');
  $('#page-title').textContent=view==='live'?'Current weather':view==='upload'?'Upload data':view==='settings'?'Settings':'Customer review';
  document.querySelectorAll('.sidebar nav button').forEach(b=>b.removeAttribute('aria-current'));
  $(`#nav-${view==='detail'?'review':view}`).setAttribute('aria-current','page');
  $('#nav-settings').disabled=role!=='Manager';
  $('#nav-settings').title=role==='Manager'?'Settings preview':'Manager access only';
  $('#mode').value=mode;
  const contextData=d??demo;
  $('#mode-description').textContent=mode==='upload'&&!uploaded?'No uploaded data · preloaded demonstration retained':`${dateLabel(contextData.review_date)} review · ${windowLabel(contextData.horizon_start,contextData.horizon_end)} · Fitzroy Crossing 6765`;
  $('#fixture-note').textContent=d?.kind==='calculated_historical_replay'?'Historical replay · synthetic accounts · unvalidated baseline · '+(d.data_mode==='upload'?'Uploaded '+d.batch_revision.slice(0,8):'Preloaded demo'): 'Review fixtures for estimates and heat links. Historical replay, no live prediction.';
  if(d?.performance_fixture)$('#fixture-note').textContent='Performance fixture · 50,000 synthetic summaries · no prediction-quality claim';
  $('#mode-controls').hidden=view!=='upload';
  if(view==='live')return renderLiveWeather();
  if(view==='upload')return renderUpload();
  if(view==='settings')return renderSettings();
  if(!d){$('#content').innerHTML=`<div class="panel empty"><strong>No uploaded data</strong>Choose the twelve synthetic business files, or return to the preloaded demonstration.<br><button class="primary" id="open-upload">Upload data</button></div>`;$('#open-upload').onclick=()=>setView('upload');return;}
  if(view==='detail'&&selected){renderDetail(d);return;}
  renderQueue(d);
}
function renderQueue(d){
  $('#content').innerHTML=`<div class="filters q1" role="search" aria-label="Review filters"><label>Customer<input id="search" type="search" placeholder="Reference, locality or postcode" value="${esc(filters.search)}"></label><label>Account type<select id="type"><option value="">Prepaid and billed</option><option>Prepaid</option><option>Billed</option></select></label><label>Past two years<select id="history"><option value="linked">Heat-linked help or difficulty</option><option value="all">All customers</option></select></label><label>Expected grid-import increase<select id="increase"><option value="past">At least one past episode</option><option value="all">All estimates and unavailable</option><option value="available">Available estimates</option><option value="unavailable">At least one unavailable</option></select></label><button class="secondary" id="reset">Reset filters</button></div><section class="panel"><div class="list-meta"><div><h2>7-day review list</h2><span id="count"></span></div><div class="review-tools"><select id="preview-state" aria-label="Review state preview"><option value="normal">${d.kind==='calculated_historical_replay'?'Calculated review':'Review fixtures'}</option><option value="empty">Empty result preview</option><option value="failure">Load failure preview</option></select><button class="secondary" id="selected-pdf" disabled>Download selected PDF</button><button class="secondary" id="export">Download filtered CSV</button></div></div><div id="queue"></div></section>`;
  $('#reset').onclick=reset;
  for(const k of ['type','history','increase']){$('#'+k).value=filters[k];$('#'+k).onchange=e=>measureUI('filter',()=>{filters[k]=e.target.value;queuePage=0;renderResults(d);});}
  $('#search').oninput=e=>measureUI('filter',()=>{filters.search=e.target.value;queuePage=0;renderResults(d);});
  $('#preview-state').value=previewState;$('#preview-state').onchange=e=>{previewState=e.target.value;renderResults(d);};
  $('#export').onclick=()=>downloadFiltered(d,$('#export'));
  renderResults(d);
}
function renderResults(d){
  if(!preparedSummaries.has(d))preparedSummaries.set(d,prepareQuery(d));
  const rows=previewState==='normal'?query(d,filters,preparedSummaries.get(d)):[];
  const page=pageRows(rows,queuePage);queuePage=page.page;const visible=page.rows;
  $('#count').textContent=previewState==='failure'?'Review unavailable':`${rows.length} customer${rows.length===1?'':'s'} · ${d.customers.length} in this ${d.data_mode==='upload'?'uploaded batch':d.kind==='calculated_historical_replay'?'historical demo':'fixture'}`;
  $('#export').disabled=rows.length===0;
  const matchedIDs=new Set(rows.map(x=>x.customer.customer_id));selectedCustomers=new Set([...selectedCustomers].filter(id=>matchedIDs.has(id)));
  const selectedPdf=$('#selected-pdf');selectedPdf.disabled=!selectedCustomers.size||selectedCustomers.size>100;selectedPdf.title=selectedCustomers.size>100?'Select at most 100 customers for the PDF':'';selectedPdf.textContent='Download selected PDF'+(selectedCustomers.size?' ('+selectedCustomers.size+')':'');selectedPdf.onclick=()=>downloadSummary([...selectedCustomers],selectedPdf,'condensed');
  if(previewState==='failure'){$('#queue').innerHTML=`<div class="empty" role="alert"><strong>Couldn’t load the review list</strong>Your filters are retained. This is a failure-state fixture.<br><button class="secondary" id="retry">Retry review</button></div>`;$('#retry').onclick=()=>{previewState='normal';renderQueue(d);};return;}
  if(!rows.length){$('#queue').innerHTML=`<div class="empty"><strong>No customers match these filters</strong>Try all customers and all estimates to see unavailable results.<br><button class="secondary" id="clear">Reset filters</button></div>`;$('#clear').onclick=reset;return;}
  const sortLabel=k=>filters.sort===k?(filters.direction==='desc'?' ↓':' ↑'):'';
  const sorted=k=>filters.sort===k?` aria-sort="${filters.direction==='desc'?'descending':'ascending'}"`:'';
  $('#queue').innerHTML=`<div class="table-wrap"><table class="review-table"><thead><tr><th class="select-column"><input id="select-all" type="checkbox" aria-label="Select all visible customers" ${visible.every(x=>selectedCustomers.has(x.customer.customer_id))?'checked':''}></th><th scope="col"${sorted('customer')}><button class="sort" data-sort="customer">Customer${sortLabel('customer')}</button></th><th scope="col"${sorted('increase')}><button class="sort" data-sort="increase">Expected grid-import increase${sortLabel('increase')}</button></th><th scope="col">Past heat-linked context</th><th scope="col">Comparison</th></tr></thead><tbody>${visible.map(x=>`<tr><td class="select-column"><input type="checkbox" data-select="${esc(x.customer.customer_id)}" aria-label="Select ${esc(x.customer.customer_id)}" ${selectedCustomers.has(x.customer.customer_id)?'checked':''}></td><td><button class="reference" data-customer="${esc(x.customer.customer_id)}">${esc(x.customer.customer_id)}</button><small>${x.customer.prepayment_meter==='True'?'Prepaid':'Billed'} · ${esc(x.customer.postcode)}</small><small>${esc(x.customer.locality)}</small></td><td><div class="event-cell">${x.estimates.map(e=>`<span>${esc(e.label)} · ${windowLabel(e.start,e.end)} · ${e.duration} days</span><strong class="${e.increase===null?'na':e.increase===x.highest?'high':''}">${pct(e.increase)}</strong>`).join('')}</div></td><td>${x.episodes.length?x.episodes.map(e=>`<div class="past-line">${esc(e.label)} <small>${dateLabel(e.start)} · ${pct(e.increase_percent)}</small></div>`).join(''):'<span class="sub">No linked episode supplied</span>'}</td><td>${x.highest===null?badge('Estimate unavailable'):x.threshold===null?badge('No linked comparison'):x.highest>=x.threshold?badge('Meets past episode','good'):badge('Below past episodes')}<small>${x.threshold!==null?'Lowest comparable episode '+pct(x.threshold):'Unlinked help excluded'}</small></td></tr>`).join('')}</tbody></table></div>${page.pages>1?`<div class="table-foot pagination"><span>Showing ${page.first}–${page.last} of ${page.total.toLocaleString('en-AU')} customers</span><div><button class="secondary" id="previous-page" ${page.page===0?'disabled':''}>Previous</button> <button class="secondary" id="next-page" ${page.page+1===page.pages?'disabled':''}>Next</button></div></div>`:''}`;
  $('#select-all').onchange=e=>measureUI('selection',()=>{for(const row of visible){const id=row.customer.customer_id;if(e.target.checked)selectedCustomers.add(id);else selectedCustomers.delete(id);}renderResults(d);});
  if(page.pages>1){$('#previous-page').onclick=()=>{queuePage--;renderResults(d);};$('#next-page').onclick=()=>{queuePage++;renderResults(d);};}
  document.querySelectorAll('[data-select]').forEach(box=>box.onchange=()=>measureUI('selection',()=>{if(box.checked)selectedCustomers.add(box.dataset.select);else selectedCustomers.delete(box.dataset.select);renderResults(d);}));
  document.querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>measureUI('sort',()=>{const k=b.dataset.sort;filters.direction=filters.sort===k&&filters.direction==='desc'?'asc':'desc';filters.sort=k;renderResults(d);}));
  document.querySelectorAll('[data-customer]').forEach(b=>b.onclick=()=>openCustomer(b.dataset.customer));
}
function reset(){queuePage=0;selectedCustomers.clear();filters={...DEFAULT_FILTERS};previewState='normal';view='review';selected=null;toast('');render();}
async function loadLiveWeather(){
  const generation=++liveWeatherGeneration;liveWeatherError='';
  try{
    const r=await fetch('api/live-weather?mode='+encodeURIComponent(mode));const value=await r.json();
    if(generation!==liveWeatherGeneration)return;
    if(!r.ok)throw Error(value.error||'Current weather unavailable');liveWeather=value;
  }catch(error){if(generation!==liveWeatherGeneration)return;liveWeatherError=error.message;liveWeather=null;}
  if(view==='live')render();
}
function weatherTimeLabel(value){
  if(!value||!Number.isFinite(new Date(value).getTime()))return 'Unavailable';
  return new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Perth',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));
}
function weatherScheduleMarkup(schedule={}){
  const enabled=schedule.enabled===true,known=schedule.enabled!==undefined;
  const state=schedule.running?'Checking weather':enabled?'Active':known?'Not running':'Scheduled';
  const outcome=schedule.last_attempt_succeeded===false?'Download failed; saved weather retained':schedule.cache_reused?'Saved weather is current':schedule.last_attempt_succeeded===true?'Weather updated':'No completed check recorded';
  return `<section class="panel pad" aria-label="Automatic weather updates"><div class="event-head"><h2>Automatic weather updates</h2>${badge(state,enabled?'good':'')}</div>${dl([['Daily check',esc(schedule.daily_time||'06:00')+' · Australia/Perth (UTC+08:00)'],['Next check',esc(weatherTimeLabel(schedule.next_run_at))+' Perth'],['Last check',esc(weatherTimeLabel(schedule.last_attempt_at))],['Last result',esc(outcome)]])}${schedule.configuration_sync_warning?'<p class="notice">Settings were saved, but their disk sync could not be confirmed.</p>':''}${schedule.state_persisted===false?'<p class="notice">Schedule status could not be saved. This running service retains the next check.</p>':''}<p class="sub">Runs while the local service is running. Failed downloads retry after 15 minutes. Business files are replaced separately through Upload data.</p></section>`;
}
function renderLiveWeather(){
  const d=liveWeather;
  $('#mode-description').textContent=d?`${dateLabel(d.review_date)} review · ${windowLabel(d.horizon_start,d.horizon_end)} · Fitzroy Crossing 6765`:'Fitzroy Crossing 6765';
  $('#fixture-note').textContent='Current forecast context · historical demonstration kept separately';
  if(!d){$('#content').innerHTML=`<section class="panel empty" ${liveWeatherError?'role="alert"':''}><strong>${liveWeatherError?esc(liveWeatherError):'Loading current weather…'}</strong><br><button id="reload-weather" class="secondary">Reload weather status</button></section>`;$('#reload-weather').onclick=loadLiveWeather;return;}
  const source=d.source;
  $('#content').innerHTML=weatherScheduleMarkup(d.schedule)+`<section class="panel"><div class="list-meta"><div><h2>Next 7 days</h2><span>${esc(d.status.state==='fresh'?'Forecast retrieved within 24 hours':d.status.state==='stale'?'Saved forecast is stale':'Forecast unavailable')} · ${d.status.complete_target_days} of 7 days supplied</span></div><button id="reload-weather" class="secondary">Reload weather status</button></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Highest temperature</th><th>Lowest temperature</th><th>Coverage</th></tr></thead><tbody>${d.days.map(day=>`<tr><td>${dateLabel(day.date)}</td><td>${day.max_temp===null?'Unavailable':fmt(day.max_temp)+'°C'}</td><td>${day.min_temp===null?'Unavailable':fmt(day.min_temp)+'°C'}</td><td>${day.status==='available'?'24 hourly readings':'Missing forecast readings'}</td></tr>`).join('')}</tbody></table></div><div class="table-foot">${source?`Retrieved ${esc(source.retrieved_at)} · Model issue time ${source.model_issued_at?esc(source.model_issued_at):'unavailable'}. <a href="https://open-meteo.com/">Weather data by Open-Meteo</a> · <a href="https://open-meteo.com/en/licence">CC BY 4.0</a>. Daily max/min are derived from hourly samples.${source.warmup_kind==='archived_model_forecast'?` ${d.context_coverage.complete_prior_calendar_days} previous days supplied as modelled weather; heat classification unavailable.`:''}`:'No valid public snapshot supplied.'}</div></section><section class="panel"><div class="list-meta"><div><h2>Customer estimates unavailable</h2><span>Current estimates need complete usage through ${dateLabel(d.business.required_usage_end)} and compatible heat-period inputs.</span></div></div><div class="table-wrap"><table><thead><tr><th>Retained customer reference</th><th>Latest supplied usage</th><th>Recent complete days</th><th>Current estimate</th></tr></thead><tbody>${d.business.customers.map(c=>`<tr><td>${esc(c.customer_id)}</td><td>${c.latest_usage_date?dateLabel(c.latest_usage_date):'Unavailable'}</td><td>${c.complete_recent_days} of 7</td><td>Unavailable</td></tr>`).join('')}</tbody></table></div><div class="table-foot">Historical source dates are retained. Current account status and heat classification are unverified. Open the customer review for the fixed historical demonstration.</div></section>`;
  $('#reload-weather').onclick=loadLiveWeather;
}
function weatherFor(d,e){const w=d.weather.filter(w=>w.date>=e.start&&w.date<=e.end);return w.length?`${fmt(Math.max(...w.map(r=>+r.max_temp)))}° / ${fmt(Math.min(...w.map(r=>+r.min_temp)))}°C`:'Unavailable';}
const dl=rows=>`<dl class="data-list">${rows.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
function recordLabel(r){return r.kind==='Payment recorded'?'<span class="payment-record"><span aria-hidden="true">✓</span> Payment recorded</span>':esc(r.kind);}
function renderDetail(d){
  const x=summary(d.customers.find(r=>r.customer.customer_id===selected),d),c=x.customer;
  const missingFinancial=!x.row.financial.length;
  const missingText=c.prepayment_meter==='True'?'No prepaid balance records were supplied. The current credit cannot be checked from this data.':'No bill records were supplied. The amount owed cannot be checked from this data.';
  const eventCards=x.estimates.map(e=>`<section class="panel pad"><div class="event-head"><div><h2 class="event-title">${esc(e.label)} · ${windowLabel(e.start,e.end)}</h2><div class="sub">${e.duration} days · ${esc(e.category)}</div></div>${badge(x.calculated?'Historical replay':'Fixture')}</div><div class="estimate ${e.increase===null?'na':''}">${pct(e.increase)}</div><div class="sub">Average daily grid-import change across the whole event</div>${dl([['Estimated daily imports',e.predicted===null?'Unavailable':fmt(e.predicted)+' kWh'],['Estimated event imports',e.predicted===null?'Unavailable':fmt(e.predicted*e.duration)+' kWh'],['Historical max / min',weatherFor(d,e)],['Official BoM category','Unavailable']])}${e.increase===null?`<p class="notice">No estimate: ${esc(e.reason||'insufficient input').replaceAll('_',' ')}</p>`:''}</section>`).join('');
  const comparison=`<section class="panel"><div class="list-meta"><h2>Past heat-linked comparison</h2></div>${x.episodes.length?`<div class="table-wrap"><table><thead><tr><th>Episode</th><th>Change in daily grid use</th></tr></thead><tbody>${x.episodes.map(e=>`<tr><td>${esc(e.label)}<small>${dateLabel(e.start)}–${dateLabel(e.end)}<br>${x.calculated?'Recorded difficulty/help overlaps heat':'Review fixture association'}</small></td><td>${pct(e.increase_percent)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">No heat-linked comparison available.</div>'}</section>`;
  const facts=`<section class="panel account-facts"><div class="list-meta"><h2>Shared account facts</h2></div><div class="table-wrap"><table><thead><tr><th>Record</th><th>Date</th><th>Amount / reference</th></tr></thead><tbody>${x.row.financial.map(r=>`<tr><td>${esc(r.kind)}</td><td>${dateLabel(r.date)}</td><td>${money(r.amount)}</td></tr>`).join('')}${missingFinancial?`<tr><td colspan="3">${esc(missingText)}</td></tr>`:''}${x.row.records.map(r=>`<tr><td>${recordLabel(r)}</td><td>${dateLabel(r.date)}</td><td>${esc(r.id)}</td></tr>`).join('')}</tbody></table></div><div class="table-foot">Recorded once for this customer. Amounts in AUD.</div></section>`;
  $('#content').innerHTML=`<button id="back" class="text-button back">← Review list</button><div class="detail-top"><div><div class="customer-name">${esc(c.customer_id)}</div><div class="sub">${c.prepayment_meter==='True'?'Prepaid':'Billed'} · ${esc(c.locality)} ${esc(c.postcode)} · Review ${dateLabel(d.review_date)}</div></div><button class="secondary" id="download-summary">Download customer summary PDF</button></div><div class="stack">${missingFinancial?`<div class="missing-data" role="note">${esc(missingText)}</div>`:''}<section class="panel reason" aria-label="Explanation"><p>${esc(explanation(x))}</p></section><section class="panel pad"><div class="chart-title"><h2>Electricity use and temperature</h2><div class="segmented" aria-label="Timeline range"><button data-range="recent" aria-pressed="${range==='recent'}">Recent 90 days</button><button data-range="history" aria-pressed="${range==='history'}">Available history</button></div></div>${timeline(x,d)}</section><div class="evidence-grid">${eventCards}${comparison}</div>${facts}<div class="detail-provenance">${x.calculated&&x.row.history_coverage?`History: ${x.row.history_coverage.available_days} of ${x.row.history_coverage.expected_days} days. `:x.calculated?'History coverage unavailable. ':''}<a href="docs/MILESTONE-1-CALCULATION.md" target="_blank">Data and calculation details</a></div></div>`;
  $('#back').onclick=()=>{view='review';selected=null;render();};
  document.querySelectorAll('[data-range]').forEach(b=>b.onclick=()=>{range=b.dataset.range;renderDetail(d);});
  $('#download-summary').onclick=()=>downloadSummary([c.customer_id],$('#download-summary'));
}
async function downloadSummary(ids,button,format='detailed'){
  const snapshot=data(),exportMode=mode,revision=snapshot.batch_revision;
  const label=button.textContent;button.disabled=true;button.textContent='Creating PDF…';
  try{
    const response=await fetch('api/customer-summary.pdf',{method:'POST',headers:{'Content-Type':'application/json','X-Q1-Request-Token':requestToken,'X-Team-Connect-CSRF':sessionCsrf},body:JSON.stringify({customer_ids:ids,mode:exportMode,batch_revision:revision,format})});
    if(!response.ok)throw Error((await response.json()).error||'PDF unavailable');
    if(response.headers.get('Content-Type')!=='application/pdf')throw Error('PDF unavailable');
    const body=new Uint8Array(await response.arrayBuffer());
    if(new TextDecoder().decode(body.slice(0,5))!=='%PDF-')throw Error('Invalid PDF');
    if(mode!==exportMode||data()?.batch_revision!==revision)throw Error('The data mode or version changed while the PDF was created. Download again from the current review.');
    download(ids.length===1?ids[0]+'-review.pdf':'q1-selected-customers.pdf',body,'application/pdf');
  }catch(error){toast(error.message+' Your selection is retained.');}
  finally{button.disabled=false;button.textContent=label;}
}
function timeline(x,d){
  const start=range==='history'?d.history_available_start:new Date(Date.parse(d.history_cutoff)-89*86400000).toISOString().slice(0,10);
  const end=d.history_cutoff,W=760,H=350,left=48,right=16,width=W-left-right;
  const xpos=date=>left+(Date.parse(date)-Date.parse(start))/(Date.parse(end)-Date.parse(start))*width;
  const u=x.row.usage.filter(r=>r.date>=start&&r.date<=end),w=d.weather.filter(r=>r.date>=start&&r.date<=end);
  const max=Math.max(5,...u.map(r=>+r.import_kwh))*1.12;
  const yval=n=>135-n/max*100;
  function path(points,value,y){let last=null;return points.map(r=>{const command=last&&days(last,r.date)===2?'L':'M';last=r.date;return `${command}${xpos(r.date).toFixed(1)},${y(value(r)).toFixed(1)}`;}).join(' ');}
  const tickDates=[start,...[.33,.66].map(f=>new Date(Date.parse(start)+(Date.parse(end)-Date.parse(start))*f).toISOString().slice(0,10)),end];
  const episodes=(d.past_events??x.episodes).filter(e=>e.end>=start&&e.start<=end);
  const shades=episodes.map(e=>`<rect x="${Math.max(left,xpos(e.start))-2}" y="30" width="${Math.max(5,Math.min(W-right,xpos(e.end))-Math.max(left,xpos(e.start))+4)}" height="108" fill="#f9e4e0" opacity=".7"><title>${esc(e.label)} · ${e.start}–${e.end} · derived heat period</title></rect>`).join('');
  const grouped=new Map();
  for(const r of [...x.row.financial,...x.row.records].filter(r=>r.date>=start&&r.date<=end).sort((a,b)=>a.date.localeCompare(b.date))){if(!grouped.has(r.date))grouped.set(r.date,[]);grouped.get(r.date).push(r);}
  let previousX=-100,lane=0;
  const records=[...grouped].map(([date,items],i)=>{const px=xpos(date);lane=px-previousX<20?1-lane:0;previousX=px;return {date,items,index:i+1,px,py:180+lane*17};});
  const marks=records.map(r=>`<g role="img" aria-label="Account date ${r.index}: ${esc(dateLabel(r.date))}, ${esc([...new Set(r.items.map(i=>i.kind))].join(', '))}"><title>${dateLabel(r.date)} · ${esc([...new Set(r.items.map(i=>i.kind))].join(', '))}</title><circle cx="${r.px}" cy="${r.py}" r="8" fill="${r.items.every(i=>i.kind==='Payment recorded')?'#176344':'#9c7735'}"/><text class="record-number" x="${r.px}" y="${r.py+3.5}" text-anchor="middle">${r.index}</text></g>`).join('');
  const recordKey=records.length?`<div class="record-key" aria-label="Account dates on the chart">${records.map(r=>`<span><b class="${r.items.every(i=>i.kind==='Payment recorded')?'payment-marker':''}">${r.index}</b>${r.items.map(recordLabel).join(' / ')} · ${dateLabel(r.date)}</span>`).join('')}</div>`:'<div class="sub chart-record-note">No bill or support dates in this part of the history.</div>';
  const useLegend=`<div class="legend chart-key"><span><i></i>Electricity from the grid</span><span><i class="temp-high"></i>Highest temperature</span><span><i class="temp-low"></i>Lowest temperature</span>${episodes.length?'<span><i class="heat"></i>Derived heat period · red dashed temperature</span>':''}</div>`;
  const upcoming=x.estimates.map(e=>`<div class="upcoming-event"><div class="upcoming-date">${esc(e.label)} · ${windowLabel(e.start,e.end)}</div><strong class="${e.predicted===null?'unavailable':''}">${e.predicted===null?'Unavailable':fmt(e.predicted)+' <small>kWh each day</small>'}</strong><span>${e.increase===null?'No estimate available':e.increase===0?'Same as usual':Math.abs(Number(e.increase.toFixed(1)))+'% '+(e.increase>0?'more':'less')+' than usual'}</span><small>Average across ${e.duration} days</small></div>`).join('');
  return `<div class="timeline-layout"><div class="recorded-timeline"><div class="timeline-scroll" tabindex="0" aria-label="Recorded timeline; scroll horizontally on small screens"><svg class="timeline-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Recorded daily electricity use and highest and lowest temperature through ${dateLabel(end)}. Numbered markers identify the account dates listed below."><text x="${left}" y="15">Electricity from the grid · kWh each day</text>${shades}${[0,.5,1].map(f=>`<line x1="${left}" x2="${W-right}" y1="${yval(max*f)}" y2="${yval(max*f)}" stroke="#e2e9e9"/><text x="${left-8}" y="${yval(max*f)+4}" text-anchor="end">${fmt(max*f)}</text>`).join('')}<path d="${path(u,r=>+r.import_kwh,yval)}" stroke="#317b76" stroke-width="2" fill="none"/><text x="${left}" y="162">Account dates</text><line x1="${left}" x2="${W-right}" y1="180" y2="180" stroke="#edf0ed"/>${marks}<text x="${left}" y="227">Recorded temperature · °C</text>${[20,30,40].map(n=>`<line x1="${left}" x2="${W-right}" y1="${320-(n-10)*2.5}" y2="${320-(n-10)*2.5}" stroke="#e2e9e9"/><text x="${left-8}" y="${324-(n-10)*2.5}" text-anchor="end">${n}</text>`).join('')}<path d="${path(w,r=>+r.max_temp,n=>320-(n-10)*2.5)}" stroke="#b58d48" stroke-width="1.5" fill="none"/><path d="${path(w,r=>+r.min_temp,n=>320-(n-10)*2.5)}" stroke="#91aaa6" stroke-width="1.5" fill="none"/>${episodes.map(e=>{const hw=w.filter(r=>r.date>=e.start&&r.date<=e.end);return `<path d="${path(hw,r=>+r.max_temp,n=>320-(n-10)*2.5)}" stroke="#b63732" stroke-width="2.5" stroke-dasharray="5 2" fill="none"/><path d="${path(hw,r=>+r.min_temp,n=>320-(n-10)*2.5)}" stroke="#b63732" stroke-width="2.5" stroke-dasharray="5 2" fill="none"/>`;}).join('')}${tickDates.map((s,i)=>`<text x="${xpos(s)}" y="340" text-anchor="${i===0?'start':i===3?'end':'middle'}">${dateLabel(s)}</text>`).join('')}</svg></div>${useLegend}${records.length>3?`<details class="chart-records"><summary>${records.length} account dates on the chart</summary>${recordKey}</details>`:recordKey}</div><aside class="upcoming-preview" aria-label="Next seven days demo estimates"><h3>Next 7 days</h3><p>${windowLabel(d.horizon_start,d.horizon_end)} · ${x.calculated?'estimated grid use':'demo estimates'}</p>${upcoming||'<div class="sub">No heat period detected in this replay window.</div>'}</aside></div>`;
}
async function postJson(path,body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Q1-Request-Token':requestToken,'X-Team-Connect-CSRF':sessionCsrf},body:JSON.stringify(body)});
  const value=await r.json();if(!r.ok)throw Error(value.error||'The local operation failed');return value;
}
async function refreshUploaded(){
  const generation=++uploadRefreshGeneration;
  try{
    const response=await fetch('api/state');if(generation!==uploadRefreshGeneration)return;
    if(!response.ok)throw Error('Could not reload upload status');
    const state=await response.json();if(generation!==uploadRefreshGeneration)return;
    uploadState=state;requestToken=state.request_token;
    if(state.active_batch&&uploaded?.batch_id===state.active_batch&&uploaded.batch_revision===state.revision)return;
    uploaded=null;
    if(state.active_batch){
      const r=await fetch('api/review?mode=upload&revision='+encodeURIComponent(state.revision));
      const value=await r.json();if(generation!==uploadRefreshGeneration)return;
      if(!r.ok)throw Error(value.error||'Uploaded data changed');
      if(value.batch_id!==state.active_batch||value.batch_revision!==state.revision)throw Error('Uploaded data changed. Reload the current batch.');
      uploaded=value;
    }
  }catch(error){if(generation===uploadRefreshGeneration)throw error;}
}
async function downloadFiltered(d,button){
  const exportMode=mode,revision=d.batch_revision;button.disabled=true;
  try{
    const r=await fetch('api/export.csv',{method:'POST',headers:{'Content-Type':'application/json','X-Q1-Request-Token':requestToken,'X-Team-Connect-CSRF':sessionCsrf},body:JSON.stringify({mode:exportMode,batch_revision:revision,customer_ids:query(d,filters).map(x=>x.customer.customer_id)})});
    if(!r.ok)throw Error((await r.json()).error||'CSV unavailable');
    const body=new Uint8Array(await r.arrayBuffer());
    if(mode!==exportMode||data()?.batch_revision!==revision)throw Error('The data mode or version changed while the CSV was created. Download again from the current review.');
    download('q1-'+(exportMode==='demo'?'preloaded':'uploaded')+'-'+revision.slice(-8)+'.csv',body,'text/csv');
  }catch(error){toast(error.message);}finally{button.disabled=false;}
}
function renderUpload(){
  const active=uploadState.summary;
  $('#content').innerHTML=`<section class="panel pad flow"><h2>Replace uploaded data</h2><p>Choose the complete twelve-file batch of synthetic business data. Files are checked and the review is calculated before you confirm replacement. The preloaded demonstration stays available.</p>${uploadState.recovery?`<div class="missing-data" role="status">${esc(uploadState.recovery)}</div>`:''}<div class="upload-current"><strong>${active?'Current uploaded batch · '+uploadState.revision.slice(0,8):'No uploaded batch yet'}</strong><span class="sub">${active?active.review_customers+' review customer'+(active.review_customers===1?'':'s')+' · '+active.total_rows.toLocaleString()+' source rows':'Fitzroy Crossing 6765 · historical review on 2 Nov 2024'}</span></div><div class="upload-box"><label for="upload-files"><strong>Choose twelve business files</strong></label><input id="upload-files" type="file" multiple accept=".csv,.gz" ${uploadBusy||uploadJobPending?'disabled':''}><span id="file-count" class="sub">CSV and the existing consumption CSV.GZ · 64 MiB total limit</span><div class="upload-actions"><button class="primary" id="check-upload" disabled>${uploadBusy?'Uploading, checking and calculating…':'Check selected files'}</button>${uploadBusy||uploadJobPending?'<button class="secondary" id="cancel-upload">Cancel upload</button>':''}${uploadJobPending&&!uploadBusy?'<button class="secondary" id="resume-upload">Resume file checks</button>':''}</div></div>${uploadError?`<div class="upload-error" role="alert">${esc(uploadError)}</div>`:''}${pendingUpload?`<div class="upload-state"><h3>Checked and ready for confirmation</h3><div>${pendingUpload.summary.review_customers} customer${pendingUpload.summary.review_customers===1?'':'s'} in the review · ${pendingUpload.summary.events} heat period${pendingUpload.summary.events===1?'':'s'}</div><div class="sub">${pendingUpload.summary.total_rows.toLocaleString()} source rows · 2 Nov 2024 · the current estimate method and historical weather are retained</div><details class="checked-files"><summary>Twelve checked files</summary><ul>${pendingUpload.summary.files.map(f=>`<li>${esc(f.file.split('/').pop())} · ${f.rows.toLocaleString()} rows</li>`).join('')}</ul></details><div class="upload-actions"><button class="primary" id="replace">Review replacement</button><button class="secondary" id="discard-upload">Discard checked files</button></div></div>`:''}<div class="upload-actions recovery-actions"><button class="secondary" id="reload-upload" ${uploadBusy||uploadJobPending?'disabled':''}>Reload upload status</button>${uploadState.previous_available?'<button class="secondary" id="restore-upload">Restore previous uploaded batch</button>':''}</div><details class="checked-files"><summary>Required filenames</summary><ul>${(uploadState.filenames??[]).map(n=>`<li>${esc(n)}</li>`).join('')}</ul></details><p class="sub">${realSession?'Signed-in Q1 instance; server permissions apply.':'One local synthetic-data instance. Role controls remain a visual preview.'}</p></section>`;
  $('#upload-files').onchange=()=>{const count=$('#upload-files').files.length;$('#file-count').textContent=count+' files selected';$('#check-upload').disabled=uploadBusy||uploadJobPending||count!==12;};
  $('#check-upload').onclick=stageUpload;
  if(uploadBusy||uploadJobPending)$('#cancel-upload').onclick=cancelUpload;
  if(uploadJobPending&&!uploadBusy)$('#resume-upload').onclick=resumeUploadJob;
  if(pendingUpload){$('#replace').onclick=()=>showReplaceDialog();$('#discard-upload').onclick=async()=>{try{await postJson('api/uploads/cancel',{request_id:pendingUpload.stage_id});pendingUpload=null;}catch(error){uploadError=error.message;}renderUpload();};}
  $('#reload-upload').onclick=async()=>{try{await refreshUploaded();uploadError='';renderUpload();}catch(e){uploadError=e.message;renderUpload();}};
  if(uploadState.previous_available)$('#restore-upload').onclick=()=>showReplaceDialog(true);
}
async function cancelUpload(){
  const operation=uploadOperation;uploadAttemptGeneration++;uploadAbort?.abort();uploadBusy=false;pendingUpload=null;uploadJobPending=!!operation;
  if(view==='upload')renderUpload();
  try{if(operation)await postJson('api/uploads/cancel',{request_id:operation});if(uploadOperation===operation){uploadOperation=null;uploadJobPending=false;uploadError='';}}
  catch(error){if(uploadOperation===operation)uploadError='Cancellation could not be confirmed. '+error.message;}
  if(view==='upload')renderUpload();
}
async function stageUpload(){
  if(uploadBusy)return;
  const files=Array.from($('#upload-files').files);if(files.length!==12)return;
  const previous=pendingUpload;pendingUpload=null;uploadError='';uploadBusy=true;
  const operation=crypto.randomUUID().replaceAll('-','');uploadOperation=operation;uploadJobPending=true;const attempt=++uploadAttemptGeneration;const controller=new AbortController();uploadAbort=controller;
  const form=new FormData();for(const file of files)form.append('files',file,file.name);
  form.append('request_id',operation);form.append('expected_revision',uploadState.revision);renderUpload();
  try{
    if(previous)await postJson('api/uploads/cancel',{request_id:previous.stage_id});
    if(uploadOperation!==operation)return;
    const r=await fetch('api/uploads/stage',{method:'POST',headers:{'X-Q1-Request-Token':requestToken,'X-Team-Connect-CSRF':sessionCsrf},body:form,signal:controller.signal});
    const result=await r.json();if(uploadOperation!==operation||uploadAttemptGeneration!==attempt)return;
    if(!r.ok){if(r.status<500)uploadJobPending=false;throw Error(result.error||'Files could not be checked');}
    const receipt=r.status===202?await waitForUploadJob(result,controller.signal):result;
    if(uploadOperation===operation&&uploadAttemptGeneration===attempt){pendingUpload=receipt;uploadJobPending=false;}
  }catch(error){if(uploadOperation===operation&&uploadAttemptGeneration===attempt){if(error.uploadJobState)uploadJobPending=false;if(error.name!=='AbortError')uploadError=error.message;}}
  finally{if(uploadOperation===operation&&uploadAttemptGeneration===attempt){uploadBusy=false;if(view==='upload')renderUpload();}}
}
async function waitForUploadJob(initial,signal){
  let job=initial;const deadline=performance.now()+75000;
  while(job.state==='queued'||job.state==='running'){
    if(signal.aborted)throw new DOMException('Upload cancelled','AbortError');
    if(performance.now()>=deadline)throw Error('Checking timed out. The current batch was kept; resume file checks or cancel before retrying.');
    await new Promise(resolve=>setTimeout(resolve,250));
    const response=await fetch('api/uploads/status?request_id='+encodeURIComponent(job.request_id),{signal:AbortSignal.any([signal,AbortSignal.timeout(5000)])});
    const value=await response.json();if(!response.ok)throw Error(value.error||'Upload status unavailable');job=value;
  }
  if(job.state!=='ready'){const error=Error(job.error||'Upload '+job.state);error.uploadJobState=job.state;throw error;}
  return job.receipt;
}
async function resumeUploadJob(){
  if(uploadBusy||!uploadOperation)return;
  const operation=uploadOperation,attempt=++uploadAttemptGeneration,controller=new AbortController();uploadAbort=controller;uploadBusy=true;uploadError='';renderUpload();
  try{
    const response=await fetch('api/uploads/status?request_id='+encodeURIComponent(operation),{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(5000)])});
    const job=await response.json();
    if(uploadOperation!==operation||uploadAttemptGeneration!==attempt)return;
    if(!response.ok){if(response.status===404){uploadOperation=null;uploadJobPending=false;}throw Error(job.error||'Upload status unavailable');}
    if(job.state==='failed'||job.state==='cancelled'){uploadJobPending=false;uploadOperation=null;}
    const receipt=await waitForUploadJob(job,controller.signal);
    if(uploadOperation===operation&&uploadAttemptGeneration===attempt){pendingUpload=receipt;uploadJobPending=false;}
  }catch(error){if(uploadAttemptGeneration===attempt&&error.name!=='AbortError')uploadError=error.message;}
  finally{if(uploadAttemptGeneration===attempt){uploadBusy=false;if(view==='upload')renderUpload();}}
}
function showReplaceDialog(restore=false){
  const dialog=$('#dialog');
  dialog.innerHTML=`<h2 id="dialog-title">${restore?'Restore the previous uploaded batch?':'Replace uploaded data?'}</h2><p>${restore?'The previous validated batch will become the uploaded review.':'The twelve checked files and their calculated review will replace the current uploaded batch.'} The preloaded demonstration stays available.</p><p>${restore?'The current batch will remain recoverable.':(pendingUpload?.summary.review_customers??0)+' customer'+(pendingUpload?.summary.review_customers===1?'':'s')+' · historical review on 2 Nov 2024. '+(uploadState.active_batch?'The previous uploaded batch remains recoverable.':'This is the first uploaded batch.')}</p><div class="dialog-actions"><button class="secondary" id="cancel-replace">Cancel</button><button class="primary" id="confirm-replace">${restore?'Restore previous batch':'Replace uploaded data'}</button></div>`;
  dialog.showModal();$('#cancel-replace').onclick=()=>dialog.close();
  $('#confirm-replace').onclick=async()=>{
    const button=$('#confirm-replace');button.disabled=true;$('#cancel-replace').disabled=true;button.textContent=restore?'Restoring…':'Replacing…';
    try{
      const result=restore?await postJson('api/uploads/rollback',{request_id:crypto.randomUUID().replaceAll('-',''),expected_revision:uploadState.revision,confirm_restore:true}):await postJson('api/uploads/activate',{stage_id:pendingUpload.stage_id,expected_revision:pendingUpload.expected_revision,confirm_replace:true});
      await refreshUploaded();pendingUpload=null;selectedCustomers.clear();filters={...DEFAULT_FILTERS};previewState='normal';mode='upload';view='review';selected=null;dialog.close();render();toast(result.unchanged?'The checked files match the current uploaded batch.':restore?'Previous uploaded batch restored.':'Uploaded data replaced. The preloaded demonstration is retained.');
    }catch(error){uploadError=error.message;dialog.close();renderUpload();}
  };
}
function renderSettings(){
  if(role!=='Manager'){view='review';render();return;}
  if(realSession){
    if(!managerSettings){$('#content').innerHTML=`<section class="panel empty">${esc(settingsError||'Loading instance settings…')}</section>`;return;}
    $('#content').innerHTML=`<section class="panel pad flow"><h2>Instance settings</h2><label class="form-field">Default opening mode<select id="opening"><option value="demo">Preloaded demonstration</option><option value="upload">Uploaded data</option></select></label><label class="form-field">Daily public-weather check<input id="weather-time" type="time" value="${esc(managerSettings.weather_time)}" required></label><p class="sub">Australia/Perth (UTC+08:00). Current saved weather is reused; otherwise the app downloads a fresh public forecast. Business uploads stay manual.</p><button id="save-settings" class="primary">Save settings</button></section>`;
    $('#opening').value=managerSettings.opening_mode;
    $('#save-settings').onclick=async()=>{const button=$('#save-settings');button.disabled=true;try{managerSettings=await postJson('api/settings',{opening_mode:$('#opening').value,weather_time:$('#weather-time').value});toast('Instance settings saved.');}catch(error){toast(error.message);}finally{button.disabled=false;}};return;
  }
  $('#content').innerHTML=`<section class="panel pad flow"><div class="role-info">${badge('Manager','good')}<span class="sub">Instance settings preview</span></div><h2>Access and data</h2><div class="table-wrap"><table class="role-table"><thead><tr><th>Capability</th><th>Officer</th><th>Manager</th></tr></thead><tbody><tr><td>Review customers and download review data</td><td>Available</td><td>Available</td></tr><tr><td>Upload and replace this instance’s data</td><td>Available</td><td>Available</td></tr><tr><td>Manage settings</td><td>Unavailable</td><td>Available</td></tr></tbody></table></div><label class="form-field">Default opening mode<select id="opening"><option>Preloaded demonstration</option><option>Uploaded data preview</option></select></label><button class="primary" id="save-settings">Preview save</button><hr class="divider"><p>Each instance is intended to keep its data isolated. Roles and settings here are visual previews held in this page only. Authentication and multi-user permissions are not connected. This milestone runs one local synthetic instance.</p></section>`;
  $('#save-settings').onclick=()=>toast('Settings interaction previewed. No account or permission changes were made.');
}
async function loadSettings(){
  settingsError='';
  try{const response=await fetch('api/settings'),value=await response.json();if(!response.ok)throw Error(value.error||'Settings unavailable');managerSettings=value;}
  catch(error){managerSettings=null;settingsError=error.message;}
  if(view==='settings')render();
}
function download(name,body,type){const url=URL.createObjectURL(new Blob([body],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#nav-review').onclick=()=>setView('review');$('#nav-upload').onclick=()=>setView('upload');$('#nav-settings').onclick=()=>{setView('settings');if(realSession)loadSettings();};
$('#nav-live').onclick=()=>{liveWeather=null;liveWeatherError='';setView('live');loadLiveWeather();};
$('#role').onchange=e=>{toast('');role=e.target.value;if(role==='Officer'&&view==='settings')view='review';render();};
$('#mode').onchange=async e=>{selectedCustomers.clear();mode=e.target.value;view='review';selected=null;toast('');try{if(mode==='upload')await refreshUploaded();render();}catch(error){toast(error.message);}};
try{
 const session=await fetch('api/session');
 if(session.status===401){location.assign('/auth/login');throw Error('Sign-in required');}
 if(!session.ok)throw Error('Local session unavailable');const account=await session.json();
 if(account.authenticated){realSession=account;sessionCsrf=account.csrf_token;role=account.role==='manager'?'Manager':'Officer';$('#role').value=role;$('#role').disabled=true;document.querySelector('.sidebar-bottom .sub').textContent='Signed in · '+role;}
 const response=await fetch(performanceMode?'tests/performance-review-50k.json':'api/review');if(!response.ok)throw Error('Review inputs unavailable');demo=await response.json();if(performanceMode)demo.performance_fixture=true;await refreshUploaded();if(realSession&&uploadState.opening_mode==='upload'&&!performanceMode)mode='upload';render();requestAnimationFrame(()=>requestAnimationFrame(()=>{$('#content').dataset.readyMs=String(performance.now());}));
}catch(error){ $('#content').setAttribute('aria-busy','false');$('#content').innerHTML='<div class="panel empty" role="alert"><strong>Couldn’t load the calculated review</strong><p>'+esc(error.message)+'</p><button class="secondary" id="reload">Retry</button></div>';$('#reload').onclick=()=>location.reload();}
