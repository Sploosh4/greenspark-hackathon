import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {DEFAULT,cutoff,caseStage,funnelFor,billedFor} from './teamconnect/core.mjs';
import {REVIEW_DEFAULTS,reviewFor,selectReviews} from './teamconnect/review.mjs';
const d=JSON.parse(await readFile(new URL('./teamconnect/scenario.json',import.meta.url)));
const customer=id=>d.customers.find(c=>c.customer_id===id);
const rows=d.customers.map(c=>reviewFor(d,c,DEFAULT.date,DEFAULT.event));
const state={...DEFAULT,...REVIEW_DEFAULTS};

test('queue combines search, community, account and reason filters without changing source records',()=>{
 const before=JSON.stringify(rows);
 const selected=selectReviews(rows,{...state,search:'C105011',scope:'South Hedland',account:'prepaid',signal:'needs'});
 assert.equal(selected.length,1);assert.equal(selected[0].reference,'C105011');
 assert.equal(JSON.stringify(rows),before);
 assert.equal(selectReviews(rows,{...state,search:'does-not-exist'}).length,0);
 assert.equal(selectReviews(rows,{...state,search:'C105011',account:'billed'}).length,0);
});
test('every queue sort works in both directions with deterministic ties',()=>{
 for(const sort of ['reference','community','account','reason','date','support','contact']){
  const asc=selectReviews(rows,{...state,sort,direction:'asc'}),desc=selectReviews(rows,{...state,sort,direction:'desc'});
  assert.equal(new Set(asc.map(r=>r.reference)).size,448);assert.equal(desc.length,448);
  assert.equal(new Set(desc.map(r=>r.reference)).size,448);
 }
 assert.equal(selectReviews(rows,{...state,sort:'reference',direction:'desc'})[0].reference,'C105149');
});
test('disclosures, support and contact preferences use case-date effective state',()=>{
 const early=reviewFor(d,customer('C105011'),'2025-01-15','HEAT01');
 const current=reviewFor(d,customer('C105011'),'2025-01-17','HEAT01');
 const delivered=reviewFor(d,customer('C105011'),'2025-01-21','HEAT01');
 const resolved=reviewFor(d,customer('C105011'),'2025-01-28','HEAT01');
 assert.equal(early.activeNeeds.length,0);assert.equal(current.activeNeeds.length,1);
 assert.equal(current.support.length,0);assert.equal(delivered.support.length,1);
 assert.equal(resolved.activeNeeds.length,0);assert.equal(resolved.support.length,0);
 assert.equal(current.contact,'email');
});
test('weather-relevant needs require current explicit cooling disclosure and a nonexpired issued forecast',()=>{
 const cooling=customer('C101664');
 assert.ok(reviewFor(d,cooling,'2025-01-17','HEAT01').weatherNeeds.length);
 assert.equal(reviewFor(d,cooling,'2025-01-12','HEAT01').weatherNeeds.length,0);
 assert.equal(reviewFor(d,cooling,'2025-01-28','HEAT01').weatherNeeds.length,0);
 assert.equal(reviewFor(d,cooling,'2025-01-17','FLOOD01').weatherNeeds.length,0);
});
test('review due today is not overdue and closed accounts do not receive financial flags',()=>{
 const source=structuredClone(d),c=customer('C105011');
 source.arrangements=[{customer_id:c.customer_id,status:'active',effective_from:'2025-01-01',review_due_date:'2025-01-17'}];
 assert.equal(reviewFor(source,c,'2025-01-17','HEAT01').due.length,0);
 assert.equal(reviewFor(source,c,'2025-01-18','HEAT01').due.length,1);
 assert.ok(!reviewFor(d,{...c,account_close_date:'2025-01-16'},'2025-01-17','HEAT01').reasons.includes('Recorded off-supply periods'));
});
test('unknown contact is distinct from an explicit unsuccessful contact; latest decision governs stage',()=>{
 const source={contacts:[],offers:[],decisions:[],deliveries:[],resolutions:[]},k={case_id:'case'};
 assert.equal(caseStage(source,k,cutoff(DEFAULT.date)).stage,'Contact not recorded');
 source.contacts=[{case_id:'case',occurred_at:'2025-01-01',outcome:'not_reached'}];
 assert.equal(caseStage(source,k,cutoff(DEFAULT.date)).stage,'Not reached');
 source.offers=[{case_id:'case',offer_id:'offer',offered_at:'2025-01-01'}];
 source.decisions=[{offer_id:'offer',decided_at:'2025-01-02',decision:'accepted'},{offer_id:'offer',decided_at:'2025-01-03',decision:'declined'}];
 assert.equal(caseStage(source,k,cutoff(DEFAULT.date)).stage,'Offer declined');
});
test('campaign cases cannot invent or enlarge their geographic audience denominator',()=>{
 const source=structuredClone(d),campaign=source.campaigns.find(r=>r.event_id==='HEAT01');
 source.audience=[];
 source.cases.push({customer_id:'C105011',case_id:'out-of-audience',campaign_id:campaign.campaign_id,opened_at:'2025-01-14'});
 const result=funnelFor(source,DEFAULT);assert.equal(result.audience.length,0);assert.equal(Object.keys(result.groups).length,0);
});
test('canonical billed arithmetic is retained and missing elapsed days or rate evidence withhold estimates',()=>{
 assert.equal(billedFor(d,'C105019','2025-03-07').estimate,18428);
 assert.equal(billedFor(d,'C105019','2025-03-07').baseline,16789);
 const source=structuredClone(d);source.billed_usage.C105019=source.billed_usage.C105019.filter(r=>r[0]!=='2025-03-02');
 assert.equal(billedFor(source,'C105019','2025-03-07').estimate,null);
 assert.equal(billedFor(source,'C105019','2025-03-07').baseline,16789);
 source.billed_rules.C105019.usage_cents_per_kwh=NaN;
 assert.equal(billedFor(source,'C105019','2025-03-07').estimate,null);
 source.bills.filter(r=>r.customer_id==='C100019').forEach(r=>delete r.usage_charge_cents);
 assert.equal(billedFor(source,'C100019','2025-03-07').estimate,null);
});
