import {cell} from '../grid.mjs';
export function nearestNativeCell(data,lon,lat){if(!data)return cell(lon,lat);const closest=(axis,v)=>axis.reduce((a,b)=>Math.abs(b-v)<Math.abs(a-v)?b:a);return cell(closest(data.longitudes,lon),closest(data.latitudes,lat));}
export function cellContainsPoint(feature,point){const {lon,lat}=feature.properties;return point[0]>=lon-.5&&point[0]<lon+.5&&point[1]>=lat-.5&&point[1]<lat+.5;}
export function nativeMeanGrid(data,index){const f=data.fields[index];return {type:'FeatureCollection',features:data.latitudes.flatMap((lat,y)=>data.longitudes.map((lon,x)=>{const feature=cell(lon,lat);feature.properties.valueC=f.valuesC[y][x];return feature;}))};}
export function mappedArea(business,selected,preferred,hasForecast=true){
 if(!business)return;
 const requested=business.areas.find(a=>a.postcode===preferred&&(!hasForecast||cellContainsPoint(selected,a.referencePoint)));if(preferred)return requested;
 const {lon,lat}=selected.properties;return hasForecast?business.areas.filter(a=>cellContainsPoint(selected,a.referencePoint)).sort((a,b)=>(a.referencePoint[0]-lon)**2+(a.referencePoint[1]-lat)**2-((b.referencePoint[0]-lon)**2+(b.referencePoint[1]-lat)**2))[0]:undefined;
}
export function historicalPoint(history,selected,preferred,hasForecast=true){
 if(!history)return;
 const {lon,lat}=selected.properties,points=history.points.filter(p=>hasForecast?cellContainsPoint(selected,[p.lon,p.lat]):p.postcode===preferred);
 return points.find(p=>p.postcode===preferred)||points.sort((a,b)=>(a.lon-lon)**2+(a.lat-lat)**2-((b.lon-lon)**2+(b.lat-lat)**2))[0];
}
export function selectedSeries(data,selected,key='valuesC'){const y=data.latitudes.indexOf(selected.properties.lat),x=data.longitudes.indexOf(selected.properties.lon);return data.fields.map(f=>f[key]?.[y]?.[x]??null);}
