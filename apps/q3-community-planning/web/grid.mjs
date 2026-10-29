// Geographic geometry only. No seasonal observations, forecasts or probabilities.
export const cell = (lon, lat) => ({type:'Feature',id:`${lon},${lat}`,properties:{lon,lat},geometry:{type:'Polygon',coordinates:[[[lon-.5,lat-.5],[lon+.5,lat-.5],[lon+.5,lat+.5],[lon-.5,lat+.5],[lon-.5,lat-.5]]]}});
export function grid(){const features=[];for(let lon=112;lon<=130;lon++)for(let lat=-36;lat<=-13;lat++)features.push(cell(lon,lat));return {type:'FeatureCollection',features};}
export function dimensions(lat){const r=lat*Math.PI/180;return {width:Math.round(111.320*Math.cos(r)-.0935*Math.cos(3*r)+.00012*Math.cos(5*r)),height:Math.round(111.13295-.55982*Math.cos(2*r)+.001175*Math.cos(4*r))};}
