"""Preparation tests use triangles only as temporary test fixtures, never map data."""
import copy,importlib.util,json,unittest,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('prepare_poa',ROOT/'scripts/prepare-poa2021-boundaries.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
CONTEXTS=json.loads((ROOT/'teamconnect/scenario.json').read_text())['context']
CONTEXT=next(r for r in CONTEXTS if r['postcode']=='6722')
RING=[[118,-20],[119,-20],[118,-21],[118,-20]]
def feature(code='6722'):return {'type':'Feature','properties':{'poa_code_2021':code,'poa_name_2021':code},'geometry':{'type':'Polygon','coordinates':[copy.deepcopy(RING)]}}
def collection(features=None):return {'type':'FeatureCollection','features':features if features is not None else [feature()]}

class PreparationChecks(unittest.TestCase):
 def test_exact_twelve_statistic_codes(self):
  self.assertEqual(len(module.context_codes(CONTEXTS)),12)
  self.assertEqual(module.context_codes(CONTEXTS),sorted(r['postcode'] for r in CONTEXTS))
 def test_invalid_statistics_and_duplicates(self):
  for patch in [{'context_geography':'SAL2021'},{'census_reference_year':'2026'},{'POA_CODE_2021':'POA6721'},{'postcode':6722}]:
   with self.assertRaises(ValueError):module.context_codes([{**CONTEXT,**patch}])
  with self.assertRaises(ValueError):module.context_codes([CONTEXT,CONTEXT])
 def test_query_only_public_four_digit_keys_and_fixed_2021_fields(self):
  q=module.query_parameters(['0872','6722']);self.assertEqual(q['where'],"poa_code_2021 IN ('0872','6722')");self.assertEqual(q['outSR'],'4326');self.assertEqual(q['f'],'geojson')
  for code in ["6722' OR 1=1",'POA6722','9494',6722]:
   with self.assertRaises(ValueError):module.query_parameters([code])
 def test_prepare_preserves_geometry_and_originals(self):
  source=collection();hole=[[118.1,-20.1],[118.2,-20.1],[118.1,-20.2],[118.1,-20.1]];source['features'][0]['geometry']['coordinates'].append(hole);before=copy.deepcopy(source)
  output=module.prepare(source,[CONTEXT]);self.assertEqual(source,before);self.assertEqual(output['features'][0]['geometry'],source['features'][0]['geometry']);self.assertEqual(output['reference_year'],2021);self.assertEqual(output['geography'],'POA2021');self.assertNotIn('population',output['features'][0]['properties'])
 def test_reject_missing_duplicate_truncated_and_wrong_geography(self):
  for source in [collection([]),collection([feature(),feature()]),{**collection(),'exceededTransferLimit':True},{**collection(),'reference_year':2026},{**collection(),'geography':'POA2026'},{**collection(),'crs':{'properties':{'name':'EPSG:3857'}}}]:
   with self.assertRaises(ValueError):module.prepare(source,[CONTEXT])
  with tempfile.TemporaryDirectory() as directory:
   source=Path(directory)/'incomplete-test-only.geojson';source.write_text(json.dumps(collection([])));out=Path(directory)/'out'
   result=subprocess.run([sys.executable,str(ROOT/'scripts/prepare-poa2021-boundaries.py'),'--source',str(source),'--out',str(out)],capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0);self.assertFalse(out.exists())
 def test_reject_points_unclosed_degenerate_and_nonfinite(self):
  geometries=[{'type':'Point','coordinates':[118,-20]},{'type':'Polygon','coordinates':[]},{'type':'Polygon','coordinates':[RING[:3]]},{'type':'Polygon','coordinates':[[[118,-20],[119,-20],[120,-20],[118,-20]]]},{'type':'Polygon','coordinates':[[[118,-20],[float('inf'),-20],[118,-21],[118,-20]]]}]
  for geometry in geometries:
   with self.assertRaises(ValueError):module.validate_geometry(geometry)
 def test_complete_subset_matches_all_twelve_without_name_or_spatial_fallback(self):
  source=collection([feature(r['postcode']) for r in CONTEXTS]);output=module.prepare(source,CONTEXTS);self.assertEqual(len(output['features']),12);self.assertEqual([f['properties']['poa_code_2021'] for f in output['features']],module.context_codes(CONTEXTS))
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'test-only.geojson';path.write_text(json.dumps(source));out=Path(directory)/'out'
   subprocess.run([sys.executable,str(ROOT/'scripts/prepare-poa2021-boundaries.py'),'--source',str(path),'--out',str(out)],capture_output=True,text=True,check=True)
   payload=(out/'poa2021.geojson').read_bytes();manifest=json.loads((out/'poa2021.provenance.json').read_text())
   self.assertEqual(manifest['feature_count'],12);self.assertEqual(manifest['output_sha256'],module.digest(payload));self.assertIn('origin not independently verified',manifest['acquisition'])

if __name__=='__main__':unittest.main()
