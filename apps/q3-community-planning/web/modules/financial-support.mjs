// Dated area aggregates only. Missing support coverage is never a numeric zero.
const safe=v=>Number.isSafeInteger(v)&&v>=0;
const hash=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const tables=['hardship_programs.csv.gz','hugs_grants.csv.gz','payment_arrangements.csv.gz','payments.csv.gz','support_arrangement_history.csv.gz'];
const supportKeys=['areas','classification','cohortCustomerSha256','cohortUsageSha256','contract','coverage','definitions','historyEnd','historyStart','monthlyGrantLedger','reviewedManifestSha256','schemaVersion','snapshotDate','sourceHashes','state'];
const areaKeys=['activeAccountDenominator','activeAccountsInEitherSupport','activeHardshipProgramAccounts','activePaymentArrangementAccounts','paidGrantAmountCentsInPeriod','paidGrantCountInPeriod','paidGrantRecipientsActiveAtSnapshot','paidGrantRecipientsInPeriod','postcode','snapshotDate'];
export function validateFinancialSupport(s,b){
 if(!s||Object.keys(s).sort().join(',')!==supportKeys.join(',')||s.schemaVersion!==2||s.contract!=='q3-financial-support-v2'||s.state!=='validated'||s.snapshotDate!==b.snapshotDate||s.historyStart!==b.historyStart||s.historyEnd!==b.historyEnd||s.cohortCustomerSha256!==b.customerSourceSha256||s.cohortUsageSha256!==b.usageSourceSha256||!hash(s.reviewedManifestSha256))throw Error('Financial cohort or snapshot contract');
 const pcs=b.areas.map(a=>a.postcode).sort();
 if(JSON.stringify(s.coverage?.accountPostcodes)!==JSON.stringify(pcs)||JSON.stringify(s.coverage?.completeTables)!==JSON.stringify(tables)||!s.sourceHashes||Object.keys(s.sourceHashes).sort().join(',')!==tables.join(',')||Object.values(s.sourceHashes).some(v=>!hash(v))||!Array.isArray(s.areas)||s.areas.length!==pcs.length||s.areas.map(a=>a.postcode).join(',')!==pcs.join(','))throw Error('Financial coverage contract');
 const known=new Map(b.areas.map(a=>[a.postcode,a]));
 for(const a of s.areas){
  if(Object.keys(a).sort().join(',')!==areaKeys.join(',')||a.snapshotDate!==b.snapshotDate||a.activeAccountDenominator!==known.get(a.postcode).accountCount||areaKeys.filter(k=>!['postcode','snapshotDate'].includes(k)).some(k=>!safe(a[k])))throw Error('Financial area counts');
  const n=a.activeAccountDenominator,p=a.activePaymentArrangementAccounts,h=a.activeHardshipProgramAccounts,u=a.activeAccountsInEitherSupport;
  if(Math.max(p,h)>u||u>Math.min(n,p+h)||a.paidGrantRecipientsActiveAtSnapshot>Math.min(n,a.paidGrantRecipientsInPeriod)||a.paidGrantRecipientsInPeriod>known.get(a.postcode).retainedAccountCount||a.paidGrantRecipientsInPeriod>a.paidGrantCountInPeriod)throw Error('Financial count reconciliation');
 }
 if(!Array.isArray(s.monthlyGrantLedger))throw Error('Grant ledger contract');
 const keys=new Set(),totals=new Map(pcs.map(pc=>[pc,{count:0,cents:0}]));
 for(const row of s.monthlyGrantLedger){
  const key=row.postcode+':'+row.month;
  if(!known.has(row.postcode)||!/^\d{4}-(0[1-9]|1[0-2])$/.test(row.month)||row.month<s.historyStart.slice(0,7)||row.month>s.historyEnd.slice(0,7)||keys.has(key)||!safe(row.retainedAccountsReceivingPaidGrant)||!safe(row.paidGrantCount)||!safe(row.paidGrantAmountCents)||row.retainedAccountsReceivingPaidGrant>row.paidGrantCount||row.retainedAccountsReceivingPaidGrant>known.get(row.postcode).retainedAccountCount)throw Error('Grant month coverage');
  keys.add(key);const total=totals.get(row.postcode);total.count+=row.paidGrantCount;total.cents+=row.paidGrantAmountCents;
 }
 for(const a of s.areas)if(a.paidGrantCountInPeriod!==totals.get(a.postcode).count||a.paidGrantAmountCentsInPeriod!==totals.get(a.postcode).cents)throw Error('Grant period reconciliation');
 return s;
}

export function financialSummary(b,postcode=null,{retained=false}={}){
 if(!b?.financialSupport)return {state:'unavailable',reason:b?.financialSupportUnavailableReason==='business_source_changed'?'Support history was cleared when the account source changed. Upload the matching files.':'No matching support history is loaded for this account snapshot.'};
 const s=validateFinancialSupport(b.financialSupport,b),areas=postcode===null?s.areas:s.areas.filter(a=>a.postcode===postcode);
 if(!areas.length)return {state:'unavailable',reason:'No financial/account coverage is loaded for this location.'};
 const sum=key=>areas.reduce((n,a)=>n+a[key],0);
 return {state:'available',retained,snapshotDate:s.snapshotDate,historyStart:s.historyStart,historyEnd:s.historyEnd,coveredAreas:areas.length,denominator:sum('activeAccountDenominator'),paymentArrangements:sum('activePaymentArrangementAccounts'),hardshipPrograms:sum('activeHardshipProgramAccounts'),eitherSupport:sum('activeAccountsInEitherSupport'),grantRecipients:sum('paidGrantRecipientsInPeriod'),grantRecipientsActiveAtSnapshot:sum('paidGrantRecipientsActiveAtSnapshot'),paidGrantCount:sum('paidGrantCountInPeriod'),paidGrantAmountCents:sum('paidGrantAmountCentsInPeriod')};
}

export function renderFinancialSupport(b,postcode,{retained=false,lookup=s=>document.querySelector(s)}={}){
 const summary=financialSummary(b,postcode,{retained});
 const $=lookup,fmt=v=>v.toLocaleString('en-AU'),when=s=>new Date(s+'T12:00:00Z').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
 $('#support-values').hidden=summary.state!=='available';
 $('#support-state').textContent=summary.state==='available'?`${retained?'Last validated support context':'Recorded support context'} · ${when(summary.snapshotDate)}`:'Support context unavailable';
 $('#support-note').textContent=summary.state==='available'?`${fmt(summary.eitherSupport)} of ${fmt(summary.denominator)} active accounts in either support group at this snapshot. Groups may overlap. Historical synthetic records; account activity stays tied to this date.`:summary.reason;
 if(summary.state==='available'){
  $('#support-arrangements').textContent=fmt(summary.paymentArrangements);$('#support-hardship').textContent=fmt(summary.hardshipPrograms);$('#support-either').textContent=fmt(summary.eitherSupport);
  $('#support-grants').textContent=`${fmt(summary.paidGrantCount)} paid grant records · ${fmt(summary.grantRecipients)} recipients in the retained cohort`;
  $('#support-grant-amount').textContent=new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',maximumFractionDigits:2}).format(summary.paidGrantAmountCents/100);
  $('#support-period').textContent=`${when(summary.historyStart)} – ${when(summary.historyEnd)}. Recorded payments, not future assistance or eligibility.`;
 }
 return summary;
}
