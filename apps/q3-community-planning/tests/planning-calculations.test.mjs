import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {nearestNativeCell,cellContainsPoint,nativeMeanGrid,mappedArea,historicalPoint,selectedSeries} from '../web/modules/planning-calculations.mjs';
const read=name=>JSON.parse(fs.readFileSync(new URL('../data/inputs/'+name,import.meta.url)));
const mean=read('seasonal-data.json'),history=read('historical-context.json'),business=read('q3-area-context.json');
const fitz=nearestNativeCell(mean,125.55,-18.2);
test('town selects actual containing native centre',()=>assert.deepEqual(fitz.properties,{lon:125.5,lat:-18.5}));
test('cell edge membership is consistent and half-open',()=>{assert.equal(cellContainsPoint(fitz,[125,-19]),true);assert.equal(cellContainsPoint(fitz,[126,-18.5]),false);});
test('no new spatial precision or values in mean layer',()=>{const grid=nativeMeanGrid(mean,1);assert.equal(grid.features.length,414);assert.equal(grid.features[5*18+13].properties.valueC,33.839);});
test('selected monthly series uses unchanged source cells',()=>assert.deepEqual(selectedSeries(mean,fitz),[32.752,33.839,33.655,32.974,32.244,32.273]));
test('actual historical point and snapshot area remain separately joined',()=>{assert.equal(mappedArea(business,fitz,'6765').accountCount,37);assert.equal(historicalPoint(history,fitz,'6765').postcode,'6765');});
test('unmapped cell creates neither accounts nor historical coverage',()=>{const inland=nearestNativeCell(mean,121.5,-23.5);assert.equal(mappedArea(business,inland,''),undefined);assert.equal(historicalPoint(history,inland,''),undefined);});

test('explicit omitted town never borrows a neighbouring business area in the same cell',()=>{const port=business.areas.find(a=>a.postcode==='6721'),selection=nearestNativeCell(mean,118.6,-20.4);assert.equal(mappedArea({areas:[port]},selection,'6722'),undefined);assert.equal(mappedArea({areas:[port]},selection,'6721')?.postcode,'6721');});
