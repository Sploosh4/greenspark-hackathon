export const USAGE_RULES=Object.freeze({minimumDrop:30,severeDrop:65,sustainedDays:3,nearZeroDays:2,hotDayDrop:30});
const numeric=value=>typeof value==='number'&&Number.isFinite(value);

export function usageSupportFactors(account){
  const factors=[];
  if(account.prepay===true&&numeric(account.selfDisconnections7d)&&account.selfDisconnections7d>=1){
    const n=account.selfDisconnections7d;
    factors.push({id:'self-disconnection',label:`${n} self-disconnection${n===1?'':'s'} · 7d`,short:`${n} self-disconnection${n===1?'':'s'}`});
  }
  if(numeric(account.nearZeroUsageDays7d)&&account.nearZeroUsageDays7d>=USAGE_RULES.nearZeroDays){
    const n=account.nearZeroUsageDays7d;
    factors.push({id:'near-zero',label:`${n} near-zero days · 7d`,short:`${n} near-zero days`});
  }
  if(numeric(account.hotDays7d)&&account.hotDays7d>=1&&numeric(account.hotDayUsageChange)&&account.hotDayUsageChange<=-USAGE_RULES.hotDayDrop){
    factors.push({id:'hot-day',label:`${account.hotDayUsageChange}% use on ${account.hotDays7d} hot day${account.hotDays7d===1?'':'s'}`,short:`${account.hotDayUsageChange}% on hot days`});
  }
  if(numeric(account.declineDays)&&account.declineDays>=USAGE_RULES.sustainedDays){
    factors.push({id:'sustained',label:`${account.declineDays}-day decline`,short:`${account.declineDays}-day decline`});
  }
  return factors;
}

export function evaluateUsageChange(account){
  const factors=usageSupportFactors(account);
  const contextChecked=account.outageExplainsDrop===false&&account.solarExplainsDrop===false;
  const flagged=numeric(account.change)&&account.change<=-USAGE_RULES.minimumDrop&&contextChecked&&factors.length>0;
  if(!flagged)return {flagged:false,priority:null,factors,driver:null,rule:null};
  const driver=factors.some(f=>f.id==='self-disconnection')?'Self-disconnection':factors.some(f=>f.id==='near-zero')?'Near-zero use':factors.some(f=>f.id==='hot-day')?'Hot-day decline':'Sustained decline';
  const urgent=account.change < -USAGE_RULES.severeDrop;
  return {flagged:true,priority:urgent?'Urgent':'High',factors,driver,rule:urgent?'Drop > 65% + supporting signal':'Drop ≥ 30% + supporting signal'};
}
