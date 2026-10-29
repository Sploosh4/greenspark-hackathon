import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {validateHistoryMetadata,historicalKey} from '../web/modules/native-history.mjs';
const metadata=JSON.parse(fs.readFileSync(new URL('../data/history/metadata.json',import.meta.url)));
test('native history metadata preserves period, units and actual coverage',()=>{assert.equal(validateHistoryMetadata(metadata).grid.dx,.05);assert.equal(metadata.coverage.missingCoastalIslandCells,18);assert.equal(metadata.quality.sourceTminAboveTmaxCellDays,2623);assert.equal(metadata.statistic,'Monthly mean of daily Tmax/Tmin midpoint');});
test('matching average follows calendar month across forecast year boundary',()=>{assert.equal(historicalKey('average','2026-10'),'average-10');assert.equal(historicalKey('average','2027-01'),'average-01');assert.equal(historicalKey('2025-11','2027-01'),'2025-11');});
test('wrong period, units, resolution and coverage are rejected',()=>{for(const change of [m=>m.units='K',m=>m.period[1]='2026-10-31',m=>m.grid.dx=.025,m=>m.coverage.populatedNativeCells=91198]){const m=structuredClone(metadata);change(m);assert.throws(()=>validateHistoryMetadata(m));}});

test('SILO observational normal follows calendar month and keeps model baseline separate',()=>{assert.equal(historicalKey('normal','2027-01'),'normal-01');assert.equal(metadata.normal.sourceObjects,21916);assert.equal(metadata.normal.sourceInversionCellDays,585);assert.equal(metadata.normal.period.join('/'),'1991-01-01/2020-12-31');});
