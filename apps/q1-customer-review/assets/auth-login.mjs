const form=document.querySelector('#sign-in'),status=document.querySelector('#status');
let csrf='';
async function challenge(){
 const r=await fetch('/api/auth/challenge',{credentials:'same-origin'}),value=await r.json();
 if(!r.ok)throw Error(value.error||'Local sign-in unavailable');csrf=value.csrf_token;
 for(const input of form.elements)input.disabled=false;
}
form.onsubmit=async event=>{
 event.preventDefault();const button=form.querySelector('button');button.disabled=true;
 try{
  const r=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Team-Connect-CSRF':csrf},body:JSON.stringify({username:form.elements.username.value,password:form.elements.password.value})}),value=await r.json();
  form.elements.password.value='';if(!r.ok)throw Error(value.error||'Sign-in failed');location.assign('/');
 }catch(error){status.textContent=error.message;try{await challenge();}catch(next){status.textContent=next.message;}}
};
try{await challenge();status.textContent='Use your approved local Q1 account.';}catch(error){status.textContent=error.message;}
