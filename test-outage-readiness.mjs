import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {evaluateOutageReadiness} from './dist/outage-readiness.mjs';
const at=hours=>new Date(Date.parse('2025-01-14T08:30:00+08:00')+hours*3600000).toISOString();
const base={region:'Pilbara',premisesId:'P-100',assessmentAt:at(0),lifeSupport:false,acknowledgementsComplete:true,acknowledgementsCheckedAt:at(0),outageAcknowledgements:[],outage:{id:'O-100',noticeVersion:2,affectedPremisesIds:['P-100','P-101'],status:'scheduled',startsAt:at(24),endsAt:at(30),lastCheckedAt:at(-1)}};
const ack={outageId:'O-100',premisesId:'P-100',noticeVersion:2,acknowledgedAt:at(-2)};
test('only an exact premises match qualifies, even in the same region',()=>{
  assert.equal(evaluateOutageReadiness(base).flagged,true);
  for(const affectedPremisesIds of [['P-10'],['P-1000'],['P-OTHER'],[],null])assert.equal(evaluateOutageReadiness({...base,outage:{...base.outage,affectedPremisesIds}}).flagged,false);
});
test('cancelled, restored, postponed, ongoing and unknown statuses cannot qualify',()=>{
  for(const status of ['cancelled','restored','postponed','ongoing',null,undefined])assert.equal(evaluateOutageReadiness({...base,lifeSupport:true,outage:{...base.outage,status}}).flagged,false);
});
test('acknowledgement of this premises and current notice removes the case',()=>{
  assert.equal(evaluateOutageReadiness({...base,lifeSupport:true,outageAcknowledgements:[ack]}).flagged,false);
});
test('another event, premises or superseded notice does not hide this outage',()=>{
  for(const other of [{outageId:'OTHER'},{premisesId:'P-101'},{noticeVersion:1}])assert.equal(evaluateOutageReadiness({...base,outageAcknowledgements:[{...ack,...other}]}).flagged,true);
});
test('unknown or stale event and acknowledgement inputs cannot qualify',()=>{
  for(const invalid of [{premisesId:null},{assessmentAt:null},{acknowledgementsComplete:null},{outageAcknowledgements:null},{outageAcknowledgements:[{...ack,acknowledgedAt:'invalid'}]},{outageAcknowledgements:[{...ack,acknowledgedAt:at(1)}]},{acknowledgementsCheckedAt:at(-25)},{acknowledgementsCheckedAt:at(1)}])assert.equal(evaluateOutageReadiness({...base,...invalid}).flagged,false);
  for(const invalid of [{id:null},{noticeVersion:null},{lastCheckedAt:at(-25)},{lastCheckedAt:at(1)},{lastCheckedAt:undefined}])assert.equal(evaluateOutageReadiness({...base,outage:{...base.outage,...invalid}}).flagged,false);
  assert.equal(evaluateOutageReadiness({...base,outage:{...base.outage,lastCheckedAt:at(-24)}}).flagged,true);
});
test('past, already-started, inverted and out-of-window schedules are excluded',()=>{
  for(const [start,end] of [[-10,-5],[-1,5],[0,6],[30,24],[24,24],[168.01,170]])assert.equal(evaluateOutageReadiness({...base,outage:{...base.outage,startsAt:at(start),endsAt:at(end)}}).flagged,false);
  assert.equal(evaluateOutageReadiness({...base,outage:{...base.outage,startsAt:at(168),endsAt:at(174)}}).flagged,true);
});
test('duration comes from the current schedule and priority follows matched evidence',()=>{
  const long=evaluateOutageReadiness({...base,duration:1});assert.equal(long.duration,6);assert.equal(long.priority,'High');
  const short=evaluateOutageReadiness({...base,outage:{...base.outage,endsAt:at(29.99)}});assert.equal(short.priority,'Review');
  const life=evaluateOutageReadiness({...base,lifeSupport:true});assert.equal(life.priority,'Urgent');assert.ok(life.factors.some(f=>f.id==='life-support'));
  assert.deepEqual(long.factors.map(f=>f.id),['premises','scheduled','acknowledgement','duration']);
});
test('scenario includes both retailers, retained life support and every exclusion type',async()=>{
  const data=JSON.parse(await readFile(new URL('./dist/data.json',import.meta.url),'utf8'));
  const candidates=data.cases.filter(r=>r.extension==='outage');
  for(const retailer of ['Horizon Power','Synergy'])assert.ok(candidates.some(r=>r.retailer===retailer&&evaluateOutageReadiness(r).flagged));
  assert.ok(candidates.some(r=>r.lifeSupport&&evaluateOutageReadiness(r).flagged));
  assert.ok(candidates.some(r=>r.lifeSupport&&!evaluateOutageReadiness(r).flagged));
  for(const status of ['cancelled','restored']){const subset=candidates.filter(r=>r.outage.status===status);assert.ok(subset.length);assert.ok(subset.every(r=>!evaluateOutageReadiness(r).flagged));}
  const acknowledged=candidates.filter(r=>r.outageAcknowledgements.some(a=>a.outageId===r.outage.id&&a.noticeVersion===r.outage.noticeVersion));assert.ok(acknowledged.length);assert.ok(acknowledged.every(r=>!evaluateOutageReadiness(r).flagged));
  assert.ok(candidates.some(r=>r.outage.affectedPremisesIds===null&&!evaluateOutageReadiness(r).flagged));
});
