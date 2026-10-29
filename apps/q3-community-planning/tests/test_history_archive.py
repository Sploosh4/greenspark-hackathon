import json,sys,unittest,hashlib,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'server'))
from history_archive import HistoryArchive
from source_adapter import SourceError

class HistoricalArchive(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.archive=HistoryArchive(ROOT/'data/history')
 def test_only_silo_permitted_months_and_no_baseline_numeric_bundle(self):
  m=self.archive.metadata;self.assertEqual(len(m['layers']),48);self.assertEqual(sorted(k for k in m['layers'] if k[0].isdigit())[0],'2024-10');self.assertEqual(sorted(k for k in m['layers'] if k[0].isdigit())[-1],'2026-09');self.assertNotIn('climatology',m);self.assertFalse(any('bom' in p.name.lower() for p in (ROOT/'data/history').iterdir()))
 def test_native_fitzroy_and_five_year_values(self):
  a=self.archive.cell('2025-11',125.55,-18.2);b=self.archive.cell('average-11',125.55,-18.2);self.assertAlmostEqual(a['values']['midpoint'],34.060001373291016);self.assertAlmostEqual(b['values']['midpoint'],32.91466751098633);self.assertAlmostEqual(b['values']['midpointMin'],31.85333251953125);self.assertEqual(len(b['sourceMonths']),5)
 def test_carnarvon_offshore_proxy_remains_missing(self):
  p=self.archive.cell('2025-11',113.65,-24.9);self.assertFalse(p['available']);self.assertIsNone(p['values']['midpoint'])
 def test_outside_grid_and_invalid_coordinate(self):
  self.assertFalse(self.archive.cell('average-10',150,-20)['available'])
  with self.assertRaises(SourceError):self.archive.cell('average-10',float('nan'),-20)
 def test_all_48_hashes_values_masks_flags_and_pngs(self):
  total=0
  for key in self.archive.metadata['layers']:
   with self.subTest(key=key):
    d=self.archive.layer(key);a=d['fields'];self.assertEqual(sum(v is not None for v in a['midpoint']),91180);self.assertTrue(self.archive.image(key).startswith(b'\x89PNG\r\n'))
    self.assertEqual(sum(a['qualityFlags']),self.archive.metadata['layers'][key]['qualityFlaggedCellDays'])
    if key.startswith('average-'):total+=sum(a['qualityFlags'])
  self.assertEqual(total,2623)
 def test_quality_flags_preserved_at_known_source_cell(self):
  p=self.archive.cell('average-05',120.35,-21.1);self.assertGreater(p['values']['qualityFlags'],0)
 def test_unknown_layer_cannot_read_arbitrary_path(self):
  for key in ['../../provenance','../climatology/wa-bom-1991-2020-01','2026-10']:
   with self.assertRaises(SourceError):self.archive.image(key)

 def test_silo_normal_reference_period_flags_and_native_cell(self):
  m=self.archive.metadata['normal'];self.assertEqual(m['sourceObjects'],21916);self.assertEqual(m['sourceDays'],10958);self.assertEqual(m['sourceInversionCellDays'],585);self.assertEqual(sum(sum(self.archive.layer(f'normal-{month:02d}')['fields']['qualityFlags']) for month in range(1,13)),585)
  p=self.archive.cell('normal-10',115.85,-31.95);self.assertAlmostEqual(p['values']['midpoint'],17.3843,places=3);self.assertEqual(len(p['sourceMonths']),30);self.assertIn('1991–2020',p['period']);self.assertIn('midpointValidPairSensitivity',p['values'])
