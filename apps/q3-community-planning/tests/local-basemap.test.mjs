import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import {createHash} from 'node:crypto';
import {localStyle,providerLayers,createBasemap,labelCandidates} from '../web/modules/local-basemap.mjs';
import {afterSourcePaint} from '../web/modules/native-history.mjs';
const raw=fs.readFileSync(new URL('../web/wa-boundary.geojson',import.meta.url)),boundary=JSON.parse(raw);
test('fallback uses the exact existing ABS display mask, keeping all islands and rings',()=>{
 assert.equal(createHash('sha256').update(raw).digest('hex'),'b3183583db6307cc4d249b09d429727934b5415d4d1edf24a33bd2259527c1fa');
 const before=JSON.stringify(boundary),style=localStyle(boundary),polygons=boundary.features[0].geometry.coordinates;
 assert.equal(JSON.stringify(boundary),before);assert.equal(polygons.length,2605);assert.equal(style.sources['local-wa'].data,boundary);
 assert.equal(style.sources['local-outside-wa'].data.features[0].geometry.coordinates.length,2606);
 assert.equal(style.sources['local-outside-wa'].data.features.length,1+polygons.reduce((n,p)=>n+p.length-1,0));
 assert.equal(style.glyphs,undefined);assert.equal(style.sprite,undefined);assert.ok(style.layers.some(x=>x.id==='Water'));
});
test('provider adaptation preserves text and sources while omitting optional sprite dependencies',()=>{
 const style={version:8,sources:{planet:{}},layers:[{id:'Background',type:'background'},{id:'POI',type:'symbol',layout:{'icon-image':'x'}},{id:'Town labels',type:'symbol',source:'planet',layout:{'text-field':'{name}','icon-image':'circle'}},{id:'Road',type:'line',source:'planet',paint:{'line-pattern':'sprite','line-color':'#fff'}},{id:'Land',type:'fill',source:'planet'}]};
 const before=JSON.stringify(style),out=providerLayers(style,'basemap-1:');assert.equal(JSON.stringify(style),before);assert.equal(out.length,3);
 assert.equal(out[0].layer.layout['text-field'],'{name}');assert.equal(out[0].layer.layout['icon-image'],undefined);assert.equal(out[0].layer.source,'basemap-1:planet');assert.equal(out[0].placement,'labels');assert.equal(out[1].layer.paint['line-pattern'],undefined);assert.equal(out[2].placement,'below-climate');
});
function harness(fetcher){
 const events=new Map(),layers=new Map(['Water','selected-outline','temperature-fill'].map(id=>[id,{id}])),sources=new Map(),states=[],timers=new Map();let timerId=0,loaded=false;
 const map={on(k,f){if(!events.has(k))events.set(k,new Set());events.get(k).add(f);},getLayer:id=>layers.get(id),getSource:id=>sources.get(id),addLayer:l=>layers.set(l.id,l),addSource:(id,s)=>sources.set(id,s),removeLayer:id=>layers.delete(id),removeSource:id=>sources.delete(id),setGlyphs(){},isSourceLoaded:()=>loaded,areTilesLoaded:()=>loaded};
 const api=createBasemap({map,fetcher,onState:s=>states.push(s),setTimer:(f,ms)=>{timers.set(++timerId,{f,ms});return timerId;},clearTimer:id=>timers.delete(id)});
 return {api,states,map,layers,sources,events,setLoaded:v=>{loaded=v;},fire:(k,e={})=>{for(const f of events.get(k)||[])f(e);},deadline:()=>{const x=[...timers.values()].find(x=>x.ms===4000);assert.ok(x);x.f();},timers};
}
const minimal={version:8,sources:{tiles:{type:'vector',url:'/maptiler/tiles/local/tiles.json'}},layers:[{id:'Road',type:'line',source:'tiles'}]};
test('slow provider never removes local layers and can recover without resetting the map',async()=>{
 let release;const h=harness(()=>new Promise(r=>{release=r;}));const pending=h.api.retry();h.deadline();assert.equal(h.api.state,'slow');assert.ok(h.layers.has('temperature-fill'));
 release({ok:true,json:async()=>minimal});await pending;assert.equal(h.api.state,'slow');h.setLoaded(true);h.fire('sourcedata');assert.equal(h.api.state,'ready');assert.ok(h.layers.has('Water'));assert.ok(h.layers.has('temperature-fill'));
});
test('style failure is explicit and manual retry ignores old source errors',async()=>{
 let n=0;const h=harness(async()=>++n===1?{ok:false}:{ok:true,json:async()=>minimal});await h.api.retry();assert.equal(h.api.state,'unavailable');await h.api.retry();h.setLoaded(true);h.fire('error',{sourceId:'basemap-1:tiles'});h.fire('idle');assert.equal(h.api.state,'ready');assert.ok(h.layers.has('temperature-fill'));
});
test('a current failed tile cannot be called loaded by a later idle event',async()=>{
 const h=harness(async()=>({ok:true,json:async()=>minimal}));await h.api.retry();h.fire('error',{sourceId:'basemap-1:tiles'});h.setLoaded(true);h.fire('idle');assert.equal(h.api.state,'unavailable');
});
test('external readiness does not wait on an unrelated local historical source',async()=>{
 const h=harness(async()=>({ok:true,json:async()=>minimal}));await h.api.retry();h.map.areTilesLoaded=()=>false;h.setLoaded(true);h.fire('sourcedata');assert.equal(h.api.state,'ready');
});
test('historical paint depends only on its own source, never global basemap idle',()=>{
 const listeners=new Set();let ownLoaded=false,current=true,painted=0;const frames=[];const map={on(k,f){assert.equal(k,'sourcedata');listeners.add(f);},off(k,f){listeners.delete(f);},getSource:()=>({}),isSourceLoaded:()=>ownLoaded};
 const watch=afterSourcePaint(map,'history',()=>current,()=>painted++,f=>frames.push(f));watch.check();assert.equal(painted,0);
 ownLoaded=true;for(const f of listeners)f({sourceId:'external'});assert.equal(frames.length,0);for(const f of listeners)f({sourceId:'history'});while(frames.length)frames.shift()();assert.equal(painted,1);assert.equal(listeners.size,0);
 current=false;const old=afterSourcePaint(map,'history',()=>current,()=>painted++,f=>frames.push(f));old.check();while(frames.length)frames.shift()();assert.equal(painted,1);
});
test('local labels use genuine references with scale, collision and selected-town handling',()=>{
 const areas=[{postcode:'6000',name:'Perth',referencePoint:[50,50]},{postcode:'6725',name:'Broome',referencePoint:[55,55]},{postcode:'9999',name:'Other',referencePoint:[200,100]}];
 const project=p=>({x:p[0],y:p[1]});assert.deepEqual(labelCandidates(areas,4,project,400,200,'').map(x=>x.name),['Perth']);assert.deepEqual(labelCandidates(areas,7,project,400,200,'6000').map(x=>x.name),['Broome','Other']);
});
test('explicit cancellation suppresses paint callbacks already queued before rapid reapply',()=>{
 const listeners=new Set(),frames=[];let painted=0;const map={on(k,f){listeners.add(f);},off(k,f){listeners.delete(f);},getSource:()=>({}),isSourceLoaded:()=>true};
 const first=afterSourcePaint(map,'warm',()=>true,()=>{painted+=100;},f=>frames.push(f));first.check();first.cancel();
 const next=afterSourcePaint(map,'warm',()=>true,()=>painted++,f=>frames.push(f));next.check();while(frames.length)frames.shift()();assert.equal(painted,1);assert.equal(listeners.size,0);
});
