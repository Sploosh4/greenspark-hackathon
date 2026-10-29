/** Client session lifetime, separate from server authentication/authorization. */
export function createAuthSession({button,fetchImpl,clearData,onError,navigate,reload,lifecycle,logoutDeadlineMs=10000}){
  let active=false,blocked=false,csrf='',epoch=0,pending=null;
  const changed=at=>blocked||at!==epoch;
  function suspend(){blocked=true;epoch++;clearData();}
  function end(){suspend();active=false;csrf='';button.hidden=true;try{navigate('/auth/login');}catch{onError('Signed out. Return to sign-in to continue.');}}
  function activate(token){
    if(blocked)return;
    if(typeof token!=='string'||!token)throw Error('Session protection unavailable');
    active=true;csrf=token;button.hidden=false;
  }
  async function request(input,options){
    if(blocked)throw Error('Session view is closed');
    const at=epoch,response=await fetchImpl(input,options);
    if(changed(at))throw Error('Session view is closed');
    if(active&&response.status===401){end();throw Error('Sign-in required');}
    const body=method=>async()=>{const value=await response[method]();if(changed(at))throw Error('Session view is closed');return value;};
    return {ok:response.ok,status:response.status,headers:response.headers,json:body('json'),arrayBuffer:body('arrayBuffer'),text:body('text'),blob:body('blob')};
  }
  function signOut(){
    if(pending)return pending;
    if(!active)return Promise.resolve();
    button.disabled=true;button.textContent='Signing out…';
    // Hide data while revocation is uncertain too. A failed request allows a
    // retry, never a cached return to protected content or a false success.
    suspend();
    pending=Promise.resolve().then(async()=>{
      const controller=new AbortController();let timer;
      const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Error('Sign out timed out'));},logoutDeadlineMs);});
      try{
        const response=await Promise.race([Promise.resolve().then(()=>fetchImpl('/api/auth/logout',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json','X-Team-Connect-CSRF':csrf},body:'{}',signal:controller.signal})),deadline]);
        if(response.status===401){end();return;}
        if(!response.ok)throw Error('Sign out could not be confirmed. Retry Sign out, or reload this page to check your session.');
        const result=await Promise.race([response.json(),deadline]);
        if(result.authenticated!==false)throw Error('Sign out could not be confirmed. Retry Sign out, or reload this page to check your session.');
        end();
      }catch(error){onError('Sign out could not be confirmed. Retry Sign out, or reload this page to check your session.');}
      finally{clearTimeout(timer);pending=null;button.disabled=false;button.textContent='Sign out';}
    });
    return pending;
  }
  button.hidden=true;button.onclick=signOut;
  lifecycle.addEventListener('pagehide',suspend);
  lifecycle.addEventListener('pageshow',event=>{if(event.persisted){suspend();reload();}});
  return {activate,request,signOut,isBlocked:()=>blocked};
}
