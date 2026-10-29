"""Pin the verified public registry and retain the 12 reviewed reference points."""
import argparse,csv,hashlib,json,zipfile
from pathlib import Path
from shapely.geometry import shape,Point
CSV_HASH='22638f591b169d21018e51ac84bac7ce4a385cd90424b9d25ce03818e017797b'
ZIP_HASH='b26c17893b88e34c682f4bba10748e3d37b003589f3e89636e32c68c8dc14f59'
TXT_HASH='4f3f536f27176acb6c80510052fd55ba1efd55f9ac77d412131658a105384656'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('references',type=Path);p.add_argument('wa_boundary',type=Path);p.add_argument('app',type=Path);a=p.parse_args();r=a.references
 raw=(r/'wa-reference-localities.csv').read_bytes();assert sha(raw)==CSV_HASH;assert sha((r/'geonames-AU.zip').read_bytes())==ZIP_HASH
 with zipfile.ZipFile(r/'geonames-AU.zip') as z:txt=z.read('AU.txt');assert sha(txt)==TXT_HASH
 lines=txt.decode().splitlines();legacy=json.loads((a.app/'data/inputs/q3-area-context.json').read_text());known={x['postcode']:x for x in legacy['areas']}
 boundary=a.wa_boundary.read_bytes();land=shape(json.loads(boundary)['features'][0]['geometry']);areas=[];outside=[]
 for row in csv.DictReader(raw.decode().splitlines()):
  pc=row['postcode'];name=row['locality'];point=[float(row['longitude']),float(row['latitude'])];inside=land.covers(Point(*point))
  if row['source']=='reviewed_Q3_SILO_sample':
   old=known[pc];assert name==old['name'] and point==old['referencePoint'];source='Reviewed Q3 SILO locality reference';source_id='reviewed-silo:'+pc
   if not inside:outside.append(pc);assert pc=='6701'
  else:
   source_row=int(row['source_row']);fields=lines[source_row-1].split('\t');assert fields[0]=='AU' and fields[1]==pc and fields[2]==name and fields[4]=='WA' and fields[11]=='4' and point==[float(fields[10]),float(fields[9])] and inside
   source='GeoNames AU postal locality reference';source_id='AU.txt:line:'+str(source_row)
  areas.append({'postcode':pc,'name':name,'referencePoint':point,'referencePointSource':source,'sourceRecordId':source_id,'insideWaLandBoundary':inside})
 assert len(areas)==387 and len({(x['postcode'],x['name'].casefold()) for x in areas})==387 and len({x['postcode'] for x in areas})==387 and outside==['6701']
 registry={'schema':'q3-trusted-business-geography-v1','source':{'name':'GeoNames AU postal extract and 12 reviewed Q3 SILO reference points','url':'https://download.geonames.org/export/zip/AU.zip','licence':'CC BY 4.0','retrievedAt':'2026-10-28','rawSha256':ZIP_HASH,'rawTextSha256':TXT_HASH,'candidateCsvSha256':CSV_HASH},'boundary':{'source':'ABS ASGS2021 WA state land polygon','url':'https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/STE/MapServer/0','licence':'CC BY 4.0','sha256':sha(boundary),'checkedInside':386,'legacyOutsideExceptions':['6701']},'meaning':'Named approximate locality reference points, not postcode boundaries, customer coordinates or actual retailer coverage. GeoNames is community sourced; no ABS crosswalk is inferred.','areas':areas}
 payload=json.dumps(registry,separators=(',',':')).encode();out=a.app/'data/geography';out.mkdir(parents=True,exist_ok=True);(out/'reference.json').write_bytes(payload)
 h=sha(payload);(a.app/'web/modules/geography-reference.mjs').write_text('export const GEOGRAPHY_SHA='+json.dumps(h)+';\nexport const GEOGRAPHY='+payload.decode()+';\n')
 print(json.dumps({'registrySha256':h,'areas':len(areas),'insideWa':386,'legacyOutsideExceptions':outside}))
if __name__=='__main__':main()
