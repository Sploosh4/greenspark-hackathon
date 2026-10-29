// Point coverage is explicit. A future verified historical raster gets its own adapter.
export function historicalFeatures(history){
 return {type:'FeatureCollection',features:history.points.map(p=>({type:'Feature',properties:{name:p.name,postcode:p.postcode,baseline:history.baseline,statistic:'Calendar-month mean daily high and low',units:'degC'},geometry:{type:'Point',coordinates:[p.lon,p.lat]}}))};
}
export function addHistoricalLayer(map,points,before){
 if(map.getSource('historical-points'))map.getSource('historical-points').setData(points);
 else{
  map.addSource('historical-points',{type:'geojson',data:points});
  map.addLayer({id:'historical-samples',type:'circle',source:'historical-points',paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,4.5,8,7],'circle-color':'#79558c','circle-opacity':.85,'circle-stroke-width':1.5,'circle-stroke-color':'#ffffff'}},before);
 }
}
export function setHistoricalVisibility(map,visible){
 if(map.getLayer('historical-samples'))map.setLayoutProperty('historical-samples','visibility',visible?'visible':'none');
}
