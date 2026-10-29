import {test} from 'node:test';import assert from 'node:assert/strict';
import {pageRows,prepareQuery,query} from '../core.mjs';import {readFileSync} from 'node:fs';
test('50k matches retain every row while each rendered page stays bounded',()=>{
 const rows=Array.from({length:50000},(_,i)=>i),first=pageRows(rows),last=pageRows(rows,9999);
 assert.equal(first.rows.length,100);assert.equal(first.first,1);assert.equal(first.total,50000);assert.equal(first.pages,500);
 assert.equal(last.page,499);assert.equal(last.last,50000);assert.equal(last.rows[99],49999);
 assert.deepEqual(pageRows([],2).rows,[]);assert.throws(()=>pageRows(rows,0,101));
});
test('prepared immutable summaries preserve query results for all core filter modes',()=>{
 const review=JSON.parse(readFileSync(new URL('../assets/review-fixture.json',import.meta.url))),prepared=prepareQuery(review);
 for(const filters of [{},{history:'all',increase:'all'},{type:'Billed'},{increase:'unavailable'},{sort:'customer',direction:'asc'}])assert.deepEqual(query(review,filters,prepared),query(review,filters));
});
