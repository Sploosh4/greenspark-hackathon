// node --test map-demo/test-ml-outlook-layer.mjs   (run from q3-seasonal-ml after export_map_layer.py)
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cellsToGeoJSON, cellSummary, MODES, LOW_SKILL } from './ml-outlook-layer.mjs';

const data = JSON.parse(readFileSync(new URL('../outputs/ml_outlook_layer.json', import.meta.url)));

test('every cell becomes a closed 1-degree square centred on its lat/lon', () => {
  for (const issue of data.issues) {
    const gj = cellsToGeoJSON(data, issue.key);
    assert.equal(gj.features.length, 255);
    for (const f of gj.features) {
      const ring = f.geometry.coordinates[0];
      assert.deepEqual(ring[0], ring[4]);
      assert.equal(ring[1][0] - ring[0][0], 1);
      assert.equal(ring[2][1] - ring[1][1], 1);
      assert.equal((ring[0][0] + ring[1][0]) / 2, f.properties.lon);
    }
  }
});

test('feature properties match the exported forecast for each lead', () => {
  const issue = data.issues.at(-1).key;
  const f = cellsToGeoJSON(data, issue).features.find(x => x.properties.id === '-18.5_125.5').properties;
  const c = data.cells.find(x => x.id === '-18.5_125.5');
  for (let i = 0; i < 6; i++) {
    assert.equal(f[`t${i}`], c.f[issue].t[i]);
    assert.equal(f[`p${i}`], c.f[issue].p[i]);
    assert.equal(f[`s${i}`], c.skill[i]);
  }
});

test('summary carries locality name, months, range and low-skill flag', () => {
  const s = cellSummary(data, '2026-10', '-18.5_125.5');
  assert.equal(s.locality, 'Fitzroy Crossing');
  assert.deepEqual(s.months.map(m => m.month), data.issues.find(i => i.key === '2026-10').months);
  for (const m of s.months) {
    assert.ok(m.lo < m.temp && m.temp < m.hi);
    assert.equal(m.lowSkill, m.skill < LOW_SKILL);
    assert.ok(Math.abs(m.temp - m.normal - m.anom) <= 0.11);  // 0.1 °C + 0.1 °C + 0.01 °C rounding
  }
  assert.equal(cellSummary(data, '2026-10', 'nope'), null);
});

test('colour scales are fixed and the temperature scale matches the app legend (14-36 °C)', () => {
  assert.deepEqual(MODES.temp.domain, [14, 36]);
  for (const m of Object.values(MODES)) {
    assert.equal(m.stops[0][0], m.domain[0]);
    assert.equal(m.stops.at(-1)[0], m.domain[1]);
  }
});
