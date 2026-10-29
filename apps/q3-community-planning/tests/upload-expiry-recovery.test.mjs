// Real staged business module with fake DOM and transport. No browser/listener.
// Asserts required recovery; fails until a definitive expired receipt is cleared.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const stage=new URL('../',import.meta.url);
test('definitively expired receipt allows staging again without page reload',async t=>{
 const original=new Map(['document','fetch'].map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));
 t.after(()=>{for(const [name,descriptor] of original){if(descriptor)Object.defineProperty(globalThis,name,descriptor);else delete globalThis[name];}});
 const elements=new Map();
 const element=selector=>{
  if(!elements.has(selector))elements.set(selector,{disabled:false,hidden:false,checked:true,value:'',textContent:'',dataset:{},files:[],replaceChildren(){},scrollIntoView(){},focus(){}});
  return elements.get(selector);
 };
 globalThis.document={querySelector:element};
 const read=name=>JSON.parse(fs.readFileSync(new URL('data/inputs/'+name,stage)));
 const packet={schema_version:1,generation:'a'.repeat(64),status:{state:'ready'},data:{mean:read('seasonal-data.json'),anomaly:read('anomaly-data.json'),history:read('historical-context.json'),business:read('q3-area-context.json')}};
 const id='a'.repeat(32),reply=(body,ok=true)=>({ok,json:async()=>body});
 globalThis.fetch=async url=>{
  if(url==='/api/q3/snapshot')return reply(packet);
  if(url==='/api/session')return reply({authenticated:false,enforcementConfigured:false,mode:'local-preview'});
  if(url==='/api/q3/business/stage')return reply({jobId:id,state:'accepted'});
  if(url==='/api/q3/business/stage-status?id='+id)return reply({error:'validation_receipt_missing_or_expired'},false);
  throw Error('Unexpected request: '+url);
 };
 await import(new URL('web/business.mjs?review-expiry-recovery',stage));
 await new Promise(resolve=>setImmediate(resolve));
 element('#customers').files=[new File(['synthetic fixture'],'customers.csv')];
 element('#usage').files=[new File(['synthetic fixture'],'consumption_daily.csv')];
 element('#synthetic').checked=true;
 await element('#upload').onsubmit({preventDefault(){}});
 assert.equal(element('#stage').disabled,false,'A known missing/expired receipt must not leave Stage locked');
 assert.equal(element('#resume-validation').hidden,true,'Do not offer endless status checks for a definitive expiry');
});
