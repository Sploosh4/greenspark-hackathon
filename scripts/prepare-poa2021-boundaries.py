"""Prepare only the official POA2021 geometries matching the existing statistics.
No application or key configuration is changed. Standard library only.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
SERVICE='https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/POA/MapServer/1'
SOURCE_FIELD='poa_code_2021'
ATTRIBUTION='Australian Bureau of Statistics, ASGS Edition 3, Postal Areas 2021. © Commonwealth of Australia. CC BY 4.0.'
LICENSE='https://creativecommons.org/licenses/by/4.0/'
SPECIAL_CODES={'9494','9797'}

def digest(payload):return hashlib.sha256(payload).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def context_codes(contexts):
    codes=[]
    for row in contexts:
        key=row.get('POA_CODE_2021','')
        if row.get('context_geography')!='POA2021' or str(row.get('census_reference_year'))!='2021' or not isinstance(key,str) or not re.fullmatch(r'POA[0-9]{4}',key):
            raise ValueError('Statistics must explicitly identify POA2021 and Census year 2021')
        code=key[3:]
        if row.get('postcode')!=code or code in SPECIAL_CODES:raise ValueError('Invalid or non-spatial postcode key')
        codes.append(code)
    if not codes or len(set(codes))!=len(codes):raise ValueError('Statistics must have nonempty unique POA2021 keys')
    return sorted(codes)

def query_parameters(codes):
    if not codes or any(not isinstance(c,str) or not re.fullmatch(r'[0-9]{4}',c) or c in SPECIAL_CODES for c in codes):raise ValueError('Only explicit four-digit spatial POA codes may be queried')
    return {'where':SOURCE_FIELD+' IN ('+','.join("'"+c+"'" for c in sorted(set(codes)))+')','outFields':'poa_code_2021,poa_name_2021','returnGeometry':'true','outSR':'4326','orderByFields':SOURCE_FIELD,'f':'geojson'}

def validate_geometry(geometry):
    if not isinstance(geometry,dict) or geometry.get('type') not in ['Polygon','MultiPolygon']:raise ValueError('Only Polygon/MultiPolygon geometry is accepted')
    polygons=[geometry.get('coordinates')] if geometry['type']=='Polygon' else geometry.get('coordinates')
    if not isinstance(polygons,list) or not polygons:raise ValueError('Empty polygon geometry')
    for polygon in polygons:
        if not isinstance(polygon,list) or not polygon:raise ValueError('Empty polygon rings')
        for ring in polygon:
            if not isinstance(ring,list) or len(ring)<4:raise ValueError('Polygon ring must have at least four coordinates')
            for point in ring:
                if not isinstance(point,list) or len(point)!=2 or not all(type(v) in [float,int] and math.isfinite(v) for v in point) or not -180<=point[0]<=180 or not -90<=point[1]<=90:
                    raise ValueError('Geometry must use finite longitude/latitude coordinates in EPSG:4326')
            if ring[0]!=ring[-1]:raise ValueError('Polygon rings must be closed')
            area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]))
            if abs(area)<=1e-12:raise ValueError('Degenerate polygon ring')

def prepare(source,contexts):
    codes=context_codes(contexts)
    if source.get('type')!='FeatureCollection' or not isinstance(source.get('features'),list) or source.get('exceededTransferLimit'):
        raise ValueError('Expected a complete official GeoJSON FeatureCollection')
    if 'reference_year' in source and source['reference_year']!=2021:raise ValueError('Wrong boundary reference year')
    if 'geography' in source and source['geography']!='POA2021':raise ValueError('Wrong boundary geography')
    crs=source.get('crs',{}).get('properties',{}).get('name')
    if crs not in [None,'EPSG:4326','urn:ogc:def:crs:EPSG::4326','urn:ogc:def:crs:OGC:1.3:CRS84']:raise ValueError('Re-export source using outSR=4326; projected coordinates are not transformed here')
    selected={}
    for feature in source['features']:
        code=feature.get('properties',{}).get(SOURCE_FIELD)
        if code not in codes:continue
        if code in selected:raise ValueError('Duplicate source boundary key: '+code)
        if feature.get('type')!='Feature':raise ValueError('Invalid GeoJSON Feature')
        validate_geometry(feature.get('geometry'))
        # Preserve all source coordinates, islands and holes; do not clip or simplify.
        selected[code]={'type':'Feature','id':'POA'+code,'properties':{'poa_code_2021':code,'poa_name_2021':feature['properties'].get('poa_name_2021',code)},'geometry':feature['geometry']}
    missing=sorted(set(codes)-set(selected))
    if missing:raise ValueError('Missing source geometry for: '+','.join(missing))
    return {'type':'FeatureCollection','geography':'POA2021','reference_year':2021,'attribution':ATTRIBUTION,'license':LICENSE,'features':[selected[c] for c in codes]}

def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--download',action='store_true',help='Fetch a public subset directly from the fixed official ABS service')
    mode.add_argument('--source',type=Path,help='Existing GeoJSON export from the exact official service; operator must verify its provenance')
    p.add_argument('--scenario',type=Path,default=ROOT/'teamconnect/scenario.json');p.add_argument('--out',type=Path,default=ROOT/'teamconnect/geography');a=p.parse_args()
    scenario_bytes=a.scenario.read_bytes();contexts=json.loads(scenario_bytes)['context'];codes=context_codes(contexts)
    url=SERVICE+'/query?'+urlencode(query_parameters(codes))
    if a.download:
        with urlopen(url,timeout=60) as response:raw=response.read()
        acquisition='direct HTTPS download from official ABS service'
    else:
        raw=a.source.read_bytes();acquisition='operator-supplied export; origin not independently verified by this script'
    result=prepare(json.loads(raw),contexts);payload=encoded(result)
    manifest={'source_service':SERVICE,'source_query_url':url,'source_layer':'POA_GEN','source_field':SOURCE_FIELD,'geography':'POA2021','reference_year':2021,'output_crs':'EPSG:4326','acquisition':acquisition,'prepared_at_utc':datetime.now(timezone.utc).isoformat(),'raw_source_sha256':digest(raw),'scenario_sha256':digest(scenario_bytes),'statistics_sha256':digest(encoded(contexts)),'output_sha256':digest(payload),'matched_codes':codes,'feature_count':len(result['features']),'attribution':ATTRIBUTION,'license':LICENSE,'transformations':['Subset to exact 2021 statistics codes','Retain source Polygon/MultiPolygon coordinates, rings and holes','Drop unrelated source properties; retain official code/name'],'limitations':['Statistical Postal Areas, not town or legal boundaries','No Census or SEIFA value is allocated to a smaller area','Geometry structural validation does not authenticate source provenance or prove topology']}
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'poa2021.geojson').write_bytes(payload)
    (a.out/'poa2021.provenance.json').write_bytes(encoded(manifest))
    print(json.dumps({'features':len(result['features']),'matched_codes':codes,'output_sha256':manifest['output_sha256'],'acquisition':acquisition},indent=2))

if __name__=='__main__':main()
