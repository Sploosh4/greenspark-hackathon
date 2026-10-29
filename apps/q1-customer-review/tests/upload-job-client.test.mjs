import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import vm from 'node:vm';
const source=readFileSync(new URL('../app.mjs',import.meta.url),'utf8');
const functions=source.slice(source.indexOf('async function waitForUploadJob'),source.indexOf('function showReplaceDialog'));
function setup(fetch){
 const ctx={uploadBusy:false,uploadOperation:'known-operation',uploadJobPending:true,uploadAttemptGeneration:0,uploadAbort:null,uploadError:'',pendingUpload:null,view:'upload',renderUpload:()=>{},fetch,encodeURIComponent,Error,DOMException,AbortController,AbortSignal,performance:{now:()=>0},setTimeout:fn=>{fn();}};
 ctx.authSession={isBlocked:()=>false,request:(...args)=>ctx.fetch(...args)};vm.createContext(ctx);vm.runInContext(functions,ctx);return ctx;
}
test('known operation can resume its ready receipt without resubmitting files',async()=>{
 const calls=[],receipt={stage_id:'known-operation'},ctx=setup(async path=>{calls.push(path);return {ok:true,json:async()=>({state:'ready',receipt})};});
 await ctx.resumeUploadJob();assert.equal(calls.length,1);assert.ok(calls[0].includes('status?request_id=known-operation'));assert.equal(ctx.pendingUpload,receipt);assert.equal(ctx.uploadBusy,false);assert.equal(ctx.uploadJobPending,false);
});
test('unknown outcome keeps operation available for resume or cancellation',async()=>{
 const ctx=setup(async()=>{throw Error('Network unavailable');});await ctx.resumeUploadJob();assert.equal(ctx.uploadOperation,'known-operation');assert.equal(ctx.uploadJobPending,true);assert.equal(ctx.uploadBusy,false);assert.match(ctx.uploadError,/Network/);
});
test('restart/absent job clears only pending candidate state',async()=>{
 const ctx=setup(async()=>({ok:false,status:404,json:async()=>({error:'Job unavailable'})}));await ctx.resumeUploadJob();assert.equal(ctx.uploadOperation,null);assert.equal(ctx.uploadJobPending,false);assert.equal(ctx.pendingUpload,null);assert.equal(ctx.uploadBusy,false);
});
test('failed validation exposes terminal outcome and permits a new candidate',async()=>{
 const ctx=setup(async()=>({ok:true,json:async()=>({state:'failed',error:'Bad schema'})}));await ctx.resumeUploadJob();assert.equal(ctx.uploadJobPending,false);assert.equal(ctx.uploadBusy,false);assert.match(ctx.uploadError,/Bad schema/);
});
test('cancellation invalidates a delayed resume response',async()=>{
 let release;const ctx=setup(()=>new Promise(resolve=>release=resolve));const running=ctx.resumeUploadJob();ctx.uploadAttemptGeneration++;ctx.uploadOperation=null;ctx.uploadBusy=false;ctx.uploadJobPending=false;
 release({ok:true,json:async()=>({state:'ready',receipt:{stage_id:'known-operation'}})});await running;assert.equal(ctx.pendingUpload,null);assert.equal(ctx.uploadBusy,false);
});
