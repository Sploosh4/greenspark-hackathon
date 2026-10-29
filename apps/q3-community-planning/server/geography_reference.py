"""Pinned public reference geometry; never supplied by an upload client."""
from functools import lru_cache
from pathlib import Path
import copy
from source_adapter import SourceError,require,digest,parse
GEOGRAPHY_SHA='ecf0e7dc32e73eea517dd3c0a3706f96441fcba1d82c98fa49ecee50276d69de'
@lru_cache(maxsize=1)
def registry():
 raw=(Path(__file__).resolve().parents[1]/'data/geography/reference.json').read_bytes();require(digest(raw)==GEOGRAPHY_SHA,'trusted_geography_hash')
 d=parse(raw.decode());require(d.get('schema')=='q3-trusted-business-geography-v1' and len(d.get('areas',[]))==387 and d.get('boundary',{}).get('checkedInside')==386,'trusted_geography_contract');return d
def reference_points(business,legacy_points):
 if business.get('geographyRegistrySha256') is None:return legacy_points
 require(business['geographyRegistrySha256']==GEOGRAPHY_SHA,'business_geography_version')
 return [{'postcode':a['postcode'],'name':a['name'],'lon':a['referencePoint'][0],'lat':a['referencePoint'][1]} for a in registry()['areas']]
def extend_trusted_context(seed):
 if seed is None:return None
 d=registry();old={a['postcode']:a for a in seed['areas']};result=copy.deepcopy(seed);areas=[]
 for ref in d['areas']:
  pc=ref['postcode']
  if pc in old:
   area=copy.deepcopy(old[pc]);require(area['name']==ref['name'] and area['referencePoint']==ref['referencePoint'],'legacy_reference_changed')
  else:
   area={'postcode':pc,'name':ref['name'],'referencePoint':ref['referencePoint'],'referencePointSource':ref['referencePointSource'],'financialContext':None,'accountCount':0,'prepaidAccounts':0,'billedAccounts':0,'retainedAccountCount':0,'closedAccounts':0,'unknownStatusAccounts':0}
  area['sourceRecordId']=ref['sourceRecordId'];areas.append(area)
 result['areas']=areas;result['geographyRegistrySha256']=GEOGRAPHY_SHA;result['geographySource']=d['source'];result['geographyMeaning']=d['meaning'];return result
