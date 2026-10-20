const priorityRank={Urgent:0,High:1,Review:2};
export const customerKey=row=>[row.retailer,row.customer].map(encodeURIComponent).join(':');
const compareFlags=(a,b)=>(priorityRank[a.priority]??3)-(priorityRank[b.priority]??3)||a.dueDay-b.dueDay||a.id.localeCompare(b.id);

export function groupCustomerFlags(rows){
  const groups=new Map();
  for(const row of rows.flatMap(r=>r.flags||[r])){
    const key=customerKey(row);
    if(!groups.has(key))groups.set(key,new Map());
    groups.get(key).set(row.id,row);
  }
  return [...groups].map(([key,found])=>{
    const flags=[...found.values()].sort(compareFlags),primary=flags[0];
    const consent=flags.some(f=>f.consent==='no')?'no':flags.every(f=>f.consent==='yes')?'yes':'not_asked';
    const sameChannel=flags.every(f=>f.channel===primary.channel);
    return {...primary,id:key,flags,consent,eligible:consent==='yes'&&sameChannel&&flags.every(f=>f.eligible===true),channel:sameChannel?primary.channel:'Review',lifeSupport:flags.some(f=>f.lifeSupport===true),dueDay:Math.min(...flags.map(f=>f.dueDay))};
  });
}

export function filterCustomerGroups(groups,filters={}){
  const {extension=null,priority='all',search='',day=null,sort=false}=filters;
  const query=search.trim().toLowerCase();
  return groups.filter(r=>r.flags.some(f=>(!extension||f.extension===extension)&&(day===null||f.dueDay===day))&&(priority==='all'||r.priority===priority)&&(!query||`${r.customer} ${r.region} ${r.locality} ${r.flags.map(f=>f.id).join(' ')}`.toLowerCase().includes(query))).sort((a,b)=>sort?a.customer.localeCompare(b.customer):compareFlags(a,b));
}

export function migratePreparedKeys(prepared,rawCases){
  const byId=new Map(rawCases.map(r=>[r.id,customerKey(r)]));
  return new Set([...prepared].map(id=>byId.get(id)||id));
}

export function outreachCandidates(rows,prepared){
  return groupCustomerFlags(rows).filter(r=>r.eligible&&!prepared.has(r.id));
}

export function customerExportRows(rows,{handoff=false,labelFor,messageFor,prepared=new Set()}={}){
  return groupCustomerFlags(rows).map(r=>{
    const ids=r.flags.map(f=>f.id).join(' | '),signals=[...new Set(r.flags.map(f=>labelFor(f.extension)))].join(' | ');
    const details=r.flags.map(f=>`${labelFor(f.extension)}: ${f.detail}`).join(' | ');
    return handoff?[ids,r.customer,r.retailer,r.region,r.channel,signals,details,messageFor(r)]:[ids,r.customer,r.retailer,r.region,signals,r.priority,details,r.consent,prepared.has(r.id)?'Prepared':'Open'];
  });
}
