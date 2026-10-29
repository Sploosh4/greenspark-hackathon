import {PERF,painted} from './performance.mjs';
export function afterSourcePaint(map,sourceId,isCurrent,onPaint,raf=requestAnimationFrame){
 let finished=false,cancelled=false;
 const detach=()=>{finished=true;map.off('sourcedata',check);};
 const cancel=()=>{cancelled=true;detach();};
 const check=event=>{
  if(finished||event&&event.sourceId!==sourceId)return;
  if(!isCurrent()){cancel();return;}
  if(!map.getSource(sourceId)||!map.isSourceLoaded(sourceId))return;
  detach();raf(()=>raf(()=>{if(!cancelled&&isCurrent()&&map.getSource(sourceId)&&map.isSourceLoaded(sourceId))onPaint();}));
 };
 map.on('sourcedata',check);return {check,cancel};
}
export function validateHistoryMetadata(m){
 if(m?.schema!=='q3-silo-native-history-v2'||m.licence!=='CC BY 4.0'||m.units!=='degC'||m.period?.join('/')!=='2021-10-01/2026-09-30'||m.grid?.width!==323||m.grid?.height!==431||m.grid.dx!==.05||m.grid.dy!==-.05||Object.keys(m.layers||{}).length!==48||m.normal?.sourceInversionCellDays!==585||m.normal?.inputGzipSha256!=='b7a340b2f084e2a0e4ea2bd558e59e5ba752e78abbcb864a8f65c33ff0cda0a7'||m.coverage?.populatedNativeCells!==91180||m.quality?.sourceTminAboveTmaxCellDays!==2623)throw Error('Historical archive contract');return m;
}
export function historicalKey(period,forecastMonth){return ['average','normal'].includes(period)?`${period}-${forecastMonth.slice(5)}`:period;}
export function createNativeHistory({map,onReady,onUpdate,onRendered=()=>{}}){
 const $=s=>document.querySelector(s);let metadata=null,lastImage=null,imageToken=0,desiredImage=null,cellToken=0,lastCell=null,loadingImage=null,pendingPaint=null;
 const periodText=p=>/^\d{4}-\d{2}$/.test(p)?new Date(p+'-01T12:00:00Z').toLocaleDateString('en-AU',{month:'long',year:'numeric',timeZone:'UTC'}):p;
 const api=async url=>{const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw Error('Historical data unavailable');return response.json();};
 function visibility(){const visible=$('#history-overlay').checked;if(map.getLayer('historical-raster'))map.setLayoutProperty('historical-raster','visibility',visible?'visible':'none');$('#history-map-key').hidden=!metadata||!visible;$('#history-overlay-state').textContent=metadata?(visible?'WA land grid · SILO':'Historical layer hidden'):'12 purple sample locations';}
 async function image(key){
  if(key!==desiredImage){desiredImage=key;++imageToken;loadingImage=null;pendingPaint?.cancel();}
  if(!map.getLayer('Water')||key===lastImage||key===loadingImage)return;
  const token=imageToken;loadingImage=key;const started=performance.now();let url=null;
  try{
   const response=await fetch(`/history/${key}.png`);if(!response.ok)throw Error('Historical raster unavailable');url=URL.createObjectURL(await response.blob());const img=new Image();img.src=url;await img.decode();
   if(token!==imageToken||key!==desiredImage){URL.revokeObjectURL(url);return;}
   URL.revokeObjectURL(url);url=null;const imageUrl=`/history/${key}.png`;
   pendingPaint=afterSourcePaint(map,'historical-raster-image',()=>token===imageToken&&key===desiredImage,()=>{onRendered();if(PERF)painted('historical-layer',started);});
   const source=map.getSource('historical-raster-image');
   if(source)source.updateImage({url:imageUrl,coordinates:metadata.image.coordinates});
   else{map.addSource('historical-raster-image',{type:'image',url:imageUrl,coordinates:metadata.image.coordinates});map.addLayer({id:'historical-raster',type:'raster',source:'historical-raster-image',paint:{'raster-opacity':Number($('#history-opacity').value),'raster-resampling':'nearest','raster-fade-duration':0}},map.getLayer('warm-highlight-outline')?'warm-highlight-outline':map.getLayer('local-climate-ceiling')?'local-climate-ceiling':'Water');}
   pendingPaint.check();
   lastImage=key;$('#history-map-period').textContent=periodText(metadata.layers[key].period);visibility();
  }catch(error){if(url)URL.revokeObjectURL(url);if(token===imageToken)$('#history-overlay-state').textContent=lastImage?'History refresh failed; prior raster retained':'Historical raster unavailable';}
  finally{if(token===imageToken)loadingImage=null;}
 }
 function renderCell(result,name){
  $('#history-values').hidden=!result.available;$('#history-midpoint-row').hidden=!result.available;
  $('#history-title').textContent=name||'Selected location';$('#history-period').textContent=periodText(result.period||metadata.layers[result.layer]?.period||'Historical period');
  if(!result.available){$('#history-detail').textContent='No native SILO land value at this selected coordinate. Coastal and island gaps remain unfilled.';$('#history-range').textContent='';return;}
  const v=result.values;$('#history-high').textContent=`${v.tmax.toFixed(1)} °C`;$('#history-low').textContent=`${v.tmin.toFixed(1)} °C`;$('#history-midpoint').textContent=`${v.midpoint.toFixed(1)} °C`;
  $('#history-range').textContent=Number.isFinite(v.midpointMin)?`Five monthly means: ${v.midpointMin.toFixed(1)}–${v.midpointMax.toFixed(1)} °C. ${result.sourceMonths.join(', ')}.`:'';
  $('#history-detail').textContent=`Native 0.05° SILO cell at ${Math.abs(result.nativeCentre[1]).toFixed(2)}°S, ${result.nativeCentre[0].toFixed(2)}°E. Monthly average of daily Tmax/Tmin midpoint; a separate measure from the forecast.${v.qualityFlags?` ${v.qualityFlags} source cell-days flagged Tmin > Tmax; values retained.${Number.isFinite(v.midpointValidPairSensitivity)?` Valid-pair sensitivity changes this midpoint by ${Math.abs(v.midpoint-v.midpointValidPairSensitivity).toFixed(4)} °C.`:''}`:''}${v.rangeFlags?` ${v.rangeFlags} source cell-days outside point-QC range; values retained.`:''}`;
 }
 async function update({overview,coordinate,forecastMonth,name}){
  if(!metadata)return;if(map.getLayer('historical-raster')&&map.getLayer('warm-highlight-outline'))map.moveLayer('historical-raster','warm-highlight-outline');const key=historicalKey($('#history-layer-period').value,forecastMonth);if(!metadata.layers[key])return;
  image(key);const token=++cellToken;
  if(overview){$('#history-values').hidden=true;$('#history-midpoint-row').hidden=true;$('#history-title').textContent='Western Australia';$('#history-period').textContent=periodText(metadata.layers[key].period);$('#history-detail').textContent='Purple shows historical monthly temperature over WA land. Choose a town or cell for the native historical reading.';$('#history-range').textContent='';return;}
  $('#history-period').textContent='Loading historical reading…';
  try{const result=await api(`/api/q3/history/cell?layer=${encodeURIComponent(key)}&lon=${coordinate[0]}&lat=${coordinate[1]}`);if(token!==cellToken)return;lastCell={result,name};renderCell(result,name);}
  catch(error){if(token!==cellToken)return;if(lastCell){renderCell(lastCell.result,lastCell.name);$('#history-detail').textContent+=' Lookup refresh failed; previous reading retained.';}else{$('#history-values').hidden=true;$('#history-midpoint-row').hidden=true;$('#history-period').textContent='Historical reading unavailable';}}
 }
 $('#history-layer-period').onchange=onUpdate;
 $('#history-opacity').oninput=()=>{if(map.getLayer('historical-raster'))map.setPaintProperty('historical-raster','raster-opacity',Number($('#history-opacity').value));};
 return {get metadata(){return metadata;},update,visibility,async load(){
  try{metadata=validateHistoryMetadata(await api('/api/q3/history/metadata'));const options=[new Option('5-year matching monthly average','average'),new Option('1991–2020 matching monthly normal','normal'),...Object.keys(metadata.layers).filter(k=>/^\d{4}-\d{2}$/.test(k)).sort().reverse().map(k=>new Option(new Date(k+'-01T12:00:00Z').toLocaleDateString('en-AU',{month:'long',year:'numeric',timeZone:'UTC'}),k))];$('#history-layer-period').replaceChildren(...options);$('#history-layer-period').disabled=false;$('#history-display-controls').hidden=false;$('#history-coverage-summary').textContent='WA';$('#history-coverage-label').textContent='historical land coverage';onReady();visibility();onUpdate();}
  catch(error){$('#history-overlay-state').textContent='Statewide history unavailable · 12 locality samples';}
 }};
}
