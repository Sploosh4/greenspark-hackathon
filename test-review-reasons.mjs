import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {cutoff,time,openAt} from './teamconnect/core.mjs';
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
  assert.equal(info.recorded,'2025-01-10');
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

test('longstanding needs and an active arrangement do not invent a review trigger',()=>{
  const d=data([need('registered_life_support',{source_event_date:'2022-06-18'})],{
    arrangements:[{customer_id:'C1',arrangement_type:'payment_plan',status:'active',effective_from:'2024-12-31',source_event_date:'2024-12-31',review_due_date:'2025-01-30'}]});
  const info=at(d);
  assert.deepEqual(info.triggers,[]);
  assert.deepEqual(info.supportNeeds,['registered_life_support']);
  assert.equal(info.recorded,'2022-06-18');
});

test('a current disclosure recorded today supplies a dated trigger without making older needs triggers',()=>{
  const info=at(data([need('registered_life_support',{source_event_date:'2022-06-18'}),need('cooling_access_need',{source_event_date:'2025-01-17'})]));
  assert.deepEqual(info.triggers,[{type:'disclosure_recorded',reason:'cooling_access_need',recorded:'2025-01-17'}]);
  assert.deepEqual(info.supportNeeds,['cooling_access_need','registered_life_support']);
});

test('case triggers use the exact need link and survive the opening day until resolution is recorded',()=>{
  const d=data([need('registered_life_support',{need_id:'LIFE'}),need('cooling_access_need',{need_id:'COOL',source_event_date:'2025-01-17'})],{
    cases:[{case_id:'CASE1',customer_id:'C1',need_id:'COOL',opened_at:'2025-01-17 09:00:00'}]});
  for(const date of ['2025-01-17','2025-01-18'])assert.deepEqual(at(d,date).triggers,[{type:'case_opened',reason:'cooling_access_need',recorded:'2025-01-17 09:00:00'}]);
  assert.deepEqual(at(d,'2025-01-16').triggers,[]);
});

test('unlinked cases are not attributed to a coincident disclosed need',()=>{
  const info=at(data([need('registered_life_support',{need_id:'LIFE'})],{
    cases:[{case_id:'CASE1',customer_id:'C1',need_id:'UNMATCHED',opened_at:'2025-01-10'}]}));
  assert.deepEqual(info.triggers,[{type:'case_opened',reason:'',recorded:'2025-01-10'}]);
});

test('resolved cases stop supplying a trigger only when the resolution is known',()=>{
  const d=data([need('registered_life_support',{need_id:'LIFE'})],{
    cases:[{case_id:'CASE1',customer_id:'C1',need_id:'LIFE',opened_at:'2025-01-10'}],
    resolutions:[{case_id:'CASE1',resolved_at:'2025-01-18 09:00:00'}]});
  assert.equal(at(d,'2025-01-17').triggers.length,1);
  assert.deepEqual(at(d,'2025-01-18').triggers,[]);
  assert.deepEqual(at(d,'2025-01-18').supportNeeds,['registered_life_support']);
});

test('future, expired and resolved disclosures cannot supply a current-day trigger',()=>{
  const info=at(data([need('future',{source_event_date:'2025-01-17 13:00:00'}),need('expired',{source_event_date:'2025-01-17',effective_to:'2025-01-17'}),need('resolved',{source_event_date:'2025-01-17',status:'resolved'}),need('other_customer',{customer_id:'C2',source_event_date:'2025-01-17'})]));
  assert.deepEqual(info.triggers,[]);
});

test('actual scenario separates the cooling case from background registration and preserves missing-trigger examples',async()=>{
  const d=JSON.parse(await readFile(new URL('./teamconnect/scenario.json',import.meta.url),'utf8'));
  const info=(id,date='2025-01-17')=>reviewInfo(d,d.customers.find(c=>c.customer_id===id),cutoff(date));
  assert.deepEqual(info('C101366').triggers,[{type:'case_opened',reason:'cooling_access_need',recorded:'2025-01-17 09:00:00'}]);
  assert.deepEqual(info('C101366').supportNeeds,['cooling_access_need','registered_life_support']);
  for(const id of ['C100562','C102046'])assert.deepEqual(info(id).triggers,[]);
  assert.deepEqual(info('C100562').supportNeeds,[]);
  assert.equal(info('C100562').recorded,'2024-12-31');
  assert.deepEqual(info('C105011','2025-01-28').triggers,[]);
});

const plan=(extra={})=>({customer_id:'C1',arrangement_id:'PLAN1',arrangement_type:'payment_plan',status:'active',effective_from:'2024-12-31',effective_to:'',source_event_date:'2024-12-31',review_due_date:'2025-01-30',...extra});

test('future arrangement reviews do not qualify by themselves and support details remain available',()=>{
  const d=data([],{arrangements:[plan()]}),before=JSON.stringify(d),info=at(d);
  assert.equal(info.inReview,false);
  assert.deepEqual(info.triggers,[]);
  assert.deepEqual(info.reasons,['payment_plan']);
  assert.equal(info.hasSupport,true);
  assert.equal(info.arr[0].review_due_date,'2025-01-30');
  assert.equal(info.recorded,'2024-12-31');
  assert.equal(JSON.stringify(d),before);
});

test('arrangement review qualifies on its due date and remains due afterward',()=>{
  const d=data([],{arrangements:[plan()]});
  assert.equal(at(d,'2025-01-29').inReview,false);
  for(const date of ['2025-01-30','2025-01-31']){
    const info=at(d,date);
    assert.equal(info.inReview,true);
    assert.deepEqual(info.triggers,[{type:'arrangement_review_due',reason:'payment_plan',recorded:'2025-01-30'}]);
    assert.equal(info.supportNeeds.length,0);
    assert.equal(matchesReviewReason(info,'support'),true);
  }
});

test('review deadlines respect the noon cutoff and missing or invalid dates do not qualify',()=>{
  for(const due of ['2025-01-17 11:59:00','2025-01-17 12:00:00'])assert.equal(at(data([],{arrangements:[plan({review_due_date:due})]})).inReview,true);
  for(const due of ['2025-01-17 12:01:00','','not-a-date'])assert.equal(at(data([],{arrangements:[plan({review_due_date:due})]})).inReview,false);
});

test('ended, future, inactive and other-customer arrangements cannot supply due-review triggers',()=>{
  const rows=[plan({effective_to:'2025-01-17',review_due_date:'2025-01-01'}),plan({effective_from:'2025-01-18',review_due_date:'2025-01-01'}),plan({customer_id:'C2',review_due_date:'2025-01-01'}),...['completed','term_ended','broken','closed_account'].map(status=>plan({status,review_due_date:'2025-01-01'}))];
  const info=at(data([],{arrangements:rows}));
  assert.deepEqual(info.triggers,[]);
  assert.equal(info.inReview,false);
  assert.deepEqual(info.arr,[]);
});

test('another recorded trigger qualifies an arrangement account before its review is due',()=>{
  const d=data([],{arrangements:[plan()],cases:[{case_id:'CASE1',customer_id:'C1',opened_at:'2025-01-16'}],resolutions:[{case_id:'CASE1',resolved_at:'2025-01-18'}]});
  assert.equal(at(d,'2025-01-17').inReview,true);
  assert.equal(at(d,'2025-01-17').triggers[0].type,'case_opened');
  const resolved=at(d,'2025-01-18');
  assert.equal(resolved.inReview,false);
  assert.equal(resolved.arr.length,1);
  assert.equal(resolved.cases.length,1);
});

test('a current disclosed need keeps its existing eligibility and any-need filter behaviour',()=>{
  const info=at(data([need('financial_pressure_disclosed'),need('cooling_access_need')],{arrangements:[plan()]}));
  assert.equal(info.inReview,true);
  assert.deepEqual(info.triggers,[]);
  for(const filter of ['financial','needs','support'])assert.equal(matchesReviewReason(info,filter),true);
});

test('the current effective arrangement history controls whether a review is due',()=>{
  const d=data([],{arrangements:[plan({effective_to:'2025-01-30'}),plan({status:'completed',effective_from:'2025-01-30',review_due_date:''})]});
  assert.equal(at(d,'2025-01-29').inReview,false);
  assert.equal(at(d,'2025-01-30').inReview,false);
  assert.deepEqual(at(d,'2025-01-30').triggers,[]);
});

test('actual scenario removes only the two not-yet-due arrangement-only entries at the default date',async()=>{
  const d=JSON.parse(await readFile(new URL('./teamconnect/scenario.json',import.meta.url),'utf8'));
  const info=(id,date='2025-01-17')=>reviewInfo(d,d.customers.find(c=>c.customer_id===id),cutoff(date));
  const rows=d.customers.filter(c=>openAt(c,cutoff('2025-01-17'))).map(c=>({id:c.customer_id,i:info(c.customer_id)}));
  assert.deepEqual(rows.filter(({i})=>i.reasons.length&&!i.inReview).map(r=>r.id).sort(),['C100562','C104786']);
  assert.equal(rows.filter(({i})=>i.inReview).length,99);
  assert.equal(info('C100562').arr[0].arrangement_type,'payment_plan');
  assert.equal(info('C100562','2025-01-28').inReview,true);
  assert.ok(info('C100562','2025-01-28').triggers.some(t=>t.type==='case_opened'));
  assert.ok(info('C100562','2025-01-30').triggers.some(t=>t.type==='arrangement_review_due'));
  const overdue=info('C100850');
  assert.equal(overdue.inReview,true);
  assert.deepEqual(overdue.supportNeeds,[]);
  assert.ok(overdue.triggers.some(t=>t.type==='arrangement_review_due'&&t.recorded==='2024-12-13'));
});
