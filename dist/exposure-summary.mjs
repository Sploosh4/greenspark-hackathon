import {customerKey,groupCustomerFlags} from './customer-review.mjs';

export const COHORT_LABELS=Object.freeze({heat:'prepay accounts',bill:'billed accounts',solar:'solar accounts',usage:'accounts',outage:'accounts'});
const flatten=rows=>rows.flatMap(r=>r.flags||[r]);
const validIdentity=r=>typeof r.customer==='string'&&r.customer.length>0&&typeof r.retailer==='string'&&r.retailer.length>0;
const inScope=(r,{retailer='all',region='all'}={})=>(retailer==='all'||r.retailer===retailer)&&(region==='all'||r.region===region);
const inCohort=(r,extension)=>extension==='heat'?r.prepay===true:extension==='bill'?r.prepay===false:extension==='solar'?r.hasSolar===true&&r.prepay===false:true;

export function uniqueExtensionRows(rows,extension){
  return groupCustomerFlags(flatten(rows).filter(r=>r.extension===extension)).map(r=>r.flags[0]);
}

export function exposureSummary(rows,population,scope={}){
  const {extension=null,days=7}=scope;
  const accounts=new Map(population.filter(r=>validIdentity(r)&&inScope(r,scope)&&inCohort(r,extension)).map(r=>[customerKey(r),r]));
  const flags=flatten(rows).filter(r=>inScope(r,scope)&&(!extension||r.extension===extension)&&r.dueDay>=0&&r.dueDay<days);
  const customers=groupCustomerFlags(flags);
  const unknownCustomers=customers.filter(r=>!accounts.has(r.id)).length;
  const signals=[...new Set(flags.map(r=>r.extension))].map(id=>({id,count:new Set(flags.filter(r=>r.extension===id).map(customerKey)).size})).sort((a,b)=>b.count-a.count||a.id.localeCompare(b.id));
  const count=customers.length,total=accounts.size;
  return {count,total,percentage:total>0&&unknownCustomers===0?count/total*100:null,unknownCustomers,signals,priorities:Object.fromEntries(['Urgent','High','Review'].map(p=>[p,customers.filter(r=>r.priority===p).length]))};
}

export function regionalExposure(rows,population,scope={}){
  const regions=[...new Set([...population,...flatten(rows)].filter(r=>inScope(r,scope)).map(r=>r.region))].filter(Boolean);
  return regions.map(region=>({region,...exposureSummary(rows,population,{...scope,region,extension:null})})).sort((a,b)=>(b.percentage??-1)-(a.percentage??-1)||b.count-a.count||a.region.localeCompare(b.region));
}
