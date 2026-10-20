import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {customerKey,groupCustomerFlags,filterCustomerGroups,migratePreparedKeys,outreachCandidates,customerExportRows} from './dist/customer-review.mjs';
import {evaluateBillPressure} from './dist/bill-pressure.mjs';
import {evaluateUsageChange} from './dist/usage-changes.mjs';
import {evaluateHeatwaveCredit} from './dist/heatwave-credit.mjs';
import {evaluateSolarPerformance} from './dist/solar-performance.mjs';
import {evaluateOutageReadiness} from './dist/outage-readiness.mjs';
const first={id:'GS-1',customer:'C-100',retailer:'Horizon Power',region:'Kimberley',locality:'Broome',extension:'heat',priority:'High',dueDay:1,eligible:true,consent:'yes',channel:'SMS',lifeSupport:false,detail:'$25 short'};
const second={...first,id:'GS-2',extension:'usage',priority:'Urgent',dueDay:3,detail:'-72% imports'};
test('one customer entry retains every distinct flag and uses the highest priority',()=>{
  const [r]=groupCustomerFlags([first,second,first]);assert.equal(r.id,customerKey(first));assert.equal(r.flags.length,2);assert.equal(r.priority,'Urgent');assert.equal(r.dueDay,1);assert.equal(r.flags[0].id,'GS-2');
});
test('customer IDs from different retailers remain separate',()=>{
  assert.equal(groupCustomerFlags([first,{...second,retailer:'Synergy'}]).length,2);
});
test('extension filtering selects customers and preserves all their reasons',()=>{
  const groups=groupCustomerFlags([first,second]);
  for(const extension of ['heat','usage']){const [r]=filterCustomerGroups(groups,{extension});assert.equal(r.flags.length,2);assert.equal(r.priority,'Urgent');}
  assert.equal(filterCustomerGroups(groups,{extension:'solar'}).length,0);
});
test('day and extension must match the same flag and priority uses the customer maximum',()=>{
  const groups=groupCustomerFlags([first,second]);
  assert.equal(filterCustomerGroups(groups,{extension:'heat',day:3}).length,0);
  assert.equal(filterCustomerGroups(groups,{extension:'usage',day:3}).length,1);
  assert.equal(filterCustomerGroups(groups,{extension:'heat',priority:'Urgent'}).length,1);
  assert.equal(filterCustomerGroups(groups,{priority:'High'}).length,0);
  assert.equal(filterCustomerGroups(groups,{search:'gs-2'}).length,1);
});
test('conflicting consent or channel inputs cannot create a contactable customer',()=>{
  for(const change of [{eligible:false},{consent:'no'},{consent:'not_asked'},{channel:'Email'}])assert.equal(groupCustomerFlags([first,{...second,...change}])[0].eligible,false);
});
test('legacy preparation on any case blocks every flag for that customer',()=>{
  const prepared=migratePreparedKeys(new Set(['GS-1']),[first,second]);
  assert.ok(prepared.has(customerKey(first)));assert.equal(outreachCandidates([second],prepared).length,0);
  assert.ok(migratePreparedKeys(prepared,[first,second]).has(customerKey(first)));
});
test('handoff candidates deduplicate raw flags and already-grouped selections',()=>{
  const grouped=groupCustomerFlags([first,second]);
  assert.equal(outreachCandidates([first,second,...grouped],new Set()).length,1);
  const prepared=new Set();for(const r of outreachCandidates(grouped,prepared))prepared.add(r.id);
  assert.equal(outreachCandidates([first],prepared).length,0);assert.equal(outreachCandidates([second],prepared).length,0);
  assert.equal(outreachCandidates(grouped,new Set(JSON.parse(JSON.stringify([...prepared])))).length,0);
});
test('queue and handoff CSV rows contain one customer, all case IDs and all reasons',()=>{
  const options={labelFor:id=>id,messageFor:r=>r.flags.map(f=>f.detail).join('; ')};
  const queue=customerExportRows([first,second,first],options);assert.equal(queue.length,1);assert.ok(queue[0][0].includes('GS-1'));assert.ok(queue[0][0].includes('GS-2'));assert.ok(queue[0][6].includes('$25 short'));assert.ok(queue[0][6].includes('-72% imports'));
  const handoff=customerExportRows([first,second],{...options,handoff:true});assert.equal(handoff.length,1);assert.ok(handoff[0][7].includes('$25 short'));assert.ok(handoff[0][7].includes('-72% imports'));
});
test('scenario has contactable overlaps for each retailer without duplicate queue entries',async()=>{
  const data=JSON.parse(await readFile(new URL('./dist/data.json',import.meta.url),'utf8'));
  const evaluators={bill:evaluateBillPressure,usage:evaluateUsageChange,heat:evaluateHeatwaveCredit,solar:evaluateSolarPerformance,outage:evaluateOutageReadiness};
  const qualified=data.cases.flatMap(r=>{const a=evaluators[r.extension](r);return a.flagged?[{...r,priority:a.priority}]:[]});
  const groups=groupCustomerFlags(qualified);assert.ok(groups.length<qualified.length);
  assert.equal(new Set(groups.map(r=>r.id)).size,groups.length);
  for(const retailer of ['Horizon Power','Synergy'])assert.ok(groups.some(r=>r.retailer===retailer&&r.flags.length>1&&r.eligible));
  for(const r of groups)assert.equal(new Set(r.flags.map(f=>f.customer)).size,1);
});
