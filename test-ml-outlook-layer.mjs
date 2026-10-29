import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {cellsToGeoJSON,cellSummary,MODES,LOW_SKILL} from './teamconnect/ml-outlook-layer.mjs';
import {mlCellId} from './teamconnect/ml-outlook-panel.mjs';
const read=path=>readFile(new URL(path,import.meta.url));
const layer=JSON.parse(await read('./teamconnect/ml-outlook/ml_outlook_layer.json'));
const provenance=JSON.parse(await read('./teamconnect/ml-outlook/provenance.json'));
const d=JSON.parse(await read('./teamconnect/scenario.json'));

test('every scenario community falls inside a forecast cell',()=>{
  const communities=new Map(d.customers.map(c=>[c.locality,c]));
  assert.equal(communities.size,12);
  for(const [name,c] of communities){
    const id=mlCellId(Number(c.latitude),Number(c.longitude));
    assert.ok(layer.cells.some(cell=>cell.id===id),`${name} → ${id}`);
  }
  assert.equal(mlCellId(-18.1966928,125.5819725),'-18.5_125.5');
});

test('cells are 1-degree squares and carry the exported values for each lead',()=>{
  for(const issue of layer.issues){
    const gj=cellsToGeoJSON(layer,issue.key);
    assert.equal(gj.features.length,layer.cells.length);
    for(const [i,f] of gj.features.entries()){
      const ring=f.geometry.coordinates[0],cell=layer.cells[i];
      assert.deepEqual(ring[0],ring[4]);assert.equal(ring[1][0]-ring[0][0],1);assert.equal(ring[2][1]-ring[1][1],1);
      for(let k=0;k<6;k++){assert.equal(f.properties[`a${k}`],cell.f[issue.key].a[k]);assert.equal(f.properties[`s${k}`],cell.skill[k]);}
    }
  }
});

test('summaries keep forecast, range, normal and low-skill flags consistent',()=>{
  for(const issue of layer.issues)for(const cell of layer.cells){
    const s=cellSummary(layer,issue.key,cell.id);
    assert.deepEqual(s.months.map(m=>m.month),issue.months);
    for(const m of s.months){
      assert.ok(m.lo<m.temp&&m.temp<m.hi);assert.ok(m.prob>=0&&m.prob<=1);
      // temp and normal are stored to 0.1 °C, anomaly to 0.01 °C: worst-case rounding gap 0.105
      assert.ok(Math.abs(m.temp-m.normal-m.anom)<=0.11);assert.equal(m.lowSkill,m.skill<LOW_SKILL);
    }
  }
  assert.equal(cellSummary(layer,'1999-01','-18.5_125.5'),null);
});

test('fixed colour scales; temperature uses the 14–36 °C outlook scale',()=>{
  assert.deepEqual(MODES.temp.domain,[14,36]);
  for(const m of Object.values(MODES)){assert.equal(m.stops[0][0],m.domain[0]);assert.equal(m.stops.at(-1)[0],m.domain[1]);}
});

test('provenance hashes match the shipped outlook files and the product is labelled experimental',async()=>{
  for(const [name,hash] of Object.entries(provenance.files))
    assert.equal(createHash('sha256').update(await read('./teamconnect/ml-outlook/'+name)).digest('hex'),hash,name);
  assert.match(provenance.status,/Not a Copernicus/);
  assert.match(provenance.relationship_to_demo_scenario,/Independent of the synthetic 2025/);
});
