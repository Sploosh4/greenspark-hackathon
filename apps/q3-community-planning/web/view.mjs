import {MEASURES,measureReading,readStatistical,projectStatistical,statisticalCell} from './modules/statistical-outlook.mjs';
import {renderFinancialSupport} from './modules/financial-support.mjs';
import {localStyle,createBasemap,labelCandidates} from './modules/local-basemap.mjs';
import {PERF,painted} from './modules/performance.mjs';
import {GEOGRAPHY} from './modules/geography-reference.mjs';
import {installSessionControl} from './modules/session.mjs';
import {cell,dimensions} from './grid.mjs';
import {validatePolicy,countMonths,countGrid,outlineMatches} from './warm-filter.mjs';
import {createSnapshotReader} from './modules/source-adapter.mjs';
import {nearestNativeCell,cellContainsPoint,nativeMeanGrid,mappedArea,historicalPoint,selectedSeries} from './modules/planning-calculations.mjs';
import {createNativeHistory,afterSourcePaint} from './modules/native-history.mjs';
import {historicalFeatures,addHistoricalLayer,setHistoricalVisibility} from './modules/historical-layer.mjs';
const $=s=>document.querySelector(s);
let history,business,anomaly,filterPolicy=null,selectedAreaCode='6765',nativeHistory=null,selectedHistoryCoordinate=[125.55,-18.2],selectedHistoryName='Fitzroy Crossing';
let supportSourceRetained=false;
let ecmwfMean,ecmwfAnomaly,lastSnapshot,statisticalPacket=null,forecastSource='ecmwf',statisticalIssue='2026-10',measureMode='temperature';
const activeBaseline=()=>forecastSource==='namash'?'1991–2020 NASA POWER / MERRA-2':'1993–2016 ECMWF model hindcast';
const displaySeries=()=>measureMode==='anomaly'?selectedSeries(anomaly,selected,'valuesAnomalyC'):selectedSeries(data,selected,measureMode==='probability'?'probability':'valuesC');
let selectionSequence=0,warmPaint=null;
let basemapReady=false,basemapState='loading';
let cameraMode='wa', overview=true,mapReady=false,currentGeneration=null,lastHistoricalUpdate=Promise.resolve(),historyRendered=false,initialMeasured=false,appMeasured=false,mapDelayed=false;
function measureReady(){
 if(PERF&&!appMeasured&&data&&currentGeneration){appMeasured=true;painted('app-ready',0,{scope:'validated source and data controls',basemap:basemapState});}
 if(PERF&&!initialMeasured&&data&&mapReady&&map.getSource('seasonal-grid')&&map.isSourceLoaded('seasonal-grid')){initialMeasured=true;painted('initial-view',0,{localMap:'rendered',history:historyRendered?'rendered':'loading',basemap:basemapReady?'rendered':basemapState});}
}
const snapshots=createSnapshotReader();
const WARM_DEFAULTS=Object.freeze({threshold:0.5,count:3});
const isWater=point=>map.queryRenderedFeatures(point,{layers:['Water',...['Water','Water intermittent','Swimming pool'].map(id=>basemap.prefix+id)].filter(id=>map.getLayer(id))}).length>0;
let selectedAreaMarker;
const selectedPlace=document.createElement('div');selectedPlace.className='place';
let data,fieldIndex=0,selected=cell(125.5,-18.5),selectedTitle='Near Fitzroy Crossing';
const monthText=ym=>new Date(`${ym}-01T12:00:00Z`).toLocaleDateString('en-AU',{month:'long',year:'numeric',timeZone:'UTC'});
const boundaryResponse=await fetch('/wa-boundary.geojson');if(!boundaryResponse.ok)throw Error('Local WA boundary unavailable');
const boundary=await boundaryResponse.json();
const map=new maplibregl.Map({container:'map',style:localStyle(boundary),center:[120.8,-25],zoom:4.05,minZoom:3,maxZoom:12,dragPan:true,dragRotate:false,pitchWithRotate:false,cooperativeGestures:true,attributionControl:false});
map.addControl(new maplibregl.ScaleControl({maxWidth:80,unit:'metric'}),'bottom-left');
map.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');
map.addControl(new maplibregl.AttributionControl({compact:false,customAttribution:'Climate: Copernicus C3S / ECMWF; statistical outlook: Namash / NASA POWER / NOAA; history: SILO / BoM | Basemap: <a href="https://www.maptiler.com/copyright/">© MapTiler</a> / <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>'}),'bottom-right');
let localLabels=[];
function updateLocalLabels(){
 for(const marker of localLabels)marker.remove();localLabels=[];
 if(!mapReady||basemapReady)return;
 const canvas=map.getCanvas();
 for(const place of labelCandidates(GEOGRAPHY.areas,map.getZoom(),p=>map.project(p),canvas.clientWidth,canvas.clientHeight,overview?'':selectedAreaCode)){
  const el=document.createElement('span');el.className='local-town-label';el.textContent=place.name;
  localLabels.push(new maplibregl.Marker({element:el,anchor:'bottom',offset:[0,-4]}).setLngLat(place.referencePoint).addTo(map));
 }
}
const basemap=createBasemap({map,onMounted:polishTownLabels,onState(state){
 const wasReady=basemapReady;basemapState=state;basemapReady=state==='ready';
 $('#map-status').textContent=basemapReady?'Basemap loaded':state==='loading'?'Local WA map · basemap loading':state==='slow'?'Local WA map · basemap slow':'Local WA map · basemap unavailable';
 $('#basemap-details').textContent=basemapReady?'External basemap rendered. Local ABS boundary and climate data remain available independently.':`Local ABS WA boundary, climate grid and town controls are available. External basemap ${state==='loading'?'is loading':state==='slow'?'is taking longer than expected':'is unavailable'}; its tiles are not reported as loaded.`;
 $('#retry-basemap').hidden=basemapReady||state==='loading';
 updateLocalLabels();measureReady();
 if(PERF&&basemapReady&&!wasReady)painted('basemap-ready',0,{basemap:'rendered'});
 if(PERF&&['slow','unavailable'].includes(state))painted('basemap-degraded',0,{basemap:state});
}});
$('#retry-basemap').onclick=()=>basemap.retry();
map.on('sourcedata',measureReady);
const firstLabel=()=>map.getStyle().layers.find(l=>l.type==='symbol')?.id;
const colour=['interpolate',['linear'],['get','valueC'],14,'#679fc8',20,'#c0d9d6',26,'#f6dea2',32,'#e77645',36,'#b51f36'];
function nativeGrid(){const source=measureMode==='anomaly'?{...anomaly,fields:anomaly.fields.map(f=>({...f,valuesC:f.valuesAnomalyC}))}:measureMode==='probability'?{...data,fields:data.fields.map(f=>({...f,valuesC:f.probability}))}:data;return nativeMeanGrid(source,fieldIndex);}
function nearestCell(lon,lat){return nearestNativeCell(data,lon,lat);}
function updateCell(feature,title){feature=cell(Number(feature.properties.lon),Number(feature.properties.lat));selected=feature;selectedTitle=title||`Cell at ${Math.abs(feature.properties.lat)}°S, ${feature.properties.lon}°E`;const {lon,lat}=feature.properties;const d=dimensions(lat);$('#cell-title').textContent=selectedTitle;$('#width').textContent=`${d.width} km`;$('#height').textContent=`${d.height} km`;$('#bounds').textContent=`${Math.abs(lat+.5)}–${Math.abs(lat-.5)}°S · ${lon-.5}–${lon+.5}°E`;if(data){const y=data.latitudes.indexOf(Number(lat)),x=data.longitudes.indexOf(Number(lon));const v=displaySeries()[fieldIndex];$('#cell-value').textContent=measureReading(v,measureMode);$('#cell-value').title=`${MEASURES[measureMode].label}; ${forecastSource==='namash'?'experimental Namash statistical source':'ECMWF monthly ensemble mean'}; native 1° source cell`;updateStatisticalCell();}map.getSource('selected-cell')?.setData({type:'FeatureCollection',features:data&&!overview?[selected]:[]});updateAreaContext();updateHistory();renderChart();updateWarmReadout();}
function renderChart(){
  updateStatisticalCell();
  $('#cell-panel').hidden=overview;$('#monthly-chart').hidden=overview||!data;$('#overview-summary').hidden=!overview||!data;
  $('#rail-title').textContent=overview?'Western Australia':(GEOGRAPHY.areas.find(a=>a.postcode===selectedAreaCode)?.name||'Selected location');
  $('#rail-intro').textContent=overview?'Explore six months of forecast temperature. Select a town or land cell for local context.':'Forecast, historical context and accounts for this location.';
  document.querySelectorAll('.month-chip').forEach((b,i)=>b.setAttribute('aria-pressed',String(i===fieldIndex)));
  if(overview||!data)return;
  const series=displaySeries();
  $('#chart-bars').replaceChildren(...data.fields.map((f,i)=>{const v=series[i];const bar=document.createElement('div');bar.className='chart-bar'+(i===fieldIndex?' active':'');const value=document.createElement('strong');value.textContent=Number.isFinite(v)?measureMode==='probability'?`${Math.round(v*100)}%`:v.toFixed(1):'—';const stem=document.createElement('i');stem.style.height=Number.isFinite(v)?`${Math.max(2,(v-MEASURES[measureMode].domain[0])/(MEASURES[measureMode].domain[1]-MEASURES[measureMode].domain[0])*52)}px`:'0px';const label=document.createElement('span');label.textContent=monthText(f.validMonth).slice(0,3);bar.append(value,stem,label);return bar;}));
}
function buildMonthChips(){ $('#time-rail').hidden=false; $('#warm-months').replaceChildren(...data.fields.map(f=>{const label=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.value=f.validMonth;input.setAttribute('aria-label',`Include ${monthText(f.validMonth)} in warm-month filter`);label.append(input,document.createTextNode(monthText(f.validMonth).slice(0,3)));return label;})); $('#month-chips').replaceChildren(...data.fields.map((f,i)=>{const b=document.createElement('button');b.className='month-chip';b.type='button';b.setAttribute('aria-label',monthText(f.validMonth));b.setAttribute('aria-pressed',String(i===fieldIndex));const name=new Date(`${f.validMonth}-01T12:00:00Z`).toLocaleDateString('en-AU',{month:'short',timeZone:'UTC'});b.append(document.createTextNode(name));const year=document.createElement('small');year.textContent=f.validMonth.slice(0,4);b.append(year);b.onclick=()=>{fieldIndex=i;$('#month').value=String(i);setMonth();};return b;}));}
function setMonth(){const started=performance.now();updateMeasureLegend();map.getSource('seasonal-grid')?.setData(nativeGrid());$('#valid-month').textContent=monthText(data.fields[fieldIndex].validMonth);$('#coverage-note').textContent=`${monthText(data.fields[fieldIndex].validMonth)} · ${MEASURES[measureMode].label}`;updateCell(selected,selectedTitle);painted('forecast-month',started);}
function fitWA(){
  cameraMode='wa';overview=true;selectedAreaCode='';selectedAreaMarker?.remove();
  map.fitBounds([[112.8,-35.5],[129,-13.5]],{padding:{top:83,bottom:125,left:35,right:35},duration:0});
  map.getSource('selected-cell')?.setData({type:'FeatureCollection',features:[]});
  updateAreaContext();updateHistory();renderChart();updateWarmReadout();
  updateLocalLabels();
}
map.on('dragstart',()=>{cameraMode='manual';});
map.on('zoomstart',e=>{if(e.originalEvent)cameraMode='manual';});
window.addEventListener('resize',()=>requestAnimationFrame(()=>{
  map.resize();
  if(cameraMode==='wa')fitWA();
  else if(cameraMode==='area'||cameraMode==='cell'){
    const area=business?.areas.find(a=>a.postcode===selectedAreaCode);
    map.jumpTo({center:area?.referencePoint||selectedHistoryCoordinate});
  }
}));
function polishTownLabels(){
  // The existing provider water polygons mask the forecast at genuine coastlines.
  if(!map.getLayer('Water'))throw Error('Basemap coastline mask unavailable');
  map.setPaintProperty('Water','fill-color','#e9eeed');
  map.setPaintProperty('Background','background-color','#e9eeed');

  // Every town uses provider geography/ranking and collision handling, never temperature.
  for(const layer of map.getStyle().layers){
    if(layer.type!=='symbol'||!['place_label','town_label','city_label'].includes(layer['source-layer']))continue;
    map.setPaintProperty(layer.id,'text-halo-color','#ffffff');
    map.setPaintProperty(layer.id,'text-halo-width',1.6);
    map.setPaintProperty(layer.id,'text-halo-blur',.25);
    map.setPaintProperty(layer.id,'text-color','#283b34');
    map.setLayoutProperty(layer.id,'text-allow-overlap',false);
    map.setLayoutProperty(layer.id,'text-ignore-placement',false);
    map.setLayoutProperty(layer.id,'text-padding',3);
    map.setLayoutProperty(layer.id,'icon-optional',true);
    if(layer.id.endsWith(':Town labels')){
      map.setLayerZoomRange(layer.id,4,16);
      map.setPaintProperty(layer.id,'text-opacity',['step',['zoom'],['case',['<=',['get','rank'],3],1,0],5,1]);
      map.setLayoutProperty(layer.id,'text-size',['interpolate',['linear'],['zoom'],5,11,8,13,12,17]);
      map.setLayoutProperty(layer.id,'text-font',['Roboto Medium','Noto Sans Regular']);
    }
    if(layer.id.endsWith(':Village labels')){
      map.setLayerZoomRange(layer.id,6,24);
      map.setPaintProperty(layer.id,'text-opacity',1);
    }
  }
}
function updateHistory(){
  if(!history)return;
  if(nativeHistory?.metadata){lastHistoricalUpdate=nativeHistory.update({overview,coordinate:selectedHistoryCoordinate,forecastMonth:data?.fields[fieldIndex].validMonth||'2026-10',name:selectedHistoryName||'Selected coordinate'});return;}
  if(overview){$('#history-values').hidden=true;$('#history-title').textContent='12 locality samples';$('#history-period').textContent='1991–2020 · SILO';$('#history-detail').textContent='Purple points show locations with historical daily high and low temperature summaries. Select a point’s cell or a town to see local context.';return;}
  const {lon,lat}=selected.properties;
  const point=historicalPoint(history,selected,selectedAreaCode,!!data);
  $('#history-values').hidden=!point;
  if(!point){$('#history-title').textContent='No local sample in this cell';$('#history-period').textContent='1991–2020 · 12 locality samples available';$('#history-detail').textContent='Purple circles show actual sampled locations. A matching WA historical grid is not loaded.';return;}
  const month=data?Number(data.fields[fieldIndex].validMonth.slice(5)):10;
  const baseline=point.months.find(m=>m.month===month);
  const label=new Date(Date.UTC(2000,month-1,1)).toLocaleDateString('en-AU',{month:'long',timeZone:'UTC'});
  $('#history-title').textContent=point.name;
  $('#history-period').textContent=`Typical ${label} · 1991–2020`;
  $('#history-high').textContent=`${baseline.meanDailyHighC.toFixed(1)} °C`;
  $('#history-low').textContent=`${baseline.meanDailyLowC.toFixed(1)} °C`;
  $('#history-detail').textContent=`Daily highs/lows averaged across ${baseline.days.toLocaleString('en-AU')} historical days. SILO point estimate at ${Math.abs(point.lat).toFixed(2)}°S, ${point.lon.toFixed(2)}°E. Different measure and coverage from the forecast; no anomaly is calculated from these SILO values.`;
}
function containsPoint(point){return cellContainsPoint(selected,point);}
function updateSupportContext(){if(business)renderFinancialSupport(business,overview?null:selectedAreaCode||'unmapped',{retained:supportSourceRetained});}
function updateAreaContext(){
  if(!business)return;
  if(overview){$('#area').options[0].textContent='Choose a town…';$('#area').value='';$('#account-count').textContent=business.totalAccounts;$('#prepaid-count').textContent=business.areas.reduce((n,a)=>n+a.prepaidAccounts,0);$('#billed-count').textContent=business.areas.reduce((n,a)=>n+a.billedAccounts,0);$('#snapshot-date').textContent=new Date(`${business.snapshotDate}T12:00:00Z`).toLocaleDateString('en-AU',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});$('#account-note').textContent=`Across ${business.areas.length} mapped areas. Historical synthetic accounts, checked against open/close dates and recorded snapshot usage.${business.unknownStatusAccounts?` ${business.unknownStatusAccounts} unknown accounts excluded.`:''}${business.notOpenAtSnapshotAccounts?` ${business.notOpenAtSnapshotAccounts} accounts opened after this snapshot and excluded.`:''} Not current account activity.`;$('#income-value').textContent='Select a town';$('#income-scope').textContent='Verified 2021 Census area context is available for mapped business areas.';$('#income-source').hidden=true;selectedAreaMarker?.remove();updateSupportContext();return;}
  const area=mappedArea(business,selected,selectedAreaCode,!!data);
  const reference=GEOGRAPHY.areas.find(a=>a.postcode===selectedAreaCode);
  selectedAreaCode=area?.postcode||reference?.postcode||'';$('#area').options[0].textContent=area||reference?'Choose a town…':'No mapped business area';$('#area').value=selectedAreaCode;
  $('#account-count').textContent=area?area.accountCount.toLocaleString('en-AU'):'—';
  $('#prepaid-count').textContent=area?area.prepaidAccounts.toLocaleString('en-AU'):'—';
  $('#billed-count').textContent=area?area.billedAccounts.toLocaleString('en-AU'):'—';
  $('#snapshot-date').textContent=new Date(`${business.snapshotDate}T12:00:00Z`).toLocaleDateString('en-AU',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
  $('#account-note').textContent=area?`${area.name} · ${area.postcode}. Historical synthetic accounts, checked against recorded open/close dates and snapshot usage. Not current or forecast-month activity.${area.unknownStatusAccounts?` ${area.unknownStatusAccounts} accounts have unknown status and are excluded.`:''}`:reference?`No business rows loaded for ${reference.name} · ${reference.postcode}. Account counts are unavailable.`:'No business area mapped to this climate cell. Account counts are unavailable.';
  const income=area?.financialContext;
  $('#income-value').textContent=income?new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',maximumFractionDigits:0}).format(income.medianWeeklyHouseholdIncomeAUD):'Unavailable';
  $('#income-scope').textContent=income?`${income.geography} · ${income.year} Census. Area context, not an individual account’s income.`:'No verified income context is available for this selected cell.';
  $('#income-source').hidden=!income;if(income)$('#income-source').href=income.sourceUrl;
  if((area||reference)&&selectedAreaMarker){const place=area||reference;selectedPlace.textContent=place.name;selectedAreaMarker.setLngLat(place.referencePoint).addTo(map);}else selectedAreaMarker?.remove();
  updateSupportContext();
}
function selectArea(code){
  const started=performance.now(),selectionId=++selectionSequence;cameraMode='area';overview=false;
  selectedAreaCode=code;
  const area=GEOGRAPHY.areas.find(a=>a.postcode===code);if(!area)return;
  const point=area.referencePoint;selectedHistoryCoordinate=point;selectedHistoryName=area.name;
  if(data)updateCell(nearestCell(...point),area?`Near ${area.name}`:'Near Fitzroy Crossing');else{$('#cell-title').textContent=area?`Near ${area.name}`:'No forecast cell loaded';updateAreaContext();updateHistory();}
  const detailsMs=performance.now()-started;
  const cameraStarted=performance.now();
  const camera=PERF?new Promise(resolve=>map.once('moveend',()=>resolve(performance.now()-cameraStarted))):Promise.resolve();
  const historyTiming=PERF?lastHistoricalUpdate.then(()=>performance.now()-started):Promise.resolve();
  map.easeTo({center:point,zoom:5.4,duration:250});
  if(PERF)Promise.all([camera,historyTiming]).then(([cameraMs,historyMs])=>painted('town-selection',started,{selectionId,detailsMs,cameraMs,historyMs}));
}
$('#area').onchange=e=>{if(e.target.value)selectArea(e.target.value);else fitWA();};
$('#financial').onchange=e=>{$('#financial-panel').hidden=!e.target.checked;};
function updatePosition(){const c=map.getCenter();$('#map-position').textContent=`${Math.abs(c.lat).toFixed(2)}°${c.lat<0?'S':'N'}, ${Math.abs(c.lng).toFixed(2)}°${c.lng<0?'W':'E'} · Zoom ${map.getZoom().toFixed(1)}`;}
map.on('moveend',()=>{updatePosition();updateLocalLabels();});
map.on('load',()=>{polishTownLabels();mapReady=true;const before=firstLabel();map.addSource('selected-cell',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'selected-outline',type:'line',source:'selected-cell',paint:{'line-color':'#183d2b','line-width':2.7}},before);if(cameraMode==='wa')fitWA();if(data)installDataLayers();measureReady();basemap.retry();});
map.on('error',e=>{console.error(e.error?.message||'Map resource error');if(e.sourceId?.startsWith('local-'))$('#map-status').textContent='Local map resource unavailable';});
map.on('click','temperature-fill',e=>{if(e.features?.length&&!isWater(e.point)){cameraMode='cell';overview=false;selectedAreaCode='';selectedHistoryCoordinate=[e.lngLat.lng,e.lngLat.lat];selectedHistoryName=null;updateCell(e.features[0]);}});
map.on('mousemove','temperature-fill',e=>map.getCanvas().style.cursor=isWater(e.point)?'':'crosshair');map.on('mouseleave','temperature-fill',()=>map.getCanvas().style.cursor='');
selectedPlace.textContent='Fitzroy Crossing';
selectedAreaMarker=new maplibregl.Marker({element:selectedPlace,anchor:'bottom',offset:[0,-6]}).setLngLat([125.582,-18.194]);
const perthReference=document.createElement('div');perthReference.className='place';perthReference.textContent='Perth';
// Perth remains a provider city label; selected locations have the dedicated marker.
$('#wa').onclick=()=>fitWA();$('#reset').onclick=()=>fitWA();
$('#fitzroy').onclick=()=>selectArea('6765');
$('#perth').onclick=()=>selectArea('6000');
$('#history-overlay').onchange=e=>{
 setHistoricalVisibility(map,e.target.checked&&!nativeHistory?.metadata);if(nativeHistory?.metadata)nativeHistory.visibility();else $('#history-overlay-state').textContent=e.target.checked?'12 purple sample locations':'Historical layer hidden';
};
map.on('click','historical-samples',e=>{
 const feature=e.features?.[0];if(!feature)return;
 const point=history?.points.find(p=>p.postcode===feature.properties.postcode);if(!point)return;
 cameraMode='cell';overview=false;selectedAreaCode=point.postcode;selectedHistoryCoordinate=[point.lon,point.lat];selectedHistoryName=point.name;
 updateCell(nearestCell(point.lon,point.lat),`Near ${point.name}`);
});
map.on('mouseenter','historical-samples',()=>map.getCanvas().style.cursor='pointer');
map.on('mouseleave','historical-samples',()=>map.getCanvas().style.cursor='');
$('#grid').onchange=e=>{if(map.getLayer('grid-lines')){map.setPaintProperty('grid-lines','line-opacity',e.target.checked?.32:.10);map.setPaintProperty('grid-lines','line-width',e.target.checked?.6:.45);}};
$('#month').onchange=e=>{fieldIndex=Number(e.target.value);setMonth();};
updateCell(selected,selectedTitle);

function selectedFilterIndices(){return [...$('#warm-months').querySelectorAll('input:checked')].map(el=>data.fields.findIndex(f=>f.validMonth===el.value));}
function chosenFilterPolicy(){
  const threshold=$('#warm-threshold').value,minimum=$('#warm-count').value;
  if(threshold===''||minimum==='')throw Error('Choose months, Δ°C and X.');
  return validatePolicy(selectedFilterIndices(),Number(threshold),Number(minimum));
}
function clearFilterLayer(){$('#clear-active-filter').hidden=true;$('#open-warm-filter').textContent='Warm months';warmPaint?.cancel();warmPaint=null;filterPolicy=null;if(anomaly)$('#warm-availability').textContent='Ready';map.getSource('warm-highlight')?.setData({type:'FeatureCollection',features:[]});$('#filter-legend').hidden=true;$('#warm-result').hidden=true;}
function filterInputChanged({periodChanged=false}={}){
  clearFilterLayer();const n=selectedFilterIndices().length;const input=$('#warm-count');input.max=String(n);input.min=n?'1':'0';input.disabled=n===0;
  let adjustment='';
  if(periodChanged){
    const previous=input.value===''?WARM_DEFAULTS.count:Number(input.value);
    const next=n?Math.max(1,Math.min(Number.isFinite(previous)?previous:WARM_DEFAULTS.count,n)):0;
    input.value=String(next);
    if(previous!==next&&n)adjustment=`X adjusted to ${next} for ${n} selected ${n===1?'month':'months'}. `;
  }
  if(!n){$('#warm-apply').disabled=true;$('#warm-status').textContent='Select at least one forecast month. X is disabled; no filter is applied.';return;}
  try{chosenFilterPolicy();$('#warm-apply').disabled=!anomaly;$('#warm-status').textContent=adjustment+'Ready to apply. No filter is applied.';}
  catch(error){$('#warm-apply').disabled=true;$('#warm-status').textContent=`Choose Δ°C and X from 1 to ${n}. No filter is applied.`;}
}
function resetWarmDefaults(){
  $('#warm-months').querySelectorAll('input').forEach(el=>el.checked=true);
  $('#warm-threshold').value=String(WARM_DEFAULTS.threshold);$('#warm-count').value=String(WARM_DEFAULTS.count);$('#warm-count').disabled=false;
  if(anomaly)filterInputChanged({periodChanged:true});else{clearFilterLayer();$('#warm-apply').disabled=true;}
}
function updateWarmReadout(){
  $('#warm-result').hidden=!filterPolicy||overview;
  if(!filterPolicy||!anomaly||overview)return;
  const values=selectedSeries(anomaly,selected,'valuesAnomalyC');
  const result=countMonths(values,filterPolicy.indices,filterPolicy.threshold,filterPolicy.minimum);
  $('#warm-result-reading').textContent=result.count===null?'Count unavailable: missing selected month':`${result.count} of ${result.required} months · ${result.meets?'Matches filter':'Below chosen count'}`;
  $('#warm-result-period').textContent=`At least +${filterPolicy.threshold}°C · X = ${filterPolicy.minimum} · ${activeBaseline()}`;
  $('#warm-result-values').replaceChildren(...filterPolicy.indices.map(i=>{const el=document.createElement('span'),v=values[i];el.textContent=`${monthText(anomaly.fields[i].validMonth).slice(0,3)} ${v===null?'—':`${v>=0?'+':''}${v.toFixed(2)}°`}`;el.title=v===null?'Missing anomaly':`${monthText(anomaly.fields[i].validMonth)}: ${v}°C anomaly (${forecastSource==='namash'?'export rounded to 0.01°C':'unrounded source value'})`;return el;}));
}
$('#warm-months').onchange=()=>filterInputChanged({periodChanged:true});
$('#warm-threshold').oninput=()=>filterInputChanged();$('#warm-count').oninput=()=>filterInputChanged();
$('#warm-all').onclick=()=>{$('#warm-months').querySelectorAll('input').forEach(el=>el.checked=true);filterInputChanged({periodChanged:true});};
$('#warm-reset').onclick=resetWarmDefaults;
$('#warm-apply').onclick=()=>{const started=performance.now();warmPaint?.cancel();warmPaint=PERF?afterSourcePaint(map,'warm-highlight',()=>!!filterPolicy,()=>painted('warm-filter',started)):null;try{if(!anomaly)throw Error('Compatible anomaly data unavailable');filterPolicy=chosenFilterPolicy();$('#warm-availability').textContent='Active';$('#clear-active-filter').hidden=false;$('#open-warm-filter').textContent='Warm months · active';const results=countGrid(anomaly,filterPolicy);map.getSource('warm-highlight')?.setData(outlineMatches(results));$('#filter-legend').textContent=`Filter outline: ≥ +${filterPolicy.threshold}°C in ≥ ${filterPolicy.minimum}/${filterPolicy.indices.length} months`;$('#filter-legend').hidden=false;$('#warm-status').textContent='Filter applied. Outlines mark matching native cells; selected measure colours are unchanged.';updateWarmReadout();warmPaint?.check();}catch(error){clearFilterLayer();$('#warm-status').textContent=error.message;}};

function installDataLayers(){
 if(!mapReady||!data)return;
 const points=historicalFeatures(history);
 if(map.getSource('seasonal-grid'))map.getSource('seasonal-grid').setData(nativeGrid());
 else{map.addSource('seasonal-grid',{type:'geojson',data:nativeGrid()});map.addLayer({id:'temperature-fill',type:'fill',source:'seasonal-grid',filter:['!=',['get','valueC'],null],paint:{'fill-color':colour,'fill-opacity':.82,'fill-antialias':false}},'local-climate-ceiling');map.addLayer({id:'grid-lines',type:'line',source:'seasonal-grid',paint:{'line-color':'#665d48','line-width':.45,'line-opacity':.10}},'local-climate-ceiling');}
 addHistoricalLayer(map,points,'selected-outline');setHistoricalVisibility(map,$('#history-overlay').checked&&!nativeHistory?.metadata);
 if(!map.getSource('warm-highlight')){map.addSource('warm-highlight',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'warm-highlight-outline',type:'line',source:'warm-highlight',paint:{'line-color':'#1e514b','line-width':1.7,'line-opacity':.85}},'local-climate-ceiling');}
 if(filterPolicy)map.getSource('warm-highlight').setData(outlineMatches(countGrid(anomaly,filterPolicy)));
 updateCell(selected,selectedTitle);$('#grid').onchange({target:$('#grid')});
}
function renderSourceStatus(packet){
 const s=packet.status;supportSourceRetained=s.last_good_retained===true;updateSupportContext();const refreshError=s.last_refresh_error||s.climate_refresh_error;
 $('#source-status').textContent=`${s.state==='ready'?'Validated bundle':s.state==='stale'?'Last validated bundle':'Data unavailable'}${s.validated_at?' · Validated '+new Date(s.validated_at).toLocaleString('en-AU',{timeZone:'UTC'})+' UTC':''}${refreshError?' · Refresh failed; previous validation retained':''}${s.earlier_forecast_issue?' · Earlier forecast issue':''}`;
 $('#source-version').textContent=packet.generation?`Bundle ${packet.generation.slice(0,12)} · Forecast issue ${s.climate_issue_date} · Accounts ${s.business_snapshot_date} · Checked ${new Date(s.checked_at).toLocaleString('en-AU',{timeZone:'UTC'})} UTC`:'No validated source bundle loaded.';
 $('#data-status').textContent=!packet.data?'Source data unavailable':refreshError?'Last validated data · refresh failed':s.earlier_forecast_issue?'Validated data · earlier forecast issue':'Genuine CDS data · local download';
 $('#data-status').dataset.state=s.state;
 if(forecastSource==='namash')updateForecastStatus();
}
function installSnapshot(packet){
 const initialLoad=currentGeneration===null;
 const oldIssue=data?.issueDate,oldValidMonth=data?.fields[fieldIndex]?.validMonth;
 const oldSelectedIndices=new Set([...$('#warm-months').querySelectorAll('input')].flatMap((el,i)=>el.checked?[i]:[]));
 const oldPeriod=new Set([...$('#warm-months').querySelectorAll('input:checked')].map(el=>el.value));
 lastSnapshot=packet;({mean:ecmwfMean,anomaly:ecmwfAnomaly,history,business}=packet.data);
 data=forecastSource==='namash'?projectStatistical(statisticalPacket,statisticalIssue):ecmwfMean;
 anomaly=forecastSource==='namash'?data:ecmwfAnomaly;
 const issueChanged=!!oldIssue&&oldIssue!==data.issueDate;
 if(issueChanged){fieldIndex=Math.max(0,data.fields.findIndex(f=>f.validMonth===oldValidMonth));clearFilterLayer();}
 $('.header-period').textContent=`${forecastSource==='namash'?'Namash ML':'ECMWF'} · ${monthText(data.issueDate.slice(0,7))} issue`;
 $('#forecast-issue').hidden=$('#forecast-issue-label').hidden=forecastSource!=='namash';
 $('#forecast-measure option[value=probability]').disabled=forecastSource!=='namash';
 updateForecastStatus();
 $('#overview-summary p').textContent=`${monthText(data.fields[0].validMonth)} – ${monthText(data.fields.at(-1).validMonth)}`;
 $('#area').replaceChildren(new Option('Choose a town…',''),...GEOGRAPHY.areas.slice().sort((a,b)=>a.name.localeCompare(b.name)||a.postcode.localeCompare(b.postcode)).map(a=>new Option(`${a.name} · ${a.postcode}`,a.postcode)));$('#area').disabled=false;
 $('#month').replaceChildren(...data.fields.map((f,i)=>new Option(monthText(f.validMonth),i)));$('#month').disabled=false;$('#forecast-measure').disabled=false;$('#month').value=String(fieldIndex);buildMonthChips();
 $('#warm-months').querySelectorAll('input').forEach((el,i)=>el.checked=initialLoad||(issueChanged?oldSelectedIndices.has(i):oldPeriod.has(el.value)));$('#warm-controls').disabled=false;$('#warm-availability').textContent=filterPolicy?'Active':'Ready';
 $('#issue-date').textContent=forecastSource==='namash'?`${monthText(statisticalIssue)}${data.partial?' · advance / partial inputs':''}`:new Date(`${data.issueDate}T12:00:00Z`).toLocaleDateString('en-AU',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
 $('#legend').hidden=false;$('#overview-summary').hidden=!overview;
 installDataLayers();setMonth();
 if(initialLoad)resetWarmDefaults();else if(!filterPolicy)filterInputChanged({periodChanged:true});
 currentGeneration=packet.generation;measureReady();
}
async function refreshSources(){
 $('#refresh-data').disabled=true;$('#source-status').textContent='Checking local source bundle…';$('#data-status').textContent=data?'Checking data · current view retained':'Loading local source bundle…';
 try{const packet=await snapshots.read();if(packet.data&&packet.generation!==currentGeneration)installSnapshot(packet);renderSourceStatus(packet);
  if(!packet.data){$('#coverage-note').textContent='Source data unavailable';$('#history-title').textContent='Historical context unavailable';$('#history-detail').textContent='No validated source bundle is available.';$('#account-note').textContent='Account context unavailable.';$('#area').disabled=true;$('#month').disabled=true;$('#warm-controls').disabled=true;$('#warm-availability').textContent='Data unavailable';$('#warm-status').textContent='Compatible anomaly data unavailable. No filter is applied.';$('#overview-summary').hidden=true;}
 }finally{$('#refresh-data').disabled=false;}
}
$('#refresh-data').onclick=refreshSources;
refreshSources();

// Keep the existing filter settings together; the map entry only reveals them.
$('#open-warm-filter').onclick=()=>{
 const panel=$('#warm-filter-panel');panel.open=true;
 panel.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
 $('#warm-filter-summary').focus({preventScroll:true});
};
$('#warm-filter-panel').addEventListener('toggle',()=>{
 $('#open-warm-filter').setAttribute('aria-expanded',String($('#warm-filter-panel').open));
});

nativeHistory=createNativeHistory({map,onRendered:()=>{historyRendered=true;measureReady();},onReady:()=>{setHistoricalVisibility(map,false);$('#history-map-key').hidden=false;},onUpdate:updateHistory});
nativeHistory.load();

installSessionControl();

function updateMeasureLegend(){
 const m=MEASURES[measureMode];$('#measure-legend').textContent=`${m.label} · ${m.unit}`;
 const stops=[];for(let i=0;i<m.stops.length;i+=2)stops.push(`${m.stops[i+1]} ${(m.stops[i]-m.domain[0])/(m.domain[1]-m.domain[0])*100}%`);
 $('.colour-bar').style.background=`linear-gradient(to right,${stops.join(',')})`;
 $('.ticks').replaceChildren(...m.ticks.map(t=>{const el=document.createElement('span');el.textContent=t;return el;}));
 $('#forecast-grid-note').textContent=`Native 1° · Fixed scale · No data: unfilled${measureMode==='anomaly'?' · '+activeBaseline():''}`;
 $('#measure-chart-heading').textContent=`${m.label} · ${m.unit}`;$('#monthly-chart').setAttribute('aria-label',`${m.label} by forecast month, ${m.unit}`);
 if(map.getLayer('temperature-fill'))map.setPaintProperty('temperature-fill','fill-color',['interpolate',['linear'],['get','valueC'],...m.stops]);
}
function updateStatisticalCell(){
 const el=$('#statistical-cell-details');el.hidden=forecastSource!=='namash'||overview;
 if(el.hidden)return;
 const r=statisticalCell(statisticalPacket,statisticalIssue,selected.properties.lon,selected.properties.lat,fieldIndex);
 if(!r){el.textContent='No Namash forecast cell covers this location. Account and historical context remain separate.';return;}
 const range=r.low===null||r.high===null?'80% model range unavailable':`80% model range ${r.low.toFixed(1)}–${r.high.toFixed(1)}°C`;
 const skill=r.skill===null?'Hindcast skill unavailable':`Hindcast MSE skill ${r.skill.toFixed(2)}${r.skill<.05?' (little or no skill)':''}`;
 el.textContent=`Experimental: ${measureReading(r.anomaly,'anomaly')} relative to 1991–2020; chance warmer ${measureReading(r.probability,'probability')}. ${range}. ${skill}.`;
}
function updateForecastStatus(){
 const ml=forecastSource==='namash';$('#forecast-source-link').href=ml?'https://github.com/Sploosh4/greenspark-hackathon/tree/e8143867c295cac0071f6e6f90ee5e0295960a95/q3-seasonal-ml':'https://cds.climate.copernicus.eu/datasets/seasonal-monthly-single-levels?tab=overview';
 $('#forecast-source-link').textContent=ml?'Namash statistical source / method ↗':'Copernicus C3S / ECMWF source ↗';
 $('#forecast-source-note').textContent=ml?`Experimental Ridge + LightGBM · ${activeBaseline()}${data.partial?' · Partial October / carried indices':''}`:`ECMWF system 51 · ${activeBaseline()} reference`;
 const details=$('#statistical-method-details');details.hidden=!ml;
 if(ml){
  const state=statisticalPacket.status.issues[statisticalIssue].state;
  $('#data-status').textContent=`Frozen Namash outlook · experimental${state==='advance'?' · advance issue':state==='stale'?' · expired outlook':''}${statisticalPacket.status.last_good_retained?' · last validated export retained':''}`;
  $('#data-status').dataset.state=statisticalPacket.status.state;
  details.textContent=`Namash frozen export 909904199eaf, commit e8143867c295. NASA POWER / MERRA-2 monthly mean T2M; anomaly and probability reference: matching 1991–2020 calendar month. Training through September 2026. ${data.partial?'November is an advance issue using October 1–21 temperature inputs and September Niño 3.4/SAM carried into October.':'October uses complete inputs through September 2026.'} Probability is the model estimate of a warmer-than-average month, not heatwave probability. Final isotonic calibration has not been independently held-out verified. The 80% model range is a Gaussian error estimate from hindcasts, not daily temperature extremes. Published cell skill is the uncorrected ensemble MSE skill vs climatology for 2006–2025, not current-issue confidence. Export values are rounded (temperature/range/normal 0.1°C; anomaly/probability 0.01). Missing cells stay unfilled. ECMWF details below describe the separate available source. No automated refresh runs this ML pipeline.`;
 }
}
function switchForecast(){
 if(!lastSnapshot)return;
 if(forecastSource==='namash'&&!statisticalPacket?.data){$('#forecast-source').value='ecmwf';forecastSource='ecmwf';return;}
 clearFilterLayer();if(forecastSource!=='namash'&&measureMode==='probability'){measureMode='temperature';$('#forecast-measure').value=measureMode;}
 installSnapshot(lastSnapshot);renderSourceStatus(lastSnapshot);
 $('#warm-status').textContent='Source or issue changed. Review selected months and apply the filter again.';
}
$('#forecast-source').onchange=e=>{forecastSource=e.target.value;switchForecast();};
$('#forecast-issue').onchange=e=>{statisticalIssue=e.target.value;switchForecast();};
$('#forecast-measure').onchange=e=>{if(!data)return;measureMode=e.target.value;setMonth();};
readStatistical().then(packet=>{
 statisticalPacket=packet;const option=$('#forecast-source option[value=namash]');option.disabled=!packet.data;option.textContent=packet.data?'Namash ML · experimental':'Namash ML · unavailable';
 if(!packet.data)option.title='The frozen statistical export is unavailable or failed validation.';
}).catch(()=>{const option=$('#forecast-source option[value=namash]');option.disabled=true;option.textContent='Namash ML · unavailable';option.title='Statistical export request or validation failed; ECMWF remains available.';});

$('#clear-active-filter').onclick=()=>filterInputChanged();
