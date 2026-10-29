import {installFinancialIntake} from './financial-intake.mjs';
import {waitForValidation} from './modules/upload-validation.mjs';
import {authenticatedFetch,installSessionControl} from './modules/session.mjs';
import {createSnapshotReader} from './modules/source-adapter.mjs';
const $=s=>document.querySelector(s),reader=createSnapshotReader();let staged=null,current=null,pendingJob=null;
const fmt=v=>Number(v).toLocaleString('en-AU');
const when=s=>new Date(s+'T12:00:00Z').toLocaleDateString('en-AU',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
const errors={active_snapshot_changed_restage_required:'The active snapshot changed. Discard this stage and review a new one.',stage_missing_or_expired:'This stage expired or the server restarted. Stage the files again.',unsupported_or_mismatched_locality:'A postcode/locality does not match the 387 supported locality references.',csv_headers_must_match_reviewed_schema:'The CSV columns must match the reviewed source schema exactly.',future_usage_observation:'Usage contains a future observation date.',trusted_upload_context_unavailable:'The trusted mapping context is unavailable. Current map data is retained; repair the source context before uploading.',upload_or_storage_failed_previous_data_retained:'The upload or save failed. The previous active data has been retained.'};
function message(text,error=false){$('#status').textContent=text;$('#status').dataset.error=String(error);}
function busy(value){for(const id of ['stage','replace','discard'])$( '#'+id).disabled=value||id==='stage'&&(!current||!!pendingJob);}
async function post(path,body){const response=await authenticatedFetch('/api/q3/business/'+path,{method:'POST',body,headers:body instanceof FormData?{}:{'Content-Type':'application/json'}});const result=await response.json();if(!response.ok)throw Error(errors[result.error]||`Validation stopped: ${(result.error||'request_failed').replaceAll('_',' ')}. Current data is unchanged.`);return result;}
async function load(){const packet=await reader.read();current=packet.data?.business||null;$('#current').textContent=current?`${fmt(current.totalAccounts)} active accounts · ${when(current.snapshotDate)} · ${current.areas.length} mapped areas${packet.status.last_refresh_error?' · Last good data; source check failed':''}`:'No validated current snapshot. Upload is unavailable.';$('#stage').disabled=!current;financialIntake.update(packet);}
function showStage(s){
 staged=s;$('#review').hidden=false;$('#summary').replaceChildren();
 for(const [label,value] of [['Active accounts',fmt(s.proposed.totalAccounts)],['Retained records',fmt(s.proposed.retainedTotalAccounts)],['Closed',fmt(s.proposed.closedAccounts)],['Unknown / excluded',fmt(s.proposed.unknownStatusAccounts)],['Not open at snapshot',fmt(s.proposed.notOpenAtSnapshotAccounts||0)]]){const block=document.createElement('div'),strong=document.createElement('strong');strong.textContent=value;block.append(strong,document.createTextNode(label));$('#summary').append(block);}
 $('#evidence').textContent=`Proposed: ${when(s.proposed.snapshotDate)}. Current: ${when(s.previous.snapshotDate)}. Validated ${fmt(s.validation.customerRows)} customer rows and ${fmt(s.validation.usageRows)} usage rows. Stage expires ${new Date(s.expiresAt).toLocaleTimeString('en-AU')}.`;
 $('#differences').replaceChildren(...s.differences.map(a=>{const row=document.createElement('tr');for(const value of [`${a.name} · ${a.postcode}`,a.before===null?'Unavailable':fmt(a.before),a.after===null?'Unavailable':fmt(a.after),a.before===null||a.after===null?'—':`${a.after-a.before>0?'+':''}${a.after-a.before}`]){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}return row;}));
 $('#review').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});$('#replace').focus({preventScroll:true});
}
$('#upload').onsubmit=async e=>{
 e.preventDefault();if(pendingJob){message('Use Check validation status for the accepted files. Current data is unchanged.',true);return;}if(staged){message('Discard the existing stage before staging another pair.',true);return;}
 const customers=$('#customers').files[0],usage=$('#usage').files[0];
 if(!customers||!usage||!$('#synthetic').checked)return;
 if(customers.size+usage.size>16*1024*1024-8192){message('The combined files exceed the 16 MiB upload limit.',true);return;}
 const body=new FormData();body.set('customers',customers);body.set('usage',usage);body.set('synthetic','true');busy(true);message('Uploading both files. Current map data is unchanged…');
 try{const receipt=await post('stage',body);if(receipt.state!=='accepted'||!receipt.jobId)throw Error('Upload receipt unavailable. Inspect the current validation before retrying.');pendingJob=receipt.jobId;$('#customers').value='';$('#usage').value='';message('Files received. Validating in the background; current data is unchanged…');await finishValidation();}
 catch(error){message(error.message,true);}finally{busy(false);}
};
async function finishValidation(){
 if(!pendingJob)return;
 $('#resume-validation').hidden=true;
 try{const proposal=await waitForValidation(pendingJob);pendingJob=null;showStage(proposal);message('Validation passed. Review the dated totals, then choose Replace to make them active.');}
 catch(error){if(error.receiptExpired){pendingJob=null;message('This receipt expired or the server restarted. Current data is unchanged. Choose the files and stage them again.',true);}else if(error.validationFailed){pendingJob=null;message(errors[error.message]||`Validation stopped: ${error.message.replaceAll('_',' ')}. Current data is unchanged.`,true);}else{$('#resume-validation').hidden=false;message(error.message+' Use Check validation status for the received files.',true);}}
}
$('#resume-validation').onclick=async()=>{busy(true);try{await finishValidation();}finally{busy(false);}};
$('#replace').onclick=async()=>{
 if(!staged)return;busy(true);message('Saving the validated replacement…');
 try{await post('replace',JSON.stringify({stageId:staged.stageId,baseGeneration:staged.baseGeneration}));staged=null;$('#review').hidden=true;await load();message('Business data replaced. Open the map and choose Refresh local data in Forecast details to load this snapshot.');}
 catch(error){message(error.message,true);}finally{busy(false);}
};
$('#discard').onclick=async()=>{if(!staged)return;busy(true);try{await post('discard',JSON.stringify({stageId:staged.stageId}));staged=null;$('#review').hidden=true;message('Stage discarded. Current data is unchanged.');}catch(error){message(error.message,true);}finally{busy(false);}};
const financialIntake=installFinancialIntake({reload:load});
load();

installSessionControl();
