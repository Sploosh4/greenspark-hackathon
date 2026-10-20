import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {evaluateHeatwaveCredit} from './dist/heatwave-credit.mjs';
const at=hours=>new Date(Date.parse('2025-01-14T08:30:00+08:00')+hours*3600000).toISOString();
const base={prepay:true,region:'Pilbara',assessmentAt:at(0),balanceAt:at(0),credit:12,dailyCost:12,topUpsComplete:true,topUps:[],heatForecast:{region:'Pilbara',isHeatEvent:true,locationMatched:true,startsAt:at(24),endsAt:at(72),dailyCost:24,peakTemperature:43}};
const topUp=(amount,hours,status='posted')=>({id:'t1',amount,at:at(hours),status});
test('credit projections use normal spending before heat and heat spending during heat',()=>{
  const a=evaluateHeatwaveCredit({...base,credit:24});
  assert.equal(a.flagged,true);assert.equal(a.runOutHours,36);assert.equal(a.shortfall,36);assert.equal(a.beforeHeat,false);assert.equal(a.priority,'High');
  const early=evaluateHeatwaveCredit({...base,credit:6});assert.equal(early.beforeHeat,true);assert.equal(early.runOutHours,12);assert.equal(early.riskInHours,24);assert.equal(early.priority,'High');
});
test('enough credit to last through heat, including exact coverage, is not flagged',()=>{
  for(const credit of [60,61,100])assert.equal(evaluateHeatwaveCredit({...base,credit}).flagged,false);
});
test('recent top-ups after the balance read count once and can remove a flag',()=>{
  const r={...base,credit:12,balanceAt:at(-4),topUps:[topUp(60,-1)]};
  const a=evaluateHeatwaveCredit(r);assert.equal(a.flagged,false);assert.equal(a.availableCredit,70);assert.equal(a.addedAfterRead,60);assert.equal(a.recentTopUpTotal,60);
});
test('top-ups already in the balance are shown but never added twice',()=>{
  for(const hours of [-3,0]){
    const a=evaluateHeatwaveCredit({...base,credit:24,topUps:[topUp(60,hours)]});
    assert.equal(a.flagged,true);assert.equal(a.availableCredit,24);assert.equal(a.addedAfterRead,0);assert.equal(a.shortfall,36);assert.equal(a.recentTopUpTotal,60);
    assert.ok(a.factors.some(f=>f.id==='top-ups'&&f.label.includes('$60.00')));
  }
});
test('pending and future top-ups do not suppress a shortfall',()=>{
  const pending=evaluateHeatwaveCredit({...base,topUps:[topUp(100,-1,'pending')]});
  assert.equal(pending.flagged,true);assert.equal(pending.availableCredit,12);assert.equal(pending.pendingTopUpTotal,100);assert.ok(pending.factors.some(f=>f.id==='pending'));
  const future=evaluateHeatwaveCredit({...base,topUps:[topUp(100,2)]});assert.equal(future.flagged,true);assert.equal(future.recentTopUpTotal,0);
});
test('priority uses the start of the heat credit gap, not low credit alone',()=>{
  for(const [starts,ends,credit,priority] of [[0,24,1,'Urgent'],[24,72,12,'High'],[48,72,1,'Review']]){
    const a=evaluateHeatwaveCredit({...base,credit,heatForecast:{...base.heatForecast,startsAt:at(starts),endsAt:at(ends)}});
    assert.equal(a.priority,priority);
  }
});
test('missing, stale, mismatched, past and non-heat inputs cannot qualify',()=>{
  for(const invalid of [{prepay:false},{balanceAt:at(-25)},{balanceAt:at(1)},{credit:null},{dailyCost:0},{topUpsComplete:null},{topUps:[topUp(-20,-1)]},{topUps:[topUp(20,-1),topUp(20,-1)]}])assert.equal(evaluateHeatwaveCredit({...base,...invalid}).flagged,false);
  for(const invalid of [{locationMatched:null},{region:'Other region'},{isHeatEvent:false},{startsAt:at(-48),endsAt:at(-1)},{startsAt:at(60),endsAt:at(30)},{endsAt:at(169)},{dailyCost:NaN}])assert.equal(evaluateHeatwaveCredit({...base,heatForecast:{...base.heatForecast,...invalid}}).flagged,false);
});
test('ongoing heat uses its remaining duration',()=>{
  const a=evaluateHeatwaveCredit({...base,heatForecast:{...base.heatForecast,startsAt:at(-12),endsAt:at(24)}});
  assert.equal(a.flagged,true);assert.equal(a.hoursToHeat,0);assert.equal(a.costThroughHeat,24);assert.equal(a.runOutHours,12);assert.equal(a.shortfall,12);
});
test('scenario includes resolved top-ups and retained top-up cases with all fields consistent',async()=>{
  const data=JSON.parse(await readFile(new URL('./dist/data.json',import.meta.url),'utf8'));
  const candidates=data.cases.filter(r=>r.extension==='heat').map(r=>({r,a:evaluateHeatwaveCredit(r)}));
  assert.ok(candidates.some(({a})=>a.flagged&&a.recentTopUpTotal>0));
  assert.ok(candidates.some(({a})=>!a.flagged&&a.addedAfterRead>0));
  assert.ok(candidates.some(({a})=>!a.flagged&&a.recentTopUpTotal>0&&a.addedAfterRead===0));
  assert.ok(candidates.some(({a})=>a.flagged&&a.pendingTopUpTotal>0));
  for(const {r,a} of candidates.filter(({a})=>a.flagged)){
    assert.equal(r.retailer,'Horizon Power');assert.ok(a.shortfall>0);assert.ok(a.riskInHours<a.hoursToEnd);assert.ok(a.factors.length>=4);
  }
});
