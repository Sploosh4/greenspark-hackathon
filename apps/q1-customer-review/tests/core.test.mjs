import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {summary,query,explanation,exportRows,days,pct,csvCell} from '../core.mjs';
const d=JSON.parse(readFileSync(new URL('../assets/review-fixture.json',import.meta.url)));
test('default: one customer each, both account types, highest event first',()=>{
  const rows=query(d);assert.deepEqual(rows.map(x=>x.customer.customer_id),['C105002','C103794','C105013','C102031']);
  assert.equal(new Set(rows.map(x=>x.customer.customer_id)).size,rows.length);
  assert.equal(rows[0].estimates.length,2);assert.equal(rows[1].row.records.filter(x=>x.id==='NEED-CO0008281').length,1);
});
test('comparison means any relevant past episode, including exact equality',()=>{
  const rows=query(d);assert.equal(rows[1].highest,42);assert.equal(rows[1].threshold,25);
  assert.ok(rows.some(x=>x.customer.customer_id==='C105013'));
});
test('unlinked assistance never establishes a heat comparison',()=>{
  const x=summary(d.customers.find(x=>x.customer.customer_id==='C102502'),d);
  assert.equal(x.episodes.length,0);assert.equal(x.threshold,null);
  assert.ok(!query(d).some(x=>x.customer.customer_id==='C102502'));
});
test('missing estimates remain null, valid zero remains zero',()=>{
  const rows=query(d,{history:'all',increase:'all'});
  const missing=rows.find(x=>x.customer.customer_id==='C105017');assert.equal(missing.highest,null);
  assert.equal(missing.estimates[0].predicted,null);assert.equal(pct(null),'Unavailable');
  const stable=rows.find(x=>x.customer.customer_id==='C101456');assert.equal(stable.highest,0);assert.equal(pct(0),'0%');
  assert.ok(explanation(missing).includes('No electricity-use estimate is available for either upcoming event'));
});
test('sort asc and desc keep fully unavailable customers last, including ties',()=>{
  const f={history:'all',increase:'all',sort:'increase'};
  assert.equal(query(d,{...f,direction:'asc'}).at(-1).customer.customer_id,'C105017');
  assert.equal(query(d,{...f,direction:'desc'}).at(-1).customer.customer_id,'C105017');
  const copy=structuredClone(d);copy.customers[1].expected_percent_fixture=[48,32];
  assert.equal(query(copy)[0].customer.customer_id,'C103794');
});
test('second event can drive ranking instead of the first event',()=>{
  const copy=structuredClone(d);copy.customers[3].expected_percent_fixture=[18,70];
  assert.equal(query(copy)[0].customer.customer_id,'C102031');
});
test('account type, case-insensitive search and empty intersection',()=>{
  assert.equal(query(d,{type:'Prepaid'}).length,2);assert.equal(query(d,{type:'Billed'}).length,2);
  assert.equal(query(d,{search:'c103794'}).length,1);assert.equal(query(d,{search:'does not exist'}).length,0);
});
test('unavailable filter includes partially unavailable customer',()=>{
  assert.deepEqual(query(d,{history:'all',increase:'unavailable'}).map(x=>x.customer.customer_id),['C105072','C105017']);
});
test('event average and duration remain internally consistent',()=>{
  const x=summary(d.customers[0],d);assert.equal(x.estimates[0].duration,3);
  assert.equal(days(d.horizon_start,d.horizon_end),7);
  assert.ok(Math.abs((x.estimates[0].predicted/x.baseline-1)*100-48)<1e-9);
});
test('CSV is per customer-event, fixture labelled, missing fields empty',()=>{
  const csv=exportRows(query(d));assert.equal(csv.split('\r\n').length,9);assert.ok(csv.includes('FIXTURE'));
  const missing=exportRows(query(d,{search:'C105017',history:'all',increase:'all'}));
  assert.ok(missing.split('\r\n')[1].includes('"3","","'));assert.ok(csvCell('=BAD()').startsWith('"\''));
});
test('closed accounts and out-of-window/unlinked episodes cannot qualify',()=>{
  const copy=structuredClone(d);copy.customers[0].customer.account_close_date=d.review_date;
  copy.customers[1].episodes.forEach(e=>e.start='2022-01-01');
  assert.deepEqual(query(copy).map(x=>x.customer.customer_id),['C105013','C102031']);
});
test('business observations stop before review; future weather is explicitly hindsight',()=>{
  for(const row of d.customers){assert.ok(row.usage.every(r=>r.date<=d.history_cutoff));assert.ok(row.records.every(r=>r.date<=d.review_date));}
  assert.ok(d.provenance.weather.includes('Hindsight'));assert.ok(d.provenance.estimates.includes('No predictive model'));
});
test('plain-English explanation preserves the strongest dated event and missing/zero distinctions',()=>{
  const copy=structuredClone(d);copy.customers[3].expected_percent_fixture=[18,70];
  const text=explanation(summary(copy.customers[3],copy));
  assert.ok(text.includes('70% more electricity from the grid per day on average during 7–9 Jan'));
  assert.ok(text.includes('15% rise'));
  assert.ok(explanation(summary(d.customers[2],d)).includes('the same as the 28% rise'));
  assert.ok(explanation(summary(d.customers[6],d)).includes('stays at the usual level'));
  assert.ok(explanation(summary(d.customers[5],d)).includes('The other event has no estimate'));
});
test('calculated provider values are displayed without the hand-authored fixture percentage',()=>{
  const copy=structuredClone(d);copy.kind='calculated_historical_replay';copy.events=[{id:'EHF-2024-11-03',start:'2024-11-03',end:'2024-11-05',label:'Heat period 1'}];
  copy.review_date='2024-11-02';copy.history_cutoff='2024-11-01';
  copy.customers[1].predictions=[{event_id:'EHF-2024-11-03',baseline:30.755428571428574,predicted:30.79099107142857,increase:0.11562999331127255,duration:3,method_id:'recent7-plus-past-heat-offset/v1'}];
  copy.customers[1].episodes=[{id:'P',start:'2024-10-22',end:'2024-10-25',linked:true,increase_percent:-7.083573387696418,label:'Financial difficulty'}];
  const x=summary(copy.customers[1],copy);
  assert.equal(x.highest,0.11562999331127255);assert.equal(x.estimates[0].predicted,30.79099107142857);
  assert.ok(explanation(x).includes('0.1% more'));assert.ok(explanation(x).includes('7.1% lower'));
  const csv=exportRows([x]);assert.ok(csv.includes('method_id'));assert.ok(!csv.includes('FIXTURE'));
});
test('missing observed comparison never becomes a zero threshold',()=>{
  const copy=structuredClone(d);copy.customers[0].episodes[0].increase_percent=null;
  const x=summary(copy.customers[0],copy);assert.equal(x.threshold,null);
  assert.ok(!query(copy).some(x=>x.customer.customer_id==='C105002'));
});
test('calculated multiple events share one row and an unavailable event stays blank',()=>{
  const copy=structuredClone(d);copy.customers=copy.customers.slice(0,1);
  copy.customers[0].predictions=[{event_id:'A',baseline:10,predicted:null,increase:null,duration:3,reason:'partial_event_boundary'},{event_id:'B',baseline:10,predicted:12,increase:20,duration:3}];
  const rows=query(copy,{history:'all',increase:'all'});
  assert.equal(rows.length,1);assert.equal(rows[0].estimates.length,2);assert.equal(rows[0].highest,20);assert.equal(rows[0].estimates[0].predicted,null);
  copy.customers[0].predictions[1]={event_id:'B',baseline:10,predicted:10,increase:0,duration:3};
  assert.equal(summary(copy.customers[0],copy).highest,0);
  copy.customers[0].predictions[1].predicted=null;copy.customers[0].predictions[1].increase=null;
  assert.equal(summary(copy.customers[0],copy).highest,null);
  copy.events=copy.events.slice(0,1);
  assert.ok(explanation(summary(copy.customers[0],copy)).includes('for this heat period'));
});
