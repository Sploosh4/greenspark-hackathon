// Functional async regression only. No browser, HTTP server or source-file edits.
// Uses the real staged controller and metadata, with deferred fetch and map/DOM
// stubs. It checks orchestration, not PNG decoding or MapLibre rendering.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createNativeHistory} from '../web/modules/native-history.mjs';

const metadata=JSON.parse(fs.readFileSync(new URL('../data/history/metadata.json',import.meta.url)));
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('A displayed → B pending → A selected rejects delayed B raster',async t=>{
 const original=new Map(['document','Option','Image','fetch','requestAnimationFrame'].map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));
 t.after(()=>{
  for(const [name,descriptor] of original){
   if(descriptor)Object.defineProperty(globalThis,name,descriptor);
   else delete globalThis[name];
  }
 });
 const elements=new Map();
 const element=selector=>{
  if(!elements.has(selector))elements.set(selector,{
   checked:true,value:selector==='#history-opacity'?'.55':'average',
   textContent:'',hidden:false,replaceChildren(){}
  });
  return elements.get(selector);
 };
 globalThis.document={querySelector:element};
 globalThis.Option=class {};
 globalThis.Image=class {async decode(){}};
 globalThis.requestAnimationFrame=fn=>setImmediate(fn);
 let resolveB;
 const pendingB=new Promise(resolve=>{resolveB=resolve;});
 const requests=[];
 const imageResponse=()=>({ok:true,blob:async()=>new Blob(['test-image-bytes'])});
 globalThis.fetch=async url=>{
  requests.push(url);
  if(url==='/api/q3/history/metadata')return {ok:true,json:async()=>metadata};
  if(url==='/history/average-11.png')return pendingB;
  if(url==='/history/average-10.png')return imageResponse();
  throw Error('Unexpected request: '+url);
 };
 const layers=new Map([['Water',{}],['warm-highlight-outline',{}]]);
 const sources=new Map(),installed=[];
 const map={
  getLayer:key=>layers.get(key),getSource:key=>sources.get(key),
  addSource(key,source){
   sources.set(key,{...source,updateImage(value){installed.push(value.url);}});
   installed.push(source.url);
  },
  addLayer(layer){layers.set(layer.id,layer);},
  once(){},on(){},off(){},isSourceLoaded:()=>true,moveLayer(){},setLayoutProperty(){},setPaintProperty(){}
 };
 const controller=createNativeHistory({map,onReady(){},onUpdate(){}});
 await controller.load();
 assert.ok(controller.metadata,'Real metadata passes the production boundary');

 await controller.update({overview:true,forecastMonth:'2026-10'});
 await flush();await flush();
 assert.deepEqual(installed,['/history/average-10.png']);

 await controller.update({overview:true,forecastMonth:'2026-11'});
 assert.ok(requests.includes('/history/average-11.png'),'B is in flight');
 await controller.update({overview:true,forecastMonth:'2026-10'});
 resolveB(imageResponse());
 await flush();await flush();

 assert.deepEqual(installed,['/history/average-10.png'],'Delayed B must never replace A');
 assert.equal(element('#history-map-period').textContent,metadata.layers['average-10'].period);
 assert.equal(element('#history-period').textContent,metadata.layers['average-10'].period);
});
