export const SOLAR_RULES=Object.freeze({minimumDrop:30,minimumAdjustedShortfall:20,highShortfall:40,minimumImportRise:20,minimumSunnyDays:3});
const numeric=value=>typeof value==='number'&&Number.isFinite(value);

export function evaluateSolarPerformance(account){
  const baselineValid=numeric(account.expectedExportChange)&&account.expectedExportChange>-100;
  const actualValid=numeric(account.exportChange)&&account.exportChange>=-100;
  const shortfall=baselineValid&&actualValid?100*(account.expectedExportChange-account.exportChange)/(100+account.expectedExportChange):null;
  const factors=[];
  if(shortfall!==null&&shortfall>=SOLAR_RULES.minimumAdjustedShortfall){
    factors.push({id:'adjusted-shortfall',label:`${Math.round(shortfall)}% below weather/season-adjusted exports`,short:`${Math.round(shortfall)}% below adjusted`});
  }
  if(numeric(account.importChange)&&account.importChange>=SOLAR_RULES.minimumImportRise){
    factors.push({id:'imports',label:`+${account.importChange}% grid imports · 7d`,short:`+${account.importChange}% imports`});
  }
  if(numeric(account.sunnyDayShortfalls7d)&&account.sunnyDayShortfalls7d>=SOLAR_RULES.minimumSunnyDays){
    const n=account.sunnyDayShortfalls7d;
    factors.push({id:'sunny-days',label:`${n} comparable sunny-day shortfalls · 7d`,short:`${n} sunny-day shortfalls`});
  }
  const contextChecked=account.cloudExplainsDrop===false&&account.seasonExplainsDrop===false;
  const flagged=actualValid&&account.exportChange<=-SOLAR_RULES.minimumDrop&&contextChecked&&factors.some(f=>f.id==='adjusted-shortfall')&&factors.some(f=>f.id!=='adjusted-shortfall');
  if(!flagged)return {flagged:false,priority:null,factors,shortfall,rule:null};
  const high=shortfall>=SOLAR_RULES.highShortfall&&factors.length===3;
  return {flagged:true,priority:high?'High':'Review',factors,shortfall,rule:high?'Adjusted shortfall ≥ 40% + 2 signals':'Adjusted shortfall ≥ 20% + supporting signal'};
}
