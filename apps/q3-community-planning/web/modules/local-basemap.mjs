// The shipped ABS display geometry stays available without provider tiles/fonts.
export const BASEMAP_PREFIX='basemap-';
const area=ring=>ring.reduce((n,p,i)=>{const q=ring[(i+1)%ring.length];return n+p[0]*q[1]-q[0]*p[1];},0);
export function localStyle(boundary){
 const f=boundary?.features?.[0];
 if(boundary.type!=='FeatureCollection'||boundary.features.length!==1||f?.geometry?.type!=='MultiPolygon'||f.properties?.state_code_2021!=='5'||f.properties?.state_name_2021!=='Western Australia')throw Error('Local WA boundary unavailable');
 const polygons=f.geometry.coordinates;
 const holes=polygons.map(p=>area(p[0])>0?p[0].slice().reverse():p[0]);
 const outside={type:'FeatureCollection',features:[{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[-180,-85],[180,-85],[180,85],[-180,85],[-180,-85]],...holes]}},...polygons.flatMap(p=>p.slice(1).map(r=>({type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[area(r)<0?r.slice().reverse():r]}})))]};
 return {version:8,name:'Local WA',sources:{'local-wa':{type:'geojson',data:boundary,attribution:'WA boundary: ABS ASGS 2021, CC BY 4.0'},'local-outside-wa':{type:'geojson',data:outside}},layers:[{id:'Background',type:'background',paint:{'background-color':'#e9eeed'}},{id:'local-wa-land',type:'fill',source:'local-wa',paint:{'fill-color':'#f1f1e9'}},{id:'local-climate-floor',type:'background',paint:{'background-opacity':0}},{id:'local-climate-ceiling',type:'background',paint:{'background-opacity':0}},{id:'Water',type:'fill',source:'local-outside-wa',paint:{'fill-color':'#e9eeed'}},{id:'local-wa-coast',type:'line',source:'local-wa',paint:{'line-color':'#8b9d94','line-width':.7,'line-opacity':.65}}]};
}

export function providerLayers(style,prefix){
 if(style?.version!==8||!style.sources||!Array.isArray(style.layers))throw Error('Basemap style unavailable');
 return style.layers.flatMap(original=>{
  if(original.type==='background'||original.type==='symbol'&&!original.layout?.['text-field'])return [];
  const layer=structuredClone(original);layer.id=prefix+layer.id;
  if(layer.source)layer.source=prefix+layer.source;if(layer.ref)layer.ref=prefix+layer.ref;
  // Decorative sprites/patterns are omitted. Town text keeps provider glyphs;
  // unrelated sprite loading must not gate the local climate sources.
  if(layer.layout)delete layer.layout['icon-image'];
  if(layer.paint)for(const key of Object.keys(layer.paint))if(key.endsWith('-pattern'))delete layer.paint[key];
  if(['Water','Water intermittent','Swimming pool'].includes(original.id)&&layer.paint)layer.paint['fill-color']='#e9eeed';
  return [{layer,placement:layer.type==='symbol'?'labels':layer.type==='line'||['Water','Water intermittent','Swimming pool'].includes(original.id)?'above-climate':'below-climate'}];
 });
}

export function createBasemap({map,onState,onMounted=()=>{},fetcher=fetch,deadlineMs=4000,styleTimeoutMs=8000,setTimer=setTimeout,clearTimer=clearTimeout}){
 let state='loading',attempt=0,installed=false,failed=false,layers=[],sources=[],deadline=null,abort=null;
 const emit=next=>{if(state!==next){state=next;onState(state);}};
 function check(){if(installed&&!failed&&sources.every(id=>map.isSourceLoaded(id))){clearTimer(deadline);emit('ready');}}
 function onError(e){const id=e.sourceId||e.error?.sourceId;if(id?.startsWith(`${BASEMAP_PREFIX}${attempt}:`)||installed&&!id&&String(e.error?.message||'').includes('/maptiler/')){failed=true;emit('unavailable');}}
 map.on('idle',check);map.on('sourcedata',check);map.on('error',onError);
 async function retry(){
  const current=++attempt;abort?.abort();clearTimer(deadline);installed=false;failed=false;
  for(const id of layers)if(map.getLayer(id))map.removeLayer(id);
  for(const id of sources)if(map.getSource(id))map.removeSource(id);
  layers=[];sources=[];state='loading';onState(state);
  deadline=setTimer(()=>{if(current===attempt&&state!=='ready'&&state!=='unavailable')emit('slow');},deadlineMs);
  const controller=new AbortController();abort=controller;
  const timeout=setTimer(()=>controller.abort(),styleTimeoutMs);
  try{
   const response=await fetcher('/maptiler/maps/streets-v4/style.json',{signal:controller.signal,cache:'no-store'});if(!response.ok)throw Error('Basemap style unavailable');
   const style=await response.json();if(current!==attempt)return;
   const prefix=`${BASEMAP_PREFIX}${current}:`,prepared=providerLayers(style,prefix);
   if(style.glyphs)map.setGlyphs(style.glyphs);
   for(const [name,source]of Object.entries(style.sources)){const id=prefix+name;map.addSource(id,source);sources.push(id);}
   for(const {layer,placement}of prepared){const before=placement==='labels'?'selected-outline':placement==='above-climate'?'Water':map.getLayer('local-climate-floor')?'local-climate-floor':'Water';map.addLayer(layer,map.getLayer(before)?before:undefined);layers.push(layer.id);}
   installed=true;onMounted();check();
  }catch(error){if(current===attempt){failed=true;emit('unavailable');}}
  finally{clearTimer(timeout);}
 }
 return {retry,get state(){return state;},get prefix(){return `${BASEMAP_PREFIX}${attempt}:`;}};
}

const major=['6000','6725','6721','6714','6765','6743','6531','6430','6330','6450','6701','6707'];
export function labelCandidates(areas,zoom,project,width,height,selected){
 const ranked=areas.filter(a=>a.postcode!==selected&&(zoom>=6.5||major.includes(a.postcode))).sort((a,b)=>{const ai=major.indexOf(a.postcode),bi=major.indexOf(b.postcode);return (ai<0?999:ai)-(bi<0?999:bi)||a.name.localeCompare(b.name);});
 const chosen=[];
 for(const a of ranked){const p=project(a.referencePoint);if(p.x<20||p.y<20||p.x>width-20||p.y>height-20||chosen.some(x=>Math.abs(x.x-p.x)<90&&Math.abs(x.y-p.y)<28))continue;chosen.push({...a,x:p.x,y:p.y});if(chosen.length===40)break;}
 return chosen;
}
