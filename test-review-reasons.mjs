import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {cutoff,time} from './teamconnect/core.mjs';
import {reviewInfo,matchesReviewReason} from './teamconnect/review-reasons.mjs';

const c={customer_id:'C1'};
const need=(type,extra={})=>({customer_id:'C1',need_type:type,status:'current',effective_from:'2025-01-01',effective_to:'',source_event_date:'2025-01-01',...extra});
const data=(needs,extra={})=>({needs,cases:[],arrangements:[],permissions:[],contacts:[],offers:[],decisions:[],deliveries:[],resolutions:[],...extra});
const at=(d,date='2025-01-17')=>reviewInfo(d,c,cutoff(date));

test('every distinct current reason is retained, newest first, without mutating records',()=>{
  const d=data([need('financial_pressure_disclosed'),need('cooling_access_need',{source_event_date:'2025-01-10'}),need('cooling_access_need')]);
  const before=JSON.stringify(d);
  const info=at(d);
  assert.deepEqual(info.reasons,['cooling_access_need','financial_pressure_disclosed']);
  assert.equal(info.flagged,'2025-01-10');
  assert.equal(JSON.stringify(d),before);
});

test('both disclosure filters match secondary reasons and retain the complete list',()=>{
  for(const types of [['financial_pressure_disclosed','cooling_access_need'],['cooling_access_need','financial_pressure_disclosed']]){
    const info=at(data(types.map((type,i)=>need(type,{source_event_date:`2025-01-0${i+1}`}))));
    for(const filter of ['', 'financial','needs'])assert.equal(matchesReviewReason(info,filter),true);
    assert.equal(info.reasons.length,2);
    assert.equal(matchesReviewReason(info,'support'),false);
  }
});

test('resolved, closed-account, expired, future and other customers needs are excluded',()=>{
  const info=at(data([need('cooling_access_need'),need('resolved_reason',{status:'resolved'}),need('closed_reason',{status:'closed_account'}),need('expired_reason',{effective_to:'2025-01-17'}),need('future_reason',{effective_from:'2025-01-18'}),need('other_customer',{customer_id:'C2'})]));
  assert.deepEqual(info.reasons,['cooling_access_need']);
  assert.equal(matchesReviewReason(info,'financial'),false);
});

test('effective dates use the selected date with an exclusive end',()=>{
  const d=data([need('financial_pressure_disclosed',{effective_to:'2025-01-18'}),need('cooling_access_need',{effective_from:'2025-01-18',source_event_date:'2025-01-18'})]);
  assert.deepEqual(at(d,'2025-01-17').reasons,['financial_pressure_disclosed']);
  assert.deepEqual(at(d,'2025-01-18').reasons,['cooling_access_need']);
});

test('resolved-only disclosures are not presented as current review reasons',()=>{
  const info=at(data([need('affordability_concern',{status:'resolved'})]));
  assert.deepEqual(info.reasons,[]);
  assert.equal(info.need,undefined);
  assert.equal(matchesReviewReason(info,'financial'),false);
  assert.equal(matchesReviewReason(info,'needs'),false);
});

test('support fallback retains every distinct active arrangement and ignores ended ones',()=>{
  const arrangement=(type,status='active')=>({customer_id:'C1',arrangement_type:type,status,effective_from:'2025-01-01',effective_to:'',source_event_date:'2025-01-01'});
  const info=at(data([],{arrangements:[arrangement('payment_plan'),arrangement('bill_extension'),arrangement('payment_plan'),arrangement('hardship_program','term_ended')]}));
  assert.deepEqual(info.reasons,['payment_plan','bill_extension']);
  assert.equal(matchesReviewReason(info,'support'),true);
  assert.equal(matchesReviewReason(info,'financial'),false);
  assert.equal(matchesReviewReason(info,'needs'),false);
});

test('support-record filtering still matches accounts with disclosures and known cases',()=>{
  const info=at(data([need('cooling_access_need'),need('financial_pressure_disclosed')],{cases:[{customer_id:'C1',case_id:'CASE1',opened_at:'2025-01-01'}]}));
  assert.deepEqual(info.reasons,['cooling_access_need','financial_pressure_disclosed']);
  assert.equal(matchesReviewReason(info,'support'),true);
  const fallback=at(data([],{cases:[{customer_id:'C1',case_id:'CASE1',opened_at:'2025-01-01'}]}));
  assert.deepEqual(fallback.reasons,['support_review']);
});

test('real scenario preserves mixed reasons under both filters and excludes future histories',async()=>{
  const d=JSON.parse(await readFile(new URL('./teamconnect/scenario.json',import.meta.url),'utf8'));
  const c=d.customers.find(r=>r.customer_id==='C102046');
  const info=reviewInfo(d,c,cutoff('2025-01-17'));
  assert.ok(info.reasons.includes('financial_pressure_disclosed'));
  assert.ok(info.reasons.includes('temperature_management_need'));
  for(const filter of ['financial','needs'])assert.equal(matchesReviewReason(info,filter),true);
  for(const date of ['2025-01-17','2025-02-04','2025-03-07']){
    for(const c of d.customers){
      const info=reviewInfo(d,c,cutoff(date));
      const t=cutoff(date);
      const expected=new Set(d.needs.filter(r=>r.customer_id===c.customer_id&&r.status==='current'&&time(r.effective_from)<=t&&(!r.effective_to||t<time(r.effective_to))).map(r=>r.need_type));
      if(expected.size)assert.deepEqual(new Set(info.reasons),expected);
    }
  }
});
