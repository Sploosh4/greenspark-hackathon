"""Admission stays exact: one reviewed demonstration, all earlier pins retained."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_source_adapter
import financial_reference as registry
from source_adapter import SourceError,canonical,digest

DEMO='4056b0aa4979cc5bf7a58b3315c36dc7a0da71c7627c2d3b6a24fc05b888c614'
OLD={
 'ad563b96dc8b085019b58b64189dbe42b3d4dbf854d36f13f77218e0ae940a29':'4709eb3a26766203c04ca312e0547b1a91c48204e80a6adb98bf7b4d63fd48a4',
 'dd1e06d2d48b47cfe010c32d6f138a7ff23c3d64b839898daa2829794d44b03e':'d42382fe0a5194e86816add18a9c3605926ece4a35471be6ba1344aefe2e622d',
 'e5b681f61a2036d3efe004222c274fc914c0da5feee5036944de0fd4726d3374':'0833f9617fe52ecf6e244878bbe513e08d705be54454ea2d4d61b6279a9065ca'}
class DemoAdmission(unittest.TestCase):
 def tearDown(self):registry._registry.cache_clear()
 def test_existing_three_entries_remain_byte_equivalent(self):
  self.assertEqual(set(registry._registry()['fixtures']),set(OLD)|{DEMO})
  for h,expected in OLD.items():self.assertEqual(digest(canonical(registry.reviewed_entry(h))),expected)
 def test_new_entry_binds_exact_cohort_window_geography_and_aggregate(self):
  e=registry.reviewed_entry(DEMO)
  self.assertEqual((e['retainedAccounts'],e['activeAccounts'],e['snapshotDate'],e['historyStart'],e['historyEnd']),(50000,46500,'2025-06-30','2023-07-01','2025-06-30'))
  self.assertEqual(e['accountPostcodes'],['6450','6701','6707','6714','6718','6721','6722','6725','6728','6743','6765','6770'])
  self.assertEqual(e['customerSourceSha256'],'671c0f06a4de7cd058e7b549b1666b81d4e30db0db0c9af2cbc1f7b01e58b9b5')
  self.assertEqual(e['usageSourceSha256'],'c4122e8529832794d02119f4a1a5108cb84d0572a169dd17cc1f68cf23ee5000')
  self.assertEqual(e['geographyRegistrySha256'],'ecf0e7dc32e73eea517dd3c0a3706f96441fcba1d82c98fa49ecee50276d69de')
  self.assertEqual(e['aggregateSha256'],'4ee0f9ee90536cf46c7914b1cec2f86baf17c3e661d058fb2bb82f9ba919a547')
 def test_unknown_and_malformed_manifest_pins_still_rejected(self):
  for h in ['0'*64,DEMO+' ',DEMO.upper(),None,{},42]:
   with self.subTest(h=h),self.assertRaisesRegex(SourceError,'unreviewed_financial_manifest'):registry.reviewed_entry(h)
 def test_returned_entry_cannot_mutate_registry_authority(self):
  e=registry.reviewed_entry(DEMO);e['accountPostcodes'].append('UNTRUSTED');e['sourceHashes'].clear()
  self.assertEqual(len(registry.reviewed_entry(DEMO)['accountPostcodes']),12);self.assertEqual(len(registry.reviewed_entry(DEMO)['sourceHashes']),5)
 def test_modified_registry_not_accepted_under_existing_pin(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'registry.json';data=json.loads(registry.REGISTRY_PATH.read_bytes());data['fixtures']['0'*64]=data['fixtures'][DEMO];p.write_bytes(canonical(data))
   registry._registry.cache_clear()
   with patch.object(registry,'REGISTRY_PATH',p),self.assertRaisesRegex(SourceError,'financial_registry_integrity'):registry.reviewed_entry('0'*64)
