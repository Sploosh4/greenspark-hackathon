import copy,unittest
import test_source_adapter as fixtures
from source_adapter import validate_business,SourceError
from geography_reference import registry,extend_trusted_context,GEOGRAPHY_SHA
from test_business_upload import file_bytes,customer,usage,CUSTOMER_HEADERS,USAGE_HEADERS
from business_upload import derive_business

class Geography(unittest.TestCase):
 def setUp(self):
  import json
  self.seed=json.loads((fixtures.ROOT/'data/inputs/q3-area-context.json').read_text());self.trusted=extend_trusted_context(self.seed)
 def test_registry_pinned_and_genuine_boundary_checked(self):
  r=registry();self.assertEqual(len(r['areas']),387);self.assertEqual(sum(a['insideWaLandBoundary'] for a in r['areas']),386);self.assertEqual([a['postcode'] for a in r['areas'] if not a['insideWaLandBoundary']],['6701']);self.assertEqual(r['source']['licence'],'CC BY 4.0')
 def test_original_12_reference_points_and_income_unchanged(self):
  for old in self.seed['areas']:
   new=next(a for a in self.trusted['areas'] if a['postcode']==old['postcode']);self.assertEqual(new['referencePoint'],old['referencePoint']);self.assertEqual(new['financialContext'],old['financialContext'])
 def test_new_statewide_area_joins_exact_reference_and_has_no_invented_income(self):
  b,_=derive_business(file_bytes(CUSTOMER_HEADERS,[customer('NEW',pc='6000',name='Perth')]),file_bytes(USAGE_HEADERS,[usage('NEW')]),False,self.trusted,fixtures.NOW.date());a=b['areas'][0];self.assertEqual(a['referencePoint'],[115.8614,-31.9522]);self.assertIsNone(a['financialContext']);self.assertEqual(b['geographyRegistrySha256'],GEOGRAPHY_SHA);self.assertEqual(b['totalAccounts'],1)
 def test_client_cannot_supply_arbitrary_coordinates_or_wrong_locality(self):
  raw=file_bytes(CUSTOMER_HEADERS,[customer('NEW',pc='6000',name='Invented')])
  with self.assertRaisesRegex(SourceError,'unsupported_or_mismatched_locality'):derive_business(raw,file_bytes(USAGE_HEADERS,[usage('NEW')]),False,self.trusted,fixtures.NOW.date())
  b,_=derive_business(file_bytes(CUSTOMER_HEADERS,[customer('NEW',pc='6000',name='Perth')]),file_bytes(USAGE_HEADERS,[usage('NEW')]),False,self.trusted,fixtures.NOW.date());b['areas'][0]['referencePoint']=[120,-20]
  with self.assertRaisesRegex(SourceError,'area_reference_point_mismatch'):validate_business(b,[])
 def test_wrong_registry_or_source_provenance_rejected(self):
  b,_=derive_business(file_bytes(CUSTOMER_HEADERS,[customer('NEW',pc='6000',name='Perth')]),file_bytes(USAGE_HEADERS,[usage('NEW')]),False,self.trusted,fixtures.NOW.date());b['geographyRegistrySha256']='0'*64
  with self.assertRaises(SourceError):validate_business(b,[])
