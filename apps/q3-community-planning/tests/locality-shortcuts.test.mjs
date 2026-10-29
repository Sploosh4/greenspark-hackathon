// Execute the real view's selection/controller wiring without a browser or map.
// Camera and rendering are stubbed; source geometry and account joins are real.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {GEOGRAPHY} from '../web/modules/geography-reference.mjs';
import {nearestNativeCell,mappedArea,selectedSeries} from '../web/modules/planning-calculations.mjs';

const read=name=>JSON.parse(fs.readFileSync(new URL(name,import.meta.url),'utf8'));
const mean=read('../data/inputs/seasonal-data.json');
const fixture=read('./fixtures/shortcut-account-context.json');
const business={areas:fixture.areas.map(area=>({...GEOGRAPHY.areas.find(ref=>ref.postcode===area.postcode),...area}))};
const source=fs.readFileSync(new URL('../web/view.mjs',import.meta.url),'utf8');
const start=source.indexOf('function selectArea(code){'),end=source.indexOf("\n$('#area').onchange",start);
assert.ok(start>=0&&end>start,'Named-area controller must remain available to the view');
const controller=source.slice(start,end);
const wiring=source.split('\n').filter(line=>/^\$\('#(?:area|fitzroy|perth)'\)\.(?:onchange|onclick)=/.test(line)).join('\n');
assert.equal(wiring.split('\n').length,3,'Exercise both locality shortcuts and the actual area selector');

function view(){
 const nodes=new Map(['#area','#fitzroy','#perth'].map(id=>[id,{}]));
 const context={GEOGRAPHY,data:mean,PERF:false,selectionSequence:0,selectedAreaCode:'',overview:true,performance:{now:()=>0},$:id=>nodes.get(id),map:{easeTo(options){context.camera=options;}},nearestCell:(...point)=>nearestNativeCell(mean,...point),fitWA(){context.overview=true;context.selectedAreaCode='';}};
 context.updateCell=(feature,title)=>{context.selected=feature;context.title=title;context.accountArea=mappedArea(business,feature,context.selectedAreaCode,true);};
 vm.runInNewContext(controller+'\n'+wiring,context);
 return {context,shortcut:id=>nodes.get('#'+id).onclick(),choose:postcode=>nodes.get('#area').onchange({target:{value:postcode}})};
}

test('Perth shortcut resolves Perth6000 and1720 accounts instead of Two Rocks31',()=>{
 const {context,shortcut}=view();shortcut('perth');
 assert.equal(context.selectedAreaCode,'6000');assert.equal(context.accountArea.postcode,'6000');
 assert.equal(context.accountArea.name,'Perth');assert.equal(context.accountArea.accountCount,1720);
 assert.equal(context.selectedHistoryName,'Perth');
 assert.deepEqual(context.selectedHistoryCoordinate,GEOGRAPHY.areas.find(a=>a.postcode==='6000').referencePoint);
});
test('Perth shortcut and explicit named selection have identical native weather and account context',()=>{
 const button=view(),selector=view();button.shortcut('perth');selector.choose('6000');
 assert.equal(button.context.accountArea.postcode,selector.context.accountArea.postcode);
 assert.deepEqual(button.context.selected.properties,selector.context.selected.properties);
 assert.deepEqual(selectedSeries(mean,button.context.selected),selectedSeries(mean,selector.context.selected));
 assert.deepEqual(button.context.camera.center,selector.context.camera.center);
});
test('Two Rocks remains31 accounts even while sharing the same coarse weather cell as Perth',()=>{
 const perth=view(),rocks=view();perth.shortcut('perth');rocks.choose('6037');
 assert.equal(rocks.context.accountArea.accountCount,31);assert.equal(rocks.context.accountArea.postcode,'6037');
 assert.deepEqual(rocks.context.selected.properties,perth.context.selected.properties);
 assert.deepEqual(selectedSeries(mean,rocks.context.selected),selectedSeries(mean,perth.context.selected));
 assert.notEqual(rocks.context.accountArea.postcode,perth.context.accountArea.postcode);
});
test('Fitzroy shortcut preserves its named reference and unavailable business coverage',()=>{
 const {context,shortcut}=view();shortcut('fitzroy');assert.equal(context.selectedAreaCode,'6765');
 assert.equal(context.selectedHistoryName,'Fitzroy Crossing');assert.equal(context.accountArea,undefined);
 assert.deepEqual(context.selected.properties,{lon:125.5,lat:-18.5});
 assert.equal(selectedSeries(mean,context.selected)[1],33.839);
});
test('another Perth postcode remains distinct through the shared selector',()=>{
 const {context,choose}=view();choose('6001');assert.equal(context.selectedAreaCode,'6001');
 assert.equal(context.accountArea.accountCount,1722);assert.equal(context.accountArea.postcode,'6001');
});
test('generic cell context still uses its documented nearest reference; shortcuts do not change that policy',()=>{
 const selection=nearestNativeCell(mean,115.861,-31.952);
 assert.equal(mappedArea(business,selection,'',true).postcode,'6037');
 assert.equal(mappedArea(business,selection,'6000',true).accountCount,1720);
 assert.equal(mappedArea(business,selection,'6765',true),undefined);
});
