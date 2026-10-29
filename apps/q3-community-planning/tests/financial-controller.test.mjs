import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {installFinancialIntake} from '../web/financial-intake.mjs';

const fixture=JSON.parse(fs.readFileSync(new URL('fixtures/financial-intake-1000-aggregate.json',import.meta.url)));
const names=['customers.csv','consumption_daily.csv.gz','manifest.json','payment_arrangements.csv.gz','hardship_programs.csv.gz','hugs_grants.csv.gz','support_arrangement_history.csv.gz','payments.csv.gz'];
function setup(t,status){
 const originals=new Map(['document','fetch'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 t.after(()=>{for(const[k,d]of originals){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k];}});
 const elements=new Map(),requests=[],generation='b'.repeat(64),jobId='a'.repeat(32);
 const el=k=>{if(!elements.has(k))elements.set(k,{disabled:false,hidden:false,checked:true,textContent:'',value:'',dataset:{},files:[],replaceChildren(...children){this.children=children;},scrollIntoView(){},focus(){}});return elements.get(k);};
 globalThis.document={querySelector:el,createElement:()=>({append(){},textContent:''})};
 el('#financial-files').files=names.map(name=>new File(['transport fixture'],name));
 const reply=(body,ok=true)=>({ok,json:async()=>body});
 globalThis.fetch=async(url,opts)=>{requests.push([url,opts]);
  if(url==='/api/session')return reply({authenticated:false,enforcementConfigured:false,mode:'local-preview'});
  if(url.endsWith('/stage'))return reply({state:'accepted',jobId});
  if(url.includes('/stage-status'))return status?status(reply):reply({jobId,state:'ready',result:{stageId:'e'.repeat(32),baseGeneration:generation,proposedSupport:fixture.support,areaCount:fixture.support.areas.length}});
  if(url.endsWith('/replace')||url.endsWith('/discard'))return reply({replaced:true});
  throw Error('Unexpected request '+url);
 };
 let reloads=0;const controller=installFinancialIntake({reload:async()=>{reloads++;},lookup:el});
 controller.update({generation,data:{business:fixture.business}});
 return {el,requests,submit:()=>el('#financial-upload').onsubmit({preventDefault(){}}),reloads:()=>reloads};
}
test('eight files stage a dated review; only explicit Replace attaches support',async t=>{
 const s=setup(t);await s.submit();assert.equal(s.reloads(),0);
 assert.match(s.el('#financial-summary').textContent,/3 arrangement accounts.*4 hardship accounts.*7 in either/);
 assert.equal(s.el('#financial-review').hidden,false);assert.equal(s.el('#financial-replace').disabled,false);
 const stage=s.requests.find(([url])=>url.endsWith('/stage'));
 assert.equal(Array.from(stage[1].body.keys()).length,10);
 assert.equal(s.requests.some(([url])=>url.endsWith('/replace')),false);
 await s.el('#financial-replace').onclick();assert.equal(s.reloads(),1);
 assert.equal(s.el('#financial-review').hidden,true);assert.equal(s.el('#financial-stage').disabled,false);
});
test('partial or duplicate packages never leave the browser',async t=>{
 const s=setup(t);s.el('#financial-files').files.pop();await s.submit();
 assert.match(s.el('#financial-status').textContent,/exactly the eight/);assert.equal(s.requests.length,0);
 s.el('#financial-files').files=names.map(()=>new File(['fixture'],'customers.csv'));await s.submit();assert.equal(s.requests.length,0);
});
test('failed validation clears pending and permits a corrected stage',async t=>{
 const s=setup(t,reply=>reply({jobId:'a'.repeat(32),state:'failed',error:'financial_cohort_mismatch'}));await s.submit();
 assert.match(s.el('#financial-status').textContent,/do not match/);assert.equal(s.el('#financial-stage').disabled,false);assert.equal(s.reloads(),0);
});
test('expired receipt clears pending without uploading again',async t=>{
 const s=setup(t,reply=>reply({error:'validation_receipt_missing_or_expired'},false));await s.submit();
 assert.match(s.el('#financial-status').textContent,/receipt expired/);assert.equal(s.el('#financial-stage').disabled,false);
 assert.equal(s.requests.filter(([url])=>url.endsWith('/stage')).length,1);assert.equal(s.reloads(),0);
});
