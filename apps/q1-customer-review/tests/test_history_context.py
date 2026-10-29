from pathlib import Path
import copy,json,unittest
from unittest.mock import patch
from prototype.history_context import attach_history,archive
import tests.test_auth_handler as auth
ROOT=Path(__file__).resolve().parents[1]
class HistoryContextTests(unittest.TestCase):
 def fixture(self):return json.loads((ROOT/'tests/fixtures/current-model-example.json').read_text())
 def test_full_lookback_and_partial_day_preserve_all_model_fields(self):
  data=self.fixture();before=copy.deepcopy(data);value=attach_history(data)
  for key in before:self.assertEqual(value[key],before[key])
  rows=value['timeline_weather'];self.assertEqual(len(rows),731);self.assertEqual(rows[0]['date'],'2024-10-28');self.assertEqual(rows[-1]['date'],'2026-10-28');self.assertIsNone(rows[-1]['max_temp']);self.assertEqual(rows[-1]['min_temp'],23.9)
  recent=[r for r in rows if r['date']>='2026-07-31'];self.assertEqual(len(recent),90);self.assertEqual(sum(r['max_temp'] is not None and r['min_temp'] is not None for r in recent),89)
  self.assertIsNone(value['timeline_weather_context']['original_available_at']);self.assertIn('excluded',value['timeline_weather_context']['scope'])
 def test_missing_archive_does_not_substitute_model_history(self):
  with patch('prototype.history_context.archive',side_effect=OSError()):value=attach_history(self.fixture())
  self.assertEqual(value['timeline_weather'],[]);self.assertEqual(value['timeline_weather_context']['status'],'unavailable')
 def test_other_modes_unchanged(self):
  data=self.fixture();data.pop('current_demo');before=copy.deepcopy(data);self.assertEqual(attach_history(data),before)
 def test_fingerprint_required(self):
  archive.cache_clear()
  with patch('prototype.history_context.EXPECTED','bad'):
   with self.assertRaises(ValueError):archive()
  archive.cache_clear();self.assertEqual(archive()['latitude'],-18.2)
 def test_authenticated_handler_returns_separate_chart_context(self):
  auth.AuthHandlerTests.setUpClass();h=auth.AuthHandlerTests();h.setUp()
  try:
   data=self.fixture();h.server.current_calculations=type('Current',(),{'view':lambda self,base:copy.deepcopy(data)})();headers=h.login('officer')
   with patch.object(h.server.uploads,'view',return_value={}):reply=h.request('/api/review?mode=upload',headers=headers)
   self.assertEqual(reply['status'],200);self.assertEqual(len(reply['body']['timeline_weather']),731);self.assertEqual(reply['body']['customers'],data['customers']);self.assertEqual(reply['body']['batch_revision'],data['batch_revision'])
  finally:h.tearDown()
