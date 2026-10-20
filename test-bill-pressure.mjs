import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {evaluateBillPressure} from './dist/bill-pressure.mjs';

const base={prepay:false,uplift:65,missedPayments90d:0,failedDirectDebits90d:0,arrearsPrevious:100,arrearsCurrent:100};
test('a large increase alone never creates bill pressure',()=>{
  for(const uplift of [25,40,55,65,200])assert.equal(evaluateBillPressure({...base,uplift}).flagged,false);
});
test('each of the three payment signals can qualify a billed customer',()=>{
  for(const signal of [{missedPayments90d:1},{failedDirectDebits90d:1},{arrearsCurrent:101}]){
    const r=evaluateBillPressure({...base,...signal});assert.equal(r.flagged,true);assert.equal(r.factors.length,1);assert.equal(r.priority,'High');
  }
});
test('flat, falling, missing and invalid arrears do not count as rising',()=>{
  for(const values of [{arrearsCurrent:50},{arrearsCurrent:100},{arrearsPrevious:null,arrearsCurrent:200},{arrearsPrevious:-20,arrearsCurrent:20},{arrearsCurrent:NaN}])assert.equal(evaluateBillPressure({...base,...values}).flagged,false);
});
test('the increase threshold and account type still apply when payment stress exists',()=>{
  assert.equal(evaluateBillPressure({...base,uplift:24.99,missedPayments90d:3}).flagged,false);
  assert.equal(evaluateBillPressure({...base,prepay:true,missedPayments90d:3}).flagged,false);
  assert.equal(evaluateBillPressure({...base,uplift:null,missedPayments90d:3}).flagged,false);
});
test('priority responds to both increase and number of distinct payment signals',()=>{
  assert.equal(evaluateBillPressure({...base,uplift:25,missedPayments90d:1}).priority,'Review');
  assert.equal(evaluateBillPressure({...base,uplift:25,missedPayments90d:5}).priority,'Review');
  assert.equal(evaluateBillPressure({...base,uplift:25,missedPayments90d:1,failedDirectDebits90d:1}).priority,'High');
  assert.equal(evaluateBillPressure({...base,uplift:40,missedPayments90d:1,failedDirectDebits90d:1}).priority,'Urgent');
});
test('scenario includes increase-only exclusions and all signal types for both retailers',async()=>{
  const data=JSON.parse(await readFile(new URL('./dist/data.json',import.meta.url),'utf8'));
  for(const retailer of ['Horizon Power','Synergy']){
    const candidates=data.cases.filter(r=>r.extension==='bill'&&r.retailer===retailer);
    const evaluated=candidates.map(evaluateBillPressure);
    assert.ok(evaluated.some(r=>!r.flagged));
    for(const kind of ['missed','failed-dd','arrears'])assert.ok(evaluated.some(r=>r.flagged&&r.factors.some(f=>f.id===kind)));
    assert.ok(evaluated.filter(r=>r.flagged).every(r=>r.factors.length>0));
  }
});
