import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app.mjs',import.meta.url),'utf8');
const refresh=source.slice(source.indexOf('async function refreshUploaded'),source.indexOf('async function downloadFiltered'));
for(const change of ['none','revision','batch','removed'])test('status refresh keeps token fresh and fetches only a changed snapshot: '+change,async()=>{
 const previous={batch_id:'A',batch_revision:'v1'},state={active_batch:'A',revision:'v1',request_token:'new-token',recovery:'visible recovery'};
 if(change==='revision')state.revision='v2';if(change==='batch')state.active_batch='B';if(change==='removed')state.active_batch=null;
 const calls=[],ctx={uploaded:previous,uploadRefreshGeneration:0,uploadState:{},requestToken:'old',encodeURIComponent,Error,fetch:async path=>{calls.push(path);return {ok:true,json:async()=>path==='api/state'?state:{batch_id:state.active_batch,batch_revision:state.revision}};}};
 ctx.authSession={isBlocked:()=>false,request:(...args)=>ctx.fetch(...args)};vm.createContext(ctx);vm.runInContext(refresh,ctx);await ctx.refreshUploaded();
 assert.equal(ctx.requestToken,'new-token');assert.equal(ctx.uploadState.recovery,'visible recovery');
 assert.equal(calls.length,['none','removed'].includes(change)?1:2);
 if(change==='none')assert.equal(ctx.uploaded,previous);
 else if(change==='removed')assert.equal(ctx.uploaded,null);
 else assert.equal(ctx.uploaded.batch_revision,state.revision);
});
test('out-of-order state and review responses cannot overwrite a newer refresh',async()=>{
 const pending=[],ctx={uploaded:null,uploadRefreshGeneration:0,uploadState:{},requestToken:'old',encodeURIComponent,Error,fetch:path=>new Promise(resolve=>pending.push({path,resolve}))};
 ctx.authSession={isBlocked:()=>false,request:(...args)=>ctx.fetch(...args)};vm.createContext(ctx);vm.runInContext(refresh,ctx);
 const reply=(item,value)=>item.resolve({ok:true,json:async()=>value}),flush=async()=>{for(let i=0;i<6;i++)await Promise.resolve();};
 const first=ctx.refreshUploaded();reply(pending[0],{active_batch:'B',revision:'v2',request_token:'token2'});await flush();
 assert.ok(pending[1].path.includes('v2'));
 const second=ctx.refreshUploaded();reply(pending[2],{active_batch:'C',revision:'v3',request_token:'token3'});await flush();
 reply(pending[3],{batch_id:'C',batch_revision:'v3'});await second;
 reply(pending[1],{batch_id:'B',batch_revision:'v2'});await first;
 assert.equal(ctx.uploaded.batch_revision,'v3');assert.equal(ctx.uploadState.revision,'v3');assert.equal(ctx.requestToken,'token3');
 const third=ctx.refreshUploaded(),fourth=ctx.refreshUploaded();
 reply(pending[5],{active_batch:null,revision:'v4',request_token:'token4'});await fourth;
 reply(pending[4],{active_batch:'B',revision:'v2',request_token:'token2'});await third;
 assert.equal(ctx.uploaded,null);assert.equal(ctx.uploadState.revision,'v4');assert.equal(ctx.requestToken,'token4');
});
test('a changed or failed review does not retain an older uploaded snapshot',async()=>{
 for(const failure of ['mismatch','http']){
  const ctx={uploaded:{batch_id:'A',batch_revision:'v1'},uploadRefreshGeneration:0,uploadState:{},requestToken:'old',encodeURIComponent,Error,fetch:async path=>({ok:path==='api/state'||failure!=='http',json:async()=>path==='api/state'?{active_batch:'B',revision:'v2',request_token:'token2'}:{batch_id:'B',batch_revision:'unexpected',error:'changed'}})};
  ctx.authSession={isBlocked:()=>false,request:(...args)=>ctx.fetch(...args)};vm.createContext(ctx);vm.runInContext(refresh,ctx);await assert.rejects(ctx.refreshUploaded());assert.equal(ctx.uploaded,null);
 }
});
