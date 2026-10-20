export const HEAT_RULES=Object.freeze({maximumBalanceAgeHours:24,forecastHours:168,recentTopUpHours:72});
const HOUR=3600000;
const numeric=value=>typeof value==='number'&&Number.isFinite(value);
const timestamp=value=>typeof value==='string'?Date.parse(value):NaN;
const cents=value=>Math.round((value+Number.EPSILON)*100)/100;
const dollars=value=>`$${value.toFixed(2)}`;

export function evaluateHeatwaveCredit(account){
  const reject=()=>({flagged:false,priority:null,factors:[],rule:null});
  const now=timestamp(account.assessmentAt),balanceAt=timestamp(account.balanceAt),forecast=account.heatForecast;
  if(account.prepay!==true||!forecast||forecast.isHeatEvent!==true||forecast.locationMatched!==true||forecast.region!==account.region||account.topUpsComplete!==true||!Array.isArray(account.topUps))return reject();
  const start=timestamp(forecast.startsAt),end=timestamp(forecast.endsAt),age=(now-balanceAt)/HOUR;
  if(![now,balanceAt,start,end].every(Number.isFinite)||age<0||age>HEAT_RULES.maximumBalanceAgeHours||end<=now||end<=start||end-now>HEAT_RULES.forecastHours*HOUR)return reject();
  if(!numeric(account.credit)||account.credit<0||!numeric(account.dailyCost)||account.dailyCost<=0||!numeric(forecast.dailyCost)||forecast.dailyCost<=0||!numeric(forecast.peakTemperature))return reject();
  const ids=new Set();
  for(const t of account.topUps){
    if(!t||typeof t.id!=='string'||!t.id||ids.has(t.id)||!numeric(t.amount)||t.amount<=0||!['posted','pending'].includes(t.status)||!Number.isFinite(timestamp(t.at)))return reject();
    ids.add(t.id);
  }
  const posted=account.topUps.filter(t=>t.status==='posted'&&timestamp(t.at)<=now);
  const addedAfterRead=posted.filter(t=>timestamp(t.at)>balanceAt).reduce((sum,t)=>sum+t.amount,0);
  const recentTopUpTotal=posted.filter(t=>timestamp(t.at)>=now-HEAT_RULES.recentTopUpHours*HOUR).reduce((sum,t)=>sum+t.amount,0);
  const pendingTopUpTotal=account.topUps.filter(t=>t.status==='pending'&&timestamp(t.at)<=now).reduce((sum,t)=>sum+t.amount,0);
  // The meter balance already includes posted top-ups at or before its timestamp.
  const availableCredit=cents(Math.max(0,account.credit+addedAfterRead-account.dailyCost*age/24));
  const hoursToHeat=Math.max(0,(start-now)/HOUR),hoursToEnd=(end-now)/HOUR;
  const costBeforeHeat=account.dailyCost*hoursToHeat/24;
  const costThroughHeat=costBeforeHeat+forecast.dailyCost*(hoursToEnd-hoursToHeat)/24;
  const shortfall=cents(Math.max(0,costThroughHeat-availableCredit));
  const runOutHours=availableCredit<=costBeforeHeat?availableCredit/(account.dailyCost/24):hoursToHeat+(availableCredit-costBeforeHeat)/(forecast.dailyCost/24);
  const riskInHours=Math.max(hoursToHeat,runOutHours);
  const values={availableCredit,addedAfterRead:cents(addedAfterRead),recentTopUpTotal:cents(recentTopUpTotal),pendingTopUpTotal:cents(pendingTopUpTotal),hoursToHeat,hoursToEnd,runOutHours,riskInHours,shortfall,costThroughHeat:cents(costThroughHeat)};
  if(shortfall<=0||runOutHours>=hoursToEnd)return {...reject(),...values};
  const beforeHeat=runOutHours<hoursToHeat;
  const factors=[
    {id:'heat',label:`${forecast.peakTemperature}°C peak · ${hoursToHeat?`heat starts in ${Math.round(hoursToHeat)}h`:'heat underway'}`,short:`${forecast.peakTemperature}°C · ${hoursToHeat?`in ${Math.round(hoursToHeat)}h`:'underway'}`},
    {id:'run-out',label:`Credit runs out in ${Math.round(runOutHours)}h · ${beforeHeat?'before heat':'during heat'}`,short:`${Math.round(runOutHours)}h to empty`},
    {id:'shortfall',label:`${dollars(shortfall)} short through heat · est.`,short:`${dollars(shortfall)} short`},
    {id:'top-ups',label:recentTopUpTotal?`${dollars(recentTopUpTotal)} posted top-ups · 72h`:'No posted top-ups · 72h',short:recentTopUpTotal?`${dollars(recentTopUpTotal)} recent top-ups`:'No recent top-ups'}
  ];
  if(pendingTopUpTotal)factors.push({id:'pending',label:`${dollars(pendingTopUpTotal)} pending top-up · excluded`,short:`${dollars(pendingTopUpTotal)} pending`});
  const priority=riskInHours<24?'Urgent':riskInHours<48?'High':'Review';
  return {flagged:true,...values,beforeHeat,priority,factors,rule:priority==='Urgent'?'Heat credit gap starts < 24h':priority==='High'?'Heat credit gap starts < 48h':'Heat credit gap starts ≥ 48h'};
}
