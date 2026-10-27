// Strict POA2021 data join, reused from the reviewed cloud boundary handoff.
const SPECIAL_CODES=new Set(['9494','9797']);
export function poa2021Code(context){
  if(context?.context_geography!=='POA2021'||String(context.census_reference_year)!=='2021')return null;
  const key=context.POA_CODE_2021;
  if(typeof key!=='string'||!/^POA[0-9]{4}$/.test(key))return null;
  const code=key.slice(3);
  return context.postcode===code&&!SPECIAL_CODES.has(code)?code:null;
}
export function validAreaGeometry(geometry){
  if(!geometry||!['Polygon','MultiPolygon'].includes(geometry.type))return false;
  const polygons=geometry.type==='Polygon'?[geometry.coordinates]:geometry.coordinates;
  if(!Array.isArray(polygons)||!polygons.length)return false;
  return polygons.every(polygon=>Array.isArray(polygon)&&polygon.length&&polygon.every(ring=>{
    if(!Array.isArray(ring)||ring.length<4)return false;
    if(!ring.every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&p[0]>=-180&&p[0]<=180&&p[1]>=-90&&p[1]<=90))return false;
    const first=ring[0],last=ring.at(-1);
    if(first[0]!==last[0]||first[1]!==last[1])return false;
    let area=0;for(let i=1;i<ring.length;i++)area+=ring[i-1][0]*ring[i][1]-ring[i][0]*ring[i-1][1];
    return Math.abs(area)>1e-12;
  }));
}
export function findPoa2021Boundary(context,collection){
  const code=poa2021Code(context);
  if(!code||collection?.type!=='FeatureCollection'||collection.geography!=='POA2021'||collection.reference_year!==2021||!Array.isArray(collection.features))return null;
  const matches=collection.features.filter(f=>f?.properties?.poa_code_2021===code);
  if(matches.length!==1)return null;
  const feature=matches[0];
  return feature.type==='Feature'&&validAreaGeometry(feature.geometry)?feature:null;
}
export function joinPoa2021Contexts(contexts,collection){
  if(!Array.isArray(contexts))return [];
  const counts=new Map();
  for(const context of contexts){const code=poa2021Code(context);if(code)counts.set(code,(counts.get(code)||0)+1);}
  return contexts.flatMap(context=>{
    const code=poa2021Code(context),boundary=findPoa2021Boundary(context,collection);
    return code&&counts.get(code)===1&&boundary?[{context,boundary}]:[];
  });
}
