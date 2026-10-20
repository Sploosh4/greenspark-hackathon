export const BILL_PRESSURE_RULES = Object.freeze({minimumIncrease:25,highIncrease:40,urgentFactorCount:2});

const amount = value => typeof value === 'number' && Number.isFinite(value);
const dollars = value => new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',maximumFractionDigits:0}).format(value);

export function paymentStressFactors(account) {
  const factors=[];
  if(amount(account.missedPayments90d) && account.missedPayments90d>=1){
    const n=account.missedPayments90d;
    factors.push({id:'missed',label:`${n} missed payment${n===1?'':'s'} · 90d`,short:`${n} missed payment${n===1?'':'s'}`});
  }
  if(amount(account.failedDirectDebits90d) && account.failedDirectDebits90d>=1){
    const n=account.failedDirectDebits90d;
    factors.push({id:'failed-dd',label:`${n} failed direct debit${n===1?'':'s'} · 90d`,short:`${n} failed direct debit${n===1?'':'s'}`});
  }
  if(amount(account.arrearsPrevious) && amount(account.arrearsCurrent) && account.arrearsPrevious>=0 && account.arrearsCurrent>account.arrearsPrevious){
    const delta=account.arrearsCurrent-account.arrearsPrevious;
    factors.push({id:'arrears',label:`Arrears +${dollars(delta)} · Nov–Dec`,short:`Arrears +${dollars(delta)}`});
  }
  return factors;
}

export function evaluateBillPressure(account) {
  const factors=paymentStressFactors(account);
  const flagged=account.prepay===false && amount(account.uplift) && account.uplift>=BILL_PRESSURE_RULES.minimumIncrease && factors.length>0;
  if(!flagged)return {flagged:false,priority:null,factors,rule:null};
  const highIncrease=account.uplift>=BILL_PRESSURE_RULES.highIncrease;
  const multiple=factors.length>=BILL_PRESSURE_RULES.urgentFactorCount;
  if(highIncrease && multiple)return {flagged:true,priority:'Urgent',factors,rule:'Increase ≥ 40% + 2+ payment signals'};
  if(highIncrease || multiple)return {flagged:true,priority:'High',factors,rule:highIncrease?'Increase ≥ 40% + payment signal':'Increase ≥ 25% + 2+ payment signals'};
  return {flagged:true,priority:'Review',factors,rule:'Increase ≥ 25% + payment signal'};
}
