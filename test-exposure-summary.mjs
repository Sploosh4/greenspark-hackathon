import assert from 'node:assert/strict';
import {test} from 'node:test';
import {exposureSummary,regionalExposure,uniqueExtensionRows} from './dist/exposure-summary.mjs';
const account=(customer,region='North',extra={})=>({customer,retailer:'Horizon Power',region,prepay:false,hasSolar:false,...extra});
const flag=(customer,extension='usage',extra={})=>({...account(customer),id:`${customer}-${extension}`,extension,priority:'High',dueDay:1,...extra});
test('regional counts and priorities count each customer once while signal counts can overlap',()=>{
  const rows=[flag('A','heat',{priority:'Review'}),flag('A','usage',{priority:'Urgent'}),flag('B')];
  const summary=exposureSummary(rows,[account('A'),account('B'),account('C'),account('D')]);
  assert.equal(summary.count,2);assert.equal(summary.total,4);assert.equal(summary.percentage,50);
  assert.deepEqual(summary.priorities,{Urgent:1,High:1,Review:0});assert.deepEqual(summary.signals,[{id:'usage',count:2},{id:'heat',count:1}]);
});
test('denominators include unflagged accounts and duplicate population rows count once',()=>{
  const summary=exposureSummary([flag('A')],[account('A'),account('A'),account('B'),account('C')]);
  assert.equal(summary.count,1);assert.equal(summary.total,3);assert.ok(Math.abs(summary.percentage-100/3)<1e-10);
});
test('heat, bill and solar percentages use their actual applicable cohorts',()=>{
  const population=[account('P1','North',{prepay:true}),account('P2','North',{prepay:true}),account('B'),account('S','North',{hasSolar:true})];
  assert.equal(exposureSummary([flag('P1','heat')],population,{extension:'heat'}).percentage,50);
  assert.equal(exposureSummary([flag('B','bill')],population,{extension:'bill'}).percentage,50);
  assert.equal(exposureSummary([flag('S','solar')],population,{extension:'solar'}).percentage,100);
  assert.equal(exposureSummary([flag('B','outage')],population,{extension:'outage'}).percentage,25);
});
test('regions rank by affected-account percentage and include regions with no flags',()=>{
  const population=[...Array.from({length:100},(_,i)=>account(`L${i}`,'Large')),...Array.from({length:10},(_,i)=>account(`S${i}`,'Small')),account('Z','Zero')];
  const rows=[...Array.from({length:5},(_,i)=>flag(`L${i}`,'usage',{region:'Large'})),flag('S0','usage',{region:'Small'})];
  const result=regionalExposure(rows,population);assert.deepEqual(result.map(r=>r.region),['Small','Large','Zero']);assert.deepEqual(result.map(r=>r.percentage),[10,5,0]);
});
test('retailer, region and time filters keep numerator and full population scopes aligned',()=>{
  const population=[account('A'),account('B'),account('C','South'),account('A','North',{retailer:'Synergy'})];
  const rows=[flag('A'),flag('B','usage',{dueDay:5}),flag('C','usage',{region:'South'}),flag('A','usage',{retailer:'Synergy'})];
  const summary=exposureSummary(rows,population,{retailer:'Horizon Power',region:'North',days:3});assert.equal(summary.count,1);assert.equal(summary.total,2);assert.equal(summary.percentage,50);
  const all=exposureSummary(rows,population);assert.equal(all.count,4);assert.equal(all.total,4);assert.equal(all.percentage,100);
});
test('overall percentages are recomputed from totals rather than averaged regional percentages',()=>{
  const population=[...Array.from({length:100},(_,i)=>account(`L${i}`,'Large')),account('S','Small')];
  const rows=[flag('L0','usage',{region:'Large'}),flag('S','usage',{region:'Small'})];
  assert.equal(exposureSummary(rows,population).percentage,2/101*100);
});
test('known zero exposure differs from missing or unmatched denominators',()=>{
  assert.equal(exposureSummary([],[account('A')]).percentage,0);
  assert.equal(exposureSummary([],[]).percentage,null);
  assert.equal(exposureSummary([flag('missing')],[account('A')]).percentage,null);
  assert.equal(exposureSummary([flag('missing')],[account('A')]).unknownCustomers,1);
});
test('extension chart rows use one representative per customer and the highest qualifying priority',()=>{
  const rows=[flag('A','bill',{id:'1',priority:'Review'}),flag('A','bill',{id:'2',priority:'Urgent'}),flag('A','usage'),flag('B','bill')];
  const unique=uniqueExtensionRows(rows,'bill');assert.equal(unique.length,2);assert.equal(unique[0].priority,'Urgent');
});
