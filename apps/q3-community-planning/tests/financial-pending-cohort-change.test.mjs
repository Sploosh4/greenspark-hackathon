// Real staged controller, synthetic aggregate fixture and deferred transport.
// No browser, listener, raw upload persistence or application-file changes.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {installFinancialIntake} from '../web/financial-intake.mjs';

test('a changed cohort before ready does not offer a dead resume button',async t=>{
 const original=new Map(['document','fetch'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 t.after(()=>{for(const [k,d] of original){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k];}});
 const fixture=JSON.parse(fs.readFileSync(new URL('fixtures/financial-intake-1000-aggregate.json',import.meta.url)));
 const elements=new Map();
 const element=k=>{if(!elements.has(k))elements.set(k,{disabled:false,hidden:false,checked:true,textContent:'',value:'',dataset:{},files:[],replaceChildren(){},scrollIntoView(){},focus(){}});return elements.get(k);};
 globalThis.document={querySelector:element,createElement:()=>({append(){},textContent:''})};
 const names=['customers.csv','consumption_daily.csv.gz','manifest.json','payment_arrangements.csv.gz','hardship_programs.csv.gz','hugs_grants.csv.gz','support_arrangement_history.csv.gz','payments.csv.gz'];
 element('#financial-files').files=names.map(name=>new File(['synthetic transport fixture'],name));
 element('#financial-synthetic').checked=true;
 const jobId='a'.repeat(32),generation='b'.repeat(64);
 const reply=(body,ok=true)=>({ok,json:async()=>body});
 let resolveStatus;
 const pendingStatus=new Promise(resolve=>{resolveStatus=resolve;});
 globalThis.fetch=async url=>{
  if(url==='/api/session')return reply({authenticated:false,enforcementConfigured:false,mode:'local-preview'});
  if(url==='/api/q3/financial/stage')return reply({state:'accepted',jobId});
  if(url==='/api/q3/financial/stage-status?id='+jobId)return pendingStatus;
  if(url==='/api/q3/financial/discard')return reply({discarded:true});
  throw Error('Unexpected request: '+url);
 };
 const controller=installFinancialIntake({reload:async()=>{},lookup:element});
 controller.update({generation,data:{business:fixture.business}});
 const submission=element('#financial-upload').onsubmit({preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 const changed=structuredClone(fixture.business);
 changed.customerSourceSha256='c'.repeat(64); // Test-only later cohort identity.
 controller.update({generation:'d'.repeat(64),data:{business:changed}});
 resolveStatus(reply({jobId,state:'ready',result:{stageId:'e'.repeat(32),baseGeneration:generation,proposedSupport:fixture.support,snapshotDate:fixture.support.snapshotDate,areaCount:fixture.support.areas.length}}));
 await submission;
 assert.equal(element('#financial-resume').hidden,true,'Ready receipt cannot be resumed after its local pending ID was cleared');
 assert.match(element('#financial-status').textContent,/source changed|cohort changed|discard/i);
 assert.equal(element('#financial-replace').disabled,true);
 assert.equal(element('#financial-discard').disabled,false);
 await element('#financial-discard').onclick();
 assert.equal(element('#financial-stage').disabled,false);
 assert.equal(element('#financial-review').hidden,true);
});
