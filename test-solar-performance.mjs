import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {evaluateSolarPerformance} from './dist/solar-performance.mjs';
const base={exportChange:-60,expectedExportChange:-10,importChange:30,sunnyDayShortfalls7d:0,cloudExplainsDrop:false,seasonExplainsDrop:false};
test('cloud and season explanations exclude even strong supporting signals',()=>{
  for(const explanation of [{cloudExplainsDrop:true},{seasonExplainsDrop:true}])assert.equal(evaluateSolarPerformance({...base,...explanation,sunnyDayShortfalls7d:5}).flagged,false);
});
test('unknown context or unusable adjusted baselines cannot qualify',()=>{
  for(const missing of [{cloudExplainsDrop:null},{seasonExplainsDrop:undefined},{expectedExportChange:null},{expectedExportChange:-100},{exportChange:NaN}])assert.equal(evaluateSolarPerformance({...base,...missing}).flagged,false);
});
test('a drop explained by the adjusted baseline or without corroboration is excluded',()=>{
  assert.equal(evaluateSolarPerformance({...base,expectedExportChange:-55}).flagged,false);
  assert.equal(evaluateSolarPerformance({...base,importChange:0}).flagged,false);
});
test('rising imports or repeated comparable sunny-day shortfalls provide corroboration',()=>{
  assert.equal(evaluateSolarPerformance(base).flagged,true);
  const sunny=evaluateSolarPerformance({...base,importChange:0,sunnyDayShortfalls7d:3});
  assert.equal(sunny.flagged,true);assert.deepEqual(sunny.factors.map(f=>f.id),['adjusted-shortfall','sunny-days']);
});
test('drop, residual, supporting-signal and priority thresholds are respected',()=>{
  assert.equal(evaluateSolarPerformance({...base,exportChange:-29.99}).flagged,false);
  assert.equal(evaluateSolarPerformance({...base,exportChange:-30,expectedExportChange:0,importChange:20}).priority,'Review');
  assert.equal(evaluateSolarPerformance({...base,exportChange:-35.99,expectedExportChange:-20}).flagged,false);
  assert.equal(evaluateSolarPerformance({...base,exportChange:-36,expectedExportChange:-20}).flagged,true);
  assert.equal(evaluateSolarPerformance({...base,exportChange:-36.01,expectedExportChange:-20}).flagged,true);
  assert.equal(evaluateSolarPerformance({...base,importChange:19.99}).flagged,false);
  assert.equal(evaluateSolarPerformance({...base,importChange:0,sunnyDayShortfalls7d:2}).flagged,false);
  assert.equal(evaluateSolarPerformance({...base,sunnyDayShortfalls7d:3}).priority,'High');
});
test('scenario retains both retailers and excludes explained and unsupported solar candidates',async()=>{
  const data=JSON.parse(await readFile(new URL('./dist/data.json',import.meta.url),'utf8'));
  const candidates=data.cases.filter(r=>r.extension==='solar');
  for(const explanation of ['cloudExplainsDrop','seasonExplainsDrop']){
    const explained=candidates.filter(r=>r[explanation]);assert.ok(explained.length);assert.ok(explained.every(r=>!evaluateSolarPerformance(r).flagged));
  }
  assert.ok(candidates.some(r=>!r.cloudExplainsDrop&&!r.seasonExplainsDrop&&!evaluateSolarPerformance(r).flagged));
  for(const retailer of ['Horizon Power','Synergy'])assert.ok(candidates.some(r=>r.retailer===retailer&&evaluateSolarPerformance(r).flagged));
});
