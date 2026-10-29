import {authenticatedFetch} from './modules/session.mjs';
import {waitForValidation} from './modules/upload-validation.mjs';
import {financialSummary,validateFinancialSupport} from './modules/financial-support.mjs';
const names={customers:'customers.csv',usage:'consumption_daily.csv.gz',manifest:'manifest.json',arrangements:'payment_arrangements.csv.gz',hardship:'hardship_programs.csv.gz',grants:'hugs_grants.csv.gz',support:'support_arrangement_history.csv.gz',payments:'payments.csv.gz'};
const messages={unreviewed_financial_manifest:'This financial package has not been reviewed for this prototype.',financial_cohort_mismatch:'The files do not match the active account source.',financial_snapshot_mismatch:'The financial dates do not match the active account snapshot.',financial_coverage_mismatch:'Financial coverage does not match the account areas.',financial_source_hash_mismatch:'A source file differs from its reviewed manifest.',support_parent_history_incomplete:'Support history is incomplete. Missing intervals cannot be counted as zero.',active_snapshot_changed_restage_required:'The active source changed. Discard this proposal and stage the matching files again.',another_validation_in_progress:'Another validation is running. Current data is unchanged.',financial_aggregate_integrity:'The proposed aggregate differs from the reviewed source evidence.'};

export function installFinancialIntake({reload,lookup=s=>document.querySelector(s)}={}){
 const $=lookup;let packet=null,pending=null,staged=null,working=false;
 const message=(text,error=false)=>{$('#financial-status').textContent=text;$('#financial-status').dataset.error=String(error);};
 const fmt=n=>n.toLocaleString('en-AU');
 function controls(){
  $('#financial-stage').disabled=working||!packet?.data?.business||!!pending||!!staged;
  $('#financial-replace').disabled=working||!staged||!!staged.unusable||staged.baseGeneration!==packet?.generation;
  $('#financial-discard').disabled=working||!staged;
  $('#financial-resume').disabled=working;
 }
 async function post(path,body){
  const r=await authenticatedFetch('/api/q3/financial/'+path,{method:'POST',body,headers:body instanceof FormData?{}:{'Content-Type':'application/json'}});const p=await r.json();
  if(!r.ok)throw Error(messages[p.error]||`Financial validation stopped: ${(p.error||'request_failed').replaceAll('_',' ')}. Current data is unchanged.`);
  return p;
 }
 function update(next){
  packet=next;const b=next?.data?.business,s=b&&financialSummary(b);
  $('#financial-current').textContent=s?.state==='available'?`Validated support context · ${s.snapshotDate} · ${fmt(s.coveredAreas)} covered areas · ${fmt(s.eitherSupport)} active accounts in either support group.`:s?.reason||'No validated account source. Financial upload is unavailable.';
  if(staged&&staged.baseGeneration!==next?.generation)message('The active source changed. Discard this proposal and stage the matching files again.',true);
  controls();
 }
 function show(s){
  validateFinancialSupport(s.proposedSupport,packet.data.business);staged=s;
  const b={...packet.data.business,financialSupport:s.proposedSupport},summary=financialSummary(b);
  $('#financial-summary').textContent=`${fmt(summary.paymentArrangements)} arrangement accounts · ${fmt(summary.hardshipPrograms)} hardship accounts · ${fmt(summary.eitherSupport)} in either group`;
  $('#financial-evidence').textContent=`Snapshot ${summary.snapshotDate}. Recorded grant period ${summary.historyStart} to ${summary.historyEnd}: ${fmt(summary.paidGrantCount)} paid grants. ${fmt(s.areaCount)} account areas matched. Raw rows are not saved.`;
  $('#financial-differences').replaceChildren(...s.proposedSupport.areas.map(a=>{const tr=document.createElement('tr');const area=packet.data.business.areas.find(x=>x.postcode===a.postcode);for(const value of [`${area.name} · ${a.postcode}`,a.activePaymentArrangementAccounts,a.activeHardshipProgramAccounts,a.activeAccountsInEitherSupport]){const td=document.createElement('td');td.textContent=typeof value==='number'?fmt(value):value;tr.append(td);}return tr;}));
  $('#financial-review').hidden=false;$('#financial-review').scrollIntoView({block:'start',behavior:'auto'});$('#financial-replace').focus({preventScroll:true});
 }
 function showUnusable(proposal,reason){
  pending=null;staged={stageId:proposal.stageId,baseGeneration:proposal.baseGeneration,unusable:true};
  $('#financial-resume').hidden=true;$('#financial-review').hidden=false;
  $('#financial-summary').textContent='This proposal cannot be applied.';
  $('#financial-evidence').textContent='No support counts from this proposal have been attached. Discard it before staging the matching source.';
  $('#financial-differences').replaceChildren();message(reason,true);
 }
 async function finish(){
  $('#financial-resume').hidden=true;
  try{const proposal=await waitForValidation(pending,{kind:'financial'});
   if(proposal.baseGeneration!==packet?.generation){showUnusable(proposal,'The account source changed during validation. Discard this proposal and stage the matching files again.');return;}
   try{show(proposal);}catch(error){showUnusable(proposal,'The returned support proposal could not be validated. Discard it and inspect the matching source.');return;}
   pending=null;message('Validation passed. Review the dated support counts before choosing Replace.');}
  catch(error){if(error.receiptExpired){pending=null;message('The receipt expired or the server restarted. Current data is unchanged; choose the files and stage again.',true);}else if(error.validationFailed){pending=null;message(messages[error.message]||`Financial validation stopped: ${error.message.replaceAll('_',' ')}. Current data is unchanged.`,true);}else{$('#financial-resume').hidden=false;message(error.message+' Check this receipt rather than uploading again.',true);}}
 }
 $('#financial-upload').onsubmit=async e=>{
  e.preventDefault();if(pending||staged||!packet?.data)return;
  const files=Array.from($('#financial-files').files),expected=Object.values(names);
  if(files.length!==8||new Set(files.map(f=>f.name)).size!==8||files.some(f=>!expected.includes(f.name))){message('Choose exactly the eight named files once each. No partial package can be staged.',true);return;}
  if(!$('#financial-synthetic').checked)return;
  if(files.reduce((n,f)=>n+f.size,0)>32*1024*1024-16384){message('The package exceeds the separate 32 MiB request limit.',true);return;}
  const body=new FormData();for(const [key,name]of Object.entries(names))body.set(key,files.find(f=>f.name===name));body.set('synthetic','true');body.set('baseGeneration',packet.generation);working=true;controls();message('Uploading the matching financial package. Current context is unchanged…');
  try{const r=await post('stage',body);if(r.state!=='accepted'||!r.jobId)throw Error('Receipt unavailable. Inspect the current validation before retrying.');pending=r.jobId;$('#financial-files').value='';message('Files received. Financial validation is running; current context is unchanged.');await finish();}
  catch(error){message(error.message,true);}finally{working=false;controls();}
 };
 $('#financial-resume').onclick=async()=>{if(!pending)return;working=true;controls();try{await finish();}finally{working=false;controls();}};
 $('#financial-replace').onclick=async()=>{
  if(!staged||staged.unusable||staged.baseGeneration!==packet?.generation)return;working=true;controls();message('Saving the validated support context…');
  try{await post('replace',JSON.stringify({stageId:staged.stageId,baseGeneration:staged.baseGeneration}));staged=null;$('#financial-review').hidden=true;await reload();message('Support context replaced. Refresh local data on the map, then enable Financial context.');}
  catch(error){message(error.message,true);}finally{working=false;controls();}
 };
 $('#financial-discard').onclick=async()=>{if(!staged)return;working=true;controls();try{await post('discard',JSON.stringify({stageId:staged.stageId}));staged=null;$('#financial-review').hidden=true;message('Financial stage discarded. Current context is unchanged.');}catch(error){message(error.message,true);}finally{working=false;controls();}};
 controls();return {update};
}
