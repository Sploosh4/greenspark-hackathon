export const OUTAGE_RULES=Object.freeze({maximumCheckAgeHours:24,forecastHours:168,highDurationHours:6});
const HOUR=3600000;
const timestamp=value=>typeof value==='string'?Date.parse(value):NaN;
const identifier=value=>typeof value==='string'&&value.trim().length>0;
const version=value=>Number.isInteger(value)&&value>0;

export function evaluateOutageReadiness(account){
  const reject=()=>({flagged:false,priority:null,factors:[],rule:null});
  const outage=account.outage,now=timestamp(account.assessmentAt);
  if(!outage||!Number.isFinite(now)||!identifier(account.premisesId)||!identifier(outage.id)||!version(outage.noticeVersion))return reject();
  if(!Array.isArray(outage.affectedPremisesIds)||!outage.affectedPremisesIds.every(identifier)||!outage.affectedPremisesIds.includes(account.premisesId))return reject();
  if(outage.status!=='scheduled'||account.acknowledgementsComplete!==true||!Array.isArray(account.outageAcknowledgements))return reject();
  const recent=value=>{const age=(now-timestamp(value))/HOUR;return Number.isFinite(age)&&age>=0&&age<=OUTAGE_RULES.maximumCheckAgeHours;};
  if(!recent(outage.lastCheckedAt)||!recent(account.acknowledgementsCheckedAt))return reject();
  const start=timestamp(outage.startsAt),end=timestamp(outage.endsAt);
  if(![start,end].every(Number.isFinite)||start<=now||end<=start||start-now>OUTAGE_RULES.forecastHours*HOUR)return reject();
  for(const ack of account.outageAcknowledgements){
    if(!ack||!identifier(ack.outageId)||!identifier(ack.premisesId)||!version(ack.noticeVersion)||!Number.isFinite(timestamp(ack.acknowledgedAt))||timestamp(ack.acknowledgedAt)>now)return reject();
  }
  const acknowledged=account.outageAcknowledgements.some(ack=>ack.outageId===outage.id&&ack.premisesId===account.premisesId&&ack.noticeVersion===outage.noticeVersion);
  if(acknowledged)return reject();
  const duration=(end-start)/HOUR;
  const when=new Date(start).toLocaleString('en-AU',{timeZone:'Australia/Perth',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false});
  const factors=[
    {id:'premises',label:`Premises ${account.premisesId} matched`,short:'Premises matched'},
    {id:'scheduled',label:`Still scheduled · ${when}`,short:'Still scheduled'},
    {id:'acknowledgement',label:'Current notice not acknowledged',short:'Not acknowledged'},
    {id:'duration',label:`${duration}h planned interruption`,short:`${duration}h duration`}
  ];
  if(account.lifeSupport===true)factors.push({id:'life-support',label:'Life support registered',short:'Life support'});
  const priority=account.lifeSupport===true?'Urgent':duration>=OUTAGE_RULES.highDurationHours?'High':'Review';
  return {flagged:true,priority,factors,duration,startsAt:outage.startsAt,endsAt:outage.endsAt,rule:priority==='Urgent'?'Matched outage + life support':priority==='High'?'Matched outage ≥ 6h · unacknowledged':'Matched outage < 6h · unacknowledged'};
}
