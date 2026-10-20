import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {evaluateUsageChange} from './dist/usage-changes.mjs';
const base={prepay:false,change:-75,outageExplainsDrop:false,solarExplainsDrop:false,selfDisconnections7d:0,nearZeroUsageDays7d:0,hotDays7d:0,hotDayUsageChange:null,declineDays:1};
test('an outage or solar explanation overrides supporting signals',()=>{
  for(const explanation of [{outageExplainsDrop:true},{solarExplainsDrop:true},{outageExplainsDrop:true,solarExplainsDrop:true}])assert.equal(evaluateUsageChange({...base,...explanation,declineDays:7,nearZeroUsageDays7d:5}).flagged,false);
});
test('a large but unsupported one-off drop does not flag someone',()=>assert.equal(evaluateUsageChange(base).flagged,false));
test('unknown context is not treated as no explanation',()=>{
  for(const missing of [{outageExplainsDrop:null},{solarExplainsDrop:undefined}])assert.equal(evaluateUsageChange({...base,...missing,declineDays:7}).flagged,false);
});
test('each supporting signal can qualify an unexplained drop',()=>{
  for(const signal of [{declineDays:3},{nearZeroUsageDays7d:2},{hotDays7d:2,hotDayUsageChange:-30},{prepay:true,selfDisconnections7d:1}])assert.equal(evaluateUsageChange({...base,...signal}).flagged,true);
  assert.equal(evaluateUsageChange({...base,selfDisconnections7d:2}).flagged,false);
});
test('drop and priority boundaries are respected',()=>{
  assert.equal(evaluateUsageChange({...base,change:-29.99,declineDays:5}).flagged,false);
  assert.equal(evaluateUsageChange({...base,change:-30,declineDays:3}).priority,'High');
  assert.equal(evaluateUsageChange({...base,change:-65,declineDays:3}).priority,'High');
  assert.equal(evaluateUsageChange({...base,change:-65.01,declineDays:3}).priority,'Urgent');
  assert.equal(evaluateUsageChange({...base,change:75,declineDays:7}).flagged,false);
});
test('scenario filters explained cases and groups every flagged case exactly once',async()=>{
  const data=JSON.parse(await readFile(new URL('./dist/data.json',import.meta.url),'utf8'));
  const candidates=data.cases.filter(r=>r.extension==='usage');
  const results=candidates.map(r=>({r,a:evaluateUsageChange(r)}));
  for(const context of ['Outage overlap','Solar shift']){
    const explained=results.filter(x=>x.r.context===context);assert.ok(explained.length);assert.ok(explained.every(x=>!x.a.flagged));
  }
  assert.ok(results.some(x=>x.r.context==='Unexplained'&&!x.a.flagged));
  const groups=new Set(['Self-disconnection','Near-zero use','Hot-day decline','Sustained decline']);
  for(const {a} of results.filter(x=>x.a.flagged)){assert.ok(a.factors.length);assert.ok(groups.has(a.driver));}
  for(const retailer of ['Synergy','Horizon Power'])assert.ok(results.some(x=>x.r.retailer===retailer&&x.a.flagged));
});
