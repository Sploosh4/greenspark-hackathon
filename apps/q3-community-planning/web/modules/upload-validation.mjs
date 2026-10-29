// A receipt means accepted bytes, never a passed validation or active replacement.
export async function waitForValidation(jobId,{fetcher=fetch,pause=ms=>new Promise(r=>setTimeout(r,ms)),now=()=>performance.now(),timeoutMs=120000,requestTimeoutMs=8000,onState=()=>{},kind='business'}={}){
 if(!['business','financial'].includes(kind))throw Error('Unknown validation workflow');
 const resultField=kind==='financial'?'proposedSupport':'proposed';
 if(typeof jobId!=='string'||!/^[A-Za-z0-9_-]{32}$/.test(jobId))throw Error('Invalid validation receipt. Current data is unchanged.');
 const start=now();
 while(now()-start<timeoutMs){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),requestTimeoutMs);let p;
  try{const response=await fetcher('/api/q3/'+kind+'/stage-status?id='+encodeURIComponent(jobId),{cache:'no-store',credentials:'same-origin',signal:controller.signal});p=await response.json();if(!response.ok){const error=Error(p.error||'Validation status unavailable');error.receiptExpired=p.error==='validation_receipt_missing_or_expired';throw error;}}
  finally{clearTimeout(timer);}
  if(p.jobId!==jobId)throw Error('Validation receipt mismatch. Current data is unchanged.');
  onState(p.state);
  if(p.state==='ready'){if(!p.result?.stageId||!p.result?.[resultField])throw Error('Invalid validated proposal. Current data is unchanged.');return p.result;}
  if(p.state==='failed'){const error=Error(p.error||'validation_failed_previous_data_retained');error.validationFailed=true;throw error;}
  if(!['accepted','validating'].includes(p.state))throw Error('Unknown validation state. Current data is unchanged.');
  await pause(500);
 }
 throw Error('Validation is still pending. Use Check validation status; do not upload the files again. Current data is unchanged.');
}
