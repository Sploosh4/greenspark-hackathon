import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {poa2021Code,validAreaGeometry,findPoa2021Boundary,joinPoa2021Contexts} from './teamconnect/area-boundaries.mjs';
const d=JSON.parse(await readFile(new URL('./teamconnect/scenario.json',import.meta.url)));
const context=d.context.find(r=>r.postcode==='6722');
// Tiny triangles are test fixtures only. No test geometry is shipped as map data.
const ring=[[118,-20],[119,-20],[118,-21],[118,-20]];
const feature=()=>({type:'Feature',properties:{poa_code_2021:'6722',poa_name_2021:'6722'},geometry:{type:'Polygon',coordinates:[structuredClone(ring)]}});
const collection=(features=[feature()])=>({type:'FeatureCollection',geography:'POA2021',reference_year:2021,features});

test('all twelve retained statistics use explicit matching 2021 POA/postcode keys',()=>{
 assert.equal(d.context.length,12);
 assert.equal(new Set(d.context.map(poa2021Code)).size,12);
 assert.ok(d.context.every(row=>poa2021Code(row)===row.postcode));
});
test('join key requires exact geography, year, prefix and consistent string postcode',()=>{
 assert.equal(poa2021Code(context),'6722');
 for(const patch of [{context_geography:'SAL2021'},{census_reference_year:'2026'},{POA_CODE_2021:'6722'},{POA_CODE_2021:'POA06722'},{postcode:'6721'},{postcode:6722}])assert.equal(poa2021Code({...context,...patch}),null);
 assert.equal(poa2021Code({...context,postcode:'0872',POA_CODE_2021:'POA0872'}),'0872');
 for(const code of ['9494','9797','ZZZZ'])assert.equal(poa2021Code({...context,postcode:code,POA_CODE_2021:'POA'+code}),null);
});
test('no boundary is substituted for missing, wrong-year, wrong-grain or unmatched geometry',()=>{
 assert.equal(findPoa2021Boundary(context,null),null);
 assert.equal(findPoa2021Boundary(context,collection([])),null);
 assert.equal(findPoa2021Boundary(context,{...collection(),reference_year:2026}),null);
 assert.equal(findPoa2021Boundary(context,{...collection(),geography:'SA12021'}),null);
 const wrong=feature();wrong.properties.poa_code_2021='6721';assert.equal(findPoa2021Boundary(context,collection([wrong])),null);
});
test('ambiguous duplicate source codes and duplicate statistics fail closed',()=>{
 assert.equal(findPoa2021Boundary(context,collection([feature(),feature()])),null);
 assert.deepEqual(joinPoa2021Contexts([context,context],collection()),[]);
});
test('whole Polygon/MultiPolygon boundaries retain islands and holes exactly',()=>{
 const f=feature(),hole=ring.map(([x,y])=>[x*.001+118.1,y*.001-20.1]);f.geometry.coordinates.push(hole);
 const found=findPoa2021Boundary(context,collection([f]));assert.equal(found,f);assert.deepEqual(found.geometry.coordinates[1],hole);
 const multi=feature();multi.geometry={type:'MultiPolygon',coordinates:[[ring],[ring.map(([x,y])=>[x+2,y])]]};
 assert.equal(findPoa2021Boundary(context,collection([multi])),multi);
});
test('points, unclosed/degenerate rings, nonfinite and projected coordinates are rejected',()=>{
 const cases=[null,{type:'Point',coordinates:[118,-20]},{type:'Polygon',coordinates:[]},{type:'Polygon',coordinates:[ring.slice(0,3)]},{type:'Polygon',coordinates:[[[118,-20],[119,-20],[120,-20],[118,-20]]]},{type:'Polygon',coordinates:[[[118,-20],[NaN,-20],[118,-21],[118,-20]]]},{type:'Polygon',coordinates:[[[118000,-20],[119000,-20],[118000,-21],[118000,-20]]]}];
 for(const geometry of cases){assert.equal(validAreaGeometry(geometry),false);assert.equal(findPoa2021Boundary(context,collection([{...feature(),geometry}])),null);}
});
test('partial joins include only matched POA rows and do not invent finer-area statistics',()=>{
 const result=joinPoa2021Contexts(d.context,collection());assert.equal(result.length,1);assert.equal(result[0].context,context);
 assert.equal(result[0].boundary.properties.population,undefined);
 assert.deepEqual(Object.keys(result[0]),['context','boundary']);
});
test('join leaves source statistics and geometry unchanged',()=>{
 const c=collection(),before=JSON.stringify({contexts:d.context,collection:c});
 joinPoa2021Contexts(d.context,c);assert.equal(JSON.stringify({contexts:d.context,collection:c}),before);
});
