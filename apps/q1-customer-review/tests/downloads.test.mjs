import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app.mjs',import.meta.url),'utf8');
const pdf=source.slice(source.indexOf('async function downloadSummary'),source.indexOf('function timeline'));
const csv=source.slice(source.indexOf('async function downloadFiltered'),source.indexOf('function renderUpload'));
function setup(){
 let resolve;const pending=new Promise(r=>resolve=r),saved=[],messages=[];
 const d={batch_revision:'demo-version',customers:[]};
 const ctx={mode:'demo',sessionCsrf:'',requestToken:'test',filters:{},snapshot:d,data:()=>ctx.snapshot,query:()=>[{customer:{customer_id:'C103794'}}],fetch:()=>pending,download:(...args)=>saved.push(args),toast:x=>messages.push(x),TextDecoder,Uint8Array,Error};
 ctx.authSession={isBlocked:()=>false,request:(...args)=>ctx.fetch(...args)};vm.createContext(ctx);vm.runInContext(pdf+'\n'+csv,ctx);
 const response={ok:true,headers:{get:()=> 'application/pdf'},arrayBuffer:async()=>new TextEncoder().encode('%PDF-1.4').buffer};
 return {ctx,d,saved,messages,release:()=>resolve(response)};
}
for(const kind of ['CSV','PDF'])for(const change of ['none','mode','revision'])test(kind+' pins the requested version: '+change,async()=>{
 const x=setup(),button={disabled:false,textContent:'Download'};
 const p=kind==='CSV'?x.ctx.downloadFiltered(x.d,button):x.ctx.downloadSummary(['C103794'],button);
 if(change==='mode')x.ctx.mode='upload';if(change==='revision')x.ctx.snapshot={batch_revision:'new-version'};
 x.release();await p;
 assert.equal(x.saved.length,change==='none'?1:0);assert.equal(button.disabled,false);
 if(change!=='none')assert.ok(x.messages.some(m=>m.includes('changed')));
 if(kind==='CSV'&&change==='none')assert.ok(x.saved[0][0].includes('preloaded'));
});
