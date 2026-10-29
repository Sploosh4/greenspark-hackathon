import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as core from '../core.mjs';
const root=new URL('../',import.meta.url);
const get=name=>JSON.parse(readFileSync(new URL('tests/fixtures/'+name,root),'utf8'));
const fixture=()=>get('current-model-example.json');
const app=readFileSync(new URL('app.mjs',root),'utf8');
function dom(){const nodes=new Map();return {nodes,$:s=>{if(!nodes.has(s))nodes.set(s,{});return nodes.get(s);}};}
function csv(text){let result=[],row=[],cell='',quoted=false;for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(cell);cell='';}else if(c==='\n'&&!quoted){row.push(cell.replace(/\r$/,''));result.push(row);row=[];cell='';}else cell+=c;}if(cell||row.length){row.push(cell.replace(/\r$/,''));result.push(row);}return result;}

test('current default table exposes the fixed scenario while historical filters stay separate',()=>{
 const d=fixture(),rows=core.query(d);assert.equal(rows.length,2);
 for(const x of rows){assert.equal(x.estimates.length,1);assert.equal(x.estimates[0].duration,7);assert.equal(x.row.reporting_lag_days,2);assert.equal(x.estimates[0].feature_evidence.usage_n7,6);assert.ok(core.explanation(x).includes('current-date synthetic scenario'));assert.equal(x.estimates[0].event_total,x.estimates[0].predicted*7);}
 assert.equal(core.query(d,{history:'linked'}).length,0);
});
test('actual current table and detail render M5/S1, reported lag and source vintage',()=>{
 const d=fixture(),ui=dom(),ctx={...core,...ui,authSession:{isBlocked:()=>false},previewState:'normal',filters:{...core.DEFAULT_FILTERS,history:'all',increase:'all'},queuePage:0,preparedSummaries:new WeakMap(),selectedCustomers:new Set(),document:{querySelectorAll:()=>[]},reset:()=>{},openCustomer:()=>{},downloadFiltered:()=>{},downloadSummary:()=>{},measureUI:(_,fn)=>fn(),fmt:n=>n==null?'Unavailable':n.toFixed(1),money:n=>String(n),badge:s=>s,weatherFor:()=> 'Modelled temperatures',dl:rows=>rows.flat().join('|'),timeline:()=>'<div>Recorded timeline</div>',selected:d.customers[0].customer.customer_id,range:'recent'};
 vm.createContext(ctx);vm.runInContext(app.slice(app.indexOf('function renderQueue'),app.indexOf('function reset')),ctx);ctx.renderQueue(d);
 assert.ok(ui.$('#content').innerHTML.includes('Current 7-day scenario'));assert.ok(ui.$('#queue').innerHTML.includes(d.customers[0].customer.customer_id));
 vm.runInContext(app.slice(app.indexOf('function recordLabel'),app.indexOf('async function downloadSummary')),ctx);ctx.renderDetail(d);
 for(const value of ['Current synthetic scenario','2-day lag','Simple baseline (S1)','Scenario data',d.current_demo.weather_retrieved_at,'Recorded timeline'])assert.ok(ui.$('#content').innerHTML.includes(value),value);
});
test('client and real server CSV cells agree including receipt and unknown issue time',()=>{
 const d=fixture(),client=csv(core.exportRows(core.query(d))),server=csv(readFileSync(new URL('tests/fixtures/current-model-example.csv',root),'utf8').replace(/^\uFEFF/,''));
 // The UI sorts by increase; compare customer rows by reference.
 assert.deepEqual(client[0],server[0]);assert.deepEqual(client.slice(1).sort(),server.slice(1).sort());
 const row=Object.fromEntries(client[0].map((k,i)=>[k,client[1][i]]));assert.equal(row.reporting_lag_days,'2');assert.equal(row.provider_issue_at,'');assert.equal(row.application_received_at,d.current_demo.business_received_at);assert.equal(row.snapshot_id,d.batch_revision);
});
test('current weather panel consumes the same API scenario and consistent seven-day window',()=>{
 const d=get('current-live-example.json'),ui=dom(),ctx={...core,...ui,authSession:{isBlocked:()=>false},liveWeather:d,liveWeatherError:'',mode:'upload',uploaded:fixture(),fmt:n=>n==null?'Unavailable':n.toFixed(1),weatherScheduleMarkup:()=>'',loadLiveWeather:()=>{},setView:()=>{}};
 vm.createContext(ctx);vm.runInContext(app.slice(app.indexOf('function currentUsageReason'),app.indexOf('function weatherFor')),ctx);ctx.renderLiveWeather();
 const html=ui.$('#content').innerHTML;assert.ok(html.includes('Current-date synthetic estimates'));assert.ok(html.includes('Current 7-day scenario'));assert.ok(html.includes('2-day reporting lag'));assert.ok(!html.includes('final review day'));assert.equal(d.horizon_start,'2026-10-29');assert.equal(d.horizon_end,'2026-11-04');
 d.current_scenario.available_customers=0;for(const row of d.business.customers){row.estimated_daily_import_kwh=null;row.expected_increase_percent=null;row.S1_daily_import_kwh=null;row.scenario_reason='recalculating_current_scenario';}
 ctx.renderLiveWeather();assert.ok(ui.$('#content').innerHTML.includes('recalculating current scenario'));assert.ok(ui.$('#content').innerHTML.includes('Unavailable'));
});
test('stable zero and missing estimates keep distinct plain-English meanings',()=>{
 const d=fixture(),p=d.customers[0].predictions[0];d.customers=d.customers.slice(0,1);p.increase=0;p.predicted=p.baseline;
 assert.ok(core.explanation(core.summary(d.customers[0],d)).includes('stay at the recent baseline'));
 p.increase=null;p.predicted=null;p.reason='incomplete_reported_week';assert.ok(core.explanation(core.summary(d.customers[0],d)).includes('incomplete reported week'));assert.equal(core.query(d,{increase:'unavailable'}).length,1);
});
