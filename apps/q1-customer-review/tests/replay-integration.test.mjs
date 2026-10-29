import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import * as core from '../core.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const original=JSON.parse(readFileSync(root+'replay-data/cohort.json')).review;
function fixture(){const d=structuredClone(original);Object.assign(d,{data_mode:'demo',batch_id:'preloaded',batch_revision:d.snapshot_id});return d;}

test('table filters agree with independently reviewed replay flags for every customer',()=>{
 const d=fixture(),qualified=core.query(d).map(x=>x.customer.customer_id);
 assert.deepEqual(qualified,['C103794']);
 for(const row of d.customers){const x=core.summary(row,d);assert.equal(qualified.includes(row.customer.customer_id),row.replay_evidence.qualifies.M5);assert.equal(x.highest,row.replay_evidence.highest_increase.M5);}
});
test('table and detail use one M5/event-local snapshot with raw S1 context',()=>{
 const d=fixture(),x=core.query(d)[0],e=x.estimates[0];
 assert.ok(Math.abs(e.predicted-30.2332970552)<1e-9);assert.ok(Math.abs(e.increase-7.841469)<1e-6);
 assert.equal(e.event_total,e.predicted*e.duration);assert.equal(x.replay.denominator_policy,'event_local_B');
 assert.ok(Math.abs(e.comparison.predicted-31.8810534043)<1e-9);
 const past=x.episodes.find(e=>e.start==='2024-10-22');assert.equal(past.actual_mean,107.825/4);assert.ok(Math.abs(past.increase_percent+0.188586)<1e-6);
 assert.ok(core.explanation(x).startsWith('In this simulated historical replay,'));
 const source=readFileSync(root+'app.mjs','utf8');const fragment=source.slice(source.indexOf('function recordLabel'),source.indexOf('async function downloadSummary'));
 const nodes=new Map(),$=s=>{if(!nodes.has(s))nodes.set(s,{});return nodes.get(s);};
 const ctx={...core,$,authSession:{isBlocked:()=>false},selected:x.customer.customer_id,range:'recent',document:{querySelectorAll:()=>[]},fmt:n=>n===null?'Unavailable':n.toFixed(1),money:n=>String(n),badge:s=>s,weatherFor:()=> 'Historical oracle weather',dl:rows=>rows.flat().join('|'),timeline:()=>'<div>Recorded timeline retained</div>',downloadSummary:()=>{}};
 vm.createContext(ctx);vm.runInContext(fragment,ctx);ctx.renderDetail(d);
 for(const text of ['+7.8%','31.9 kWh/day','-0.2%','26.96 kWh/day observed','27.01 kWh/day baseline','Recorded timeline retained'])assert.ok($('#content').innerHTML.includes(text),text);
});
function parseCsv(text){let result=[],row=[],cell='',quoted=false;for(let i=0;i<text.length;i++){let c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(cell);cell='';}else if(c==='\n'&&!quoted){row.push(cell.replace(/\r$/,''));result.push(row);row=[];cell='';}else cell+=c;}if(cell||row.length){row.push(cell.replace(/\r$/,''));result.push(row);}return result;}
test('server and client CSV cells agree with the selected table/detail snapshot',()=>{
 const d=fixture(),rows=core.query(d),client=parseCsv(core.exportRows(rows));
 const bytes=readFileSync(root+'replay-data/cohort.csv');
 const server=parseCsv(bytes.toString('utf8').replace(/^\uFEFF/,''));assert.deepEqual(client,server);
 const values=Object.fromEntries(server[0].map((name,i)=>[name,server[1][i]]));assert.equal(values.snapshot_id,d.batch_revision);assert.equal(+values.estimated_daily_import_kwh,rows[0].estimates[0].predicted);
});
test('missing, stable zero, multiple events, lower past threshold and sorting remain consistent',()=>{
 const d=fixture(),row=d.customers.find(r=>r.customer.customer_id==='C103794');
 d.customers=[row];row.episodes=[{...row.episodes[0],increase_percent:200},{...row.episodes[0],increase_percent:0}];
 row.predictions[0].increase=0;row.predictions[0].predicted=row.predictions[0].baseline;
 assert.equal(core.query(d).length,1);assert.equal(core.summary(row,d).threshold,0);
 const other={...d.events[0],id:'unavailable-event'};d.events.push(other);row.predictions.push({event_id:other.id,increase:null,predicted:null,baseline:null,duration:3,reason:'missing_history'});
 const x=core.summary(row,d);assert.equal(x.estimates[1].increase,null);assert.equal(core.query(d,{increase:'unavailable'}).length,1);
 assert.ok(core.explanation(x).includes('Another heat period has no estimate'));
 row.predictions[0].increase=null;row.predictions[0].predicted=null;assert.equal(core.query(d).length,0);assert.equal(core.query(d,{history:'all',increase:'all'}).length,1);
});
test('CSV rejects mixed snapshots and never labels legacy estimates as M5',()=>{
 const d=fixture(),rows=core.query(d),x=rows[0];assert.ok(x.row.legacy_predictions.every(p=>!p.method_id.includes('frozen-v3-M5')));
 assert.throws(()=>core.exportRows([x,{...x,snapshot_id:'different'}]),/Mixed replay snapshots/);
 assert.throws(()=>core.exportRows([x,{...x,replay:null}]),/Mixed replay snapshots/);
});
