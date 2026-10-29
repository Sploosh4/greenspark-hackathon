// Community planning: state-wide ML temperature outlook (real Oct/Nov 2026 issues, 1-degree cells).
// Independent of the synthetic 2025 scenario and its As-of date. Uses a WA outline instead of the
// MapTiler basemap so it renders without a map key; the existing postcode map is unchanged.
import {addMlOutlookLayer,cellSummary,MODES,LOW_SKILL,skillWord} from './ml-outlook-layer.mjs';
import {esc} from './core.mjs';

const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const monthText=ym=>{const [y,m]=ym.split('-');return MON[m-1]+' '+y;};
const MODE_LABELS={anom:'Difference from average',prob:'Chance warmer',temp:'Temperature'};
const cellText=s=>`${-s.lat-.5}–${-s.lat+.5}°S · ${s.lon-.5}–${s.lon+.5}°E`;
export const mlCellId=(lat,lon)=>`${(Math.floor(lat)+.5).toFixed(1)}_${(Math.floor(lon)+.5).toFixed(1)}`;

let dataPromise;
export function loadMlOutlook(){
  if(!dataPromise)dataPromise=Promise.all(['./ml-outlook/ml_outlook_layer.json','./ml-outlook/wa_outline.geojson'].map(url=>fetch(url).then(r=>{if(!r.ok)throw Error('ML outlook unavailable');return r.json();})))
    .catch(error=>{dataPromise=null;throw error;});
  return dataPromise;
}

export function mlOutlookShell(c){
  return `<section class="panel pad ml-outlook" id="ml-outlook" aria-labelledby="ml-outlook-title"><div class="section-head"><h2 id="ml-outlook-title">WA temperature outlook</h2><div class="ml-badges"><span class="status warn">ML · experimental</span><span class="status">Real data · Oct–Nov 2026 issues</span></div></div>
    <p class="sub ml-intro">Monthly mean temperature on 1° cells, from a statistical model checked against 20 years of past forecasts. It is not linked to the 2025 synthetic accounts or the As-of date above. Planning context only: it does not forecast heatwaves or their dates.</p>
    <div class="ml-controls"><label>Forecast issue<select id="ml-issue" disabled></select></label><div class="segmented" id="ml-mode" aria-label="Map measure">${Object.entries(MODE_LABELS).map(([k,v])=>`<button type="button" data-ml-mode="${k}" aria-pressed="false">${v}</button>`).join('')}</div></div>
    <div class="ml-grid"><div><div id="ml-map" data-ml-state="loading" role="img" aria-label="Map of WA 1-degree cells coloured by the ML outlook; the table beside it lists the same values for ${esc(c.locality)}"></div><div class="ml-months" id="ml-months" role="radiogroup" aria-label="Forecast month"></div><div class="ml-legend" id="ml-legend"></div></div><div id="ml-detail" aria-live="polite"><div class="empty">Loading outlook…</div></div></div>
    <div class="notice">Faded cells: little skill in past forecasts at that lead time. Compare differences from average, not absolute °C, with Copernicus. <a href="ml-outlook/provenance.json" target="_blank" rel="noopener">Sources and method</a></div></section>`;
}

export function initMlOutlook(c,saved,save){
  const host=document.querySelector('#ml-map');if(!host)return {remove(){}};
  let map,ml,removed=false,data,selected=mlCellId(Number(c.latitude),Number(c.longitude));
  const st={issue:saved.mlIssue,mode:MODES[saved.mlMode]?saved.mlMode:'anom',month:Math.min(5,Math.max(0,Number(saved.mlMonth)||0))};
  const $=s=>document.querySelector(s);
  const persist=()=>save({mlIssue:st.issue,mlMode:st.mode,mlMonth:String(st.month)});

  function renderControls(){
    const issue=data.issues.find(i=>i.key===st.issue);
    $('#ml-issue').innerHTML=data.issues.map(i=>`<option value="${esc(i.key)}" ${i.key===st.issue?'selected':''}>${esc(i.label)} issue${i.uses_partial_month?' · includes 1–21 Oct':''}</option>`).join('');
    document.querySelectorAll('[data-ml-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mlMode===st.mode)));
    $('#ml-months').innerHTML=issue.months.map((ym,i)=>`<button type="button" role="radio" data-ml-month="${i}" aria-checked="${i===st.month}" tabindex="${i===st.month?0:-1}">${monthText(ym)}</button>`).join('');
    const m=MODES[st.mode],span=m.domain[1]-m.domain[0];
    $('#ml-legend').innerHTML=`<span>${esc(m.label)}</span><div class="ml-bar" style="background:linear-gradient(90deg,${m.stops.map(([v,col])=>`${col} ${(v-m.domain[0])/span*100}%`).join(',')})"></div><div class="ml-ticks">${m.ticks.map(t=>`<span>${st.mode==='prob'?Math.round(t*100)+'%':t}</span>`).join('')}</div>`;
  }
  function renderDetail(){
    const s=cellSummary(data,st.issue,selected);
    if(!s){$('#ml-detail').innerHTML='<div class="empty">Select a cell on the map</div>';return;}
    const m=s.months[st.month],own=selected===mlCellId(Number(c.latitude),Number(c.longitude));
    $('#ml-detail').innerHTML=`<h3>${esc(own?c.locality:s.locality??'Grid cell')}</h3><div class="sub">${cellText(s)} · whole 1° cell, not the town or postcode boundary</div>
      <div class="stat"><label>${esc(MODES[st.mode].label)} · ${monthText(m.month)}</label><strong>${MODES[st.mode].fmt({temp:m.temp,anom:m.anom,prob:m.prob}[st.mode])}</strong><small>${m.temp.toFixed(1)} °C forecast · ${m.lo.toFixed(1)}–${m.hi.toFixed(1)} °C likely range · 1991–2020 average ${m.normal.toFixed(1)} °C</small></div>
      <div class="table-wrap"><table class="ml-table"><thead><tr><th scope="col">Month</th><th scope="col">Mean °C</th><th scope="col">vs average</th><th scope="col">Chance warmer</th><th scope="col">Past skill</th></tr></thead><tbody>${s.months.map((x,i)=>`<tr${i===st.month?' class="selected"':''}><td>${monthText(x.month)}</td><td>${x.temp.toFixed(1)}</td><td>${MODES.anom.fmt(x.anom)}</td><td>${MODES.prob.fmt(x.prob)}</td><td>${x.lowSkill?'<span class="status">Little</span>':esc(skillWord(x.skill)[0].toUpperCase()+skillWord(x.skill).slice(1))}</td></tr>`).join('')}</tbody></table></div>
      ${m.lowSkill?`<div class="notice">Past forecasts for this cell showed little skill ${m.lead} month${m.lead>1?'s':''} ahead; treat ${monthText(m.month)} as close to the long-term average.</div>`:''}
      ${own?'':`<button class="text-button" type="button" id="ml-back">← Back to ${esc(c.locality)}</button>`}`;
    host.dataset.mlCell=selected;
    const back=$('#ml-back');if(back)back.onclick=()=>ml.select(mlCellId(Number(c.latitude),Number(c.longitude)));
  }
  const refresh=()=>{renderControls();renderDetail();};

  loadMlOutlook().then(([layer,outline])=>{
    if(removed||!host.isConnected)return;
    data=layer;if(!data.issues.some(i=>i.key===st.issue))st.issue=data.issues.at(-1).key;
    map=new window.maplibregl.Map({container:host,attributionControl:false,renderWorldCopies:false,bounds:[[111.8,-35.8],[129.4,-13.4]],fitBoundsOptions:{padding:16},
      style:{version:8,sources:{wa:{type:'geojson',data:outline,attribution:'Outline: Natural Earth'}},layers:[{id:'sea',type:'background',paint:{'background-color':'#e3ecee'}},{id:'wa-land',type:'fill',source:'wa',paint:{'fill-color':'#f4f3ee'}},{id:'wa-line',type:'line',source:'wa',paint:{'line-color':'#56676a','line-width':1}}]}});
    map.addControl(new window.maplibregl.NavigationControl({showCompass:false}),'top-right');
    map.addControl(new window.maplibregl.AttributionControl({compact:true}),'bottom-right');
    const resizeObserver=new ResizeObserver(()=>{if(!removed&&host.clientWidth)map.resize();});resizeObserver.observe(host);map.on('remove',()=>resizeObserver.disconnect());
    map.on('load',()=>{
      if(removed)return;
      ml=addMlOutlookLayer(map,data,{issue:st.issue,month:st.month,mode:st.mode,beforeId:'wa-line',onSelect:s=>{if(s){selected=s.id;renderDetail();}}});
      const marker=document.createElement('div');marker.className='ml-place';marker.innerHTML=`<i></i>${esc(c.locality)}`;
      new window.maplibregl.Marker({element:marker,anchor:'left',offset:[-4,0]}).setLngLat([Number(c.longitude),Number(c.latitude)]).addTo(map);
      ml.select(selected);host.dataset.mlState='ready';host.dataset.mlIssue=st.issue;$('#ml-issue').disabled=false;
    });
    map.on('error',()=>{if(!removed&&host.dataset.mlState!=='ready'){host.dataset.mlState='error';}});
    refresh();
    $('#ml-issue').onchange=e=>{st.issue=e.target.value;ml?.setIssue(st.issue);host.dataset.mlIssue=st.issue;persist();refresh();};
    $('#ml-mode').onclick=e=>{const k=e.target.closest('[data-ml-mode]')?.dataset.mlMode;if(k){st.mode=k;ml?.setMode(k);persist();refresh();}};
    $('#ml-months').onclick=e=>{const i=e.target.closest('[data-ml-month]')?.dataset.mlMonth;if(i!=null){st.month=+i;ml?.setMonth(st.month);persist();refresh();}};
    $('#ml-months').onkeydown=e=>{const step={ArrowRight:1,ArrowLeft:-1}[e.key];if(step){st.month=(st.month+step+6)%6;ml?.setMonth(st.month);persist();refresh();$(`[data-ml-month="${st.month}"]`).focus();}};
  }).catch(()=>{
    if(removed||!host.isConnected)return;
    host.dataset.mlState='error';$('#ml-detail').innerHTML='<div class="empty">ML outlook unavailable</div>';
  });
  return {remove(){removed=true;map?.remove();}};
}
