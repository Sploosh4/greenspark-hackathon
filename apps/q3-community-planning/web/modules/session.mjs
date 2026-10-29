// Session tokens stay in HttpOnly cookies. Only the per-session CSRF is read here.
export async function session(){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
 try{const response=await fetch('/api/session',{cache:'no-store',credentials:'same-origin',signal:controller.signal});if(!response.ok)throw Error('Sign in required');return await response.json();}finally{clearTimeout(timer);}
}
export async function authenticatedFetch(url,options={}){
 const headers=new Headers(options.headers||{}),method=(options.method||'GET').toUpperCase();
 if(!['GET','HEAD'].includes(method)){const current=await session();if(current.enforcementConfigured===false&&current.mode==='local-preview'){}else if(current.authenticated&&current.role==='manager'&&current.csrf_token)headers.set('X-Team-Connect-CSRF',current.csrf_token);else throw Error('Sign in required');}
 return fetch(url,{...options,headers,credentials:'same-origin'});
}

export async function installSessionControl(){
 try{const current=await session();if(!current.authenticated)return;const button=document.querySelector('#sign-out');if(button){button.hidden=false;button.textContent='Sign out';button.onclick=async()=>{button.disabled=true;try{const r=await authenticatedFetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(r.ok)location.assign('/auth/login');else button.disabled=false;}catch(error){button.disabled=false;}};}const note=document.querySelector('#auth-workflow-note');if(note)note.textContent='Manager-only server session. Replacement remains local and atomic; failed validation or save retains the last good snapshot.';}catch(error){}
}
