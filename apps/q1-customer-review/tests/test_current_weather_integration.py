"""Existing authenticated GET -> cache -> context -> JSON, without a listener."""
from copy import deepcopy
from datetime import timedelta
import hashlib,json,threading
from pathlib import Path
import unittest
from unittest.mock import patch

import tests.test_auth_handler as auth_handlers
from prototype.public_weather import PublicWeatherStore
from prototype.weather_job import DailyCacheJob
from prototype.replay_snapshot import load_snapshot,MODE
from prototype.inputs import DEFAULT_SOURCE

ROOT=Path(__file__).resolve().parents[1]
NOW=__import__('datetime').datetime.fromisoformat('2026-10-29T03:00:00+08:00')
INPUT=ROOT/'tests/fixtures/retained-public-wrapper.json'

class CurrentWeatherIntegrationTests(unittest.TestCase):
    request=auth_handlers.AuthHandlerTests.request
    login=auth_handlers.AuthHandlerTests.login
    @classmethod
    def setUpClass(cls):
        auth_handlers.AuthHandlerTests.setUpClass.__func__(cls)
        cls.replay=load_snapshot(ROOT/'replay-data/cohort.json',source_root=DEFAULT_SOURCE,availability_mode=MODE)
    def setUp(self):
        auth_handlers.AuthHandlerTests.setUp(self)
        self.weather_root=Path(self.tmp.name)/'current-weather'
        self.store=PublicWeatherStore(self.weather_root,Path(self.tmp.name)/'absent',clock=lambda:NOW)
        self.assertTrue(self.store.ingest(INPUT,upstream_status=False)['succeeded'])
        self.server.public_weather=self.store;self.server.weather_job=DailyCacheJob(self.store)
        self.server.live_coverage={};self.server.live_coverage_lock=threading.RLock()
        self.server.clock=lambda:NOW;self.server.review=self.replay;self.server.demo_revision=self.replay['snapshot_id']
        self.headers=self.login('officer')
    def tearDown(self):auth_handlers.AuthHandlerTests.tearDown(self)
    def current(self):
        result=self.request('/api/live-weather',headers=self.headers);self.assertEqual(result['status'],200,result)
        return result['body']
    def test_seven_days_exact_provenance_current_unavailable_and_historical_unchanged(self):
        before=deepcopy(self.server.review);payload=self.current()
        self.assertEqual(len(payload['days']),7);self.assertEqual(payload['status']['complete_target_days'],7)
        self.assertEqual((payload['horizon_start'],payload['horizon_end']),('2026-10-30','2026-11-05'))
        self.assertEqual(payload['weather_snapshot_sha256'],hashlib.sha256(INPUT.read_bytes()).hexdigest())
        self.assertEqual(payload['availability']['adapter_loaded_at'],NOW.isoformat())
        self.assertIsNone(payload['availability']['model_issued_at']);self.assertEqual(payload['spatial_context']['actual_forecast_elevation_m'],114)
        self.assertFalse(payload['current_customer_estimates_available']);self.assertEqual(payload['heat_classification']['status'],'unavailable')
        self.assertEqual(payload['business']['supplied_usage_end'],'2025-06-30')
        self.assertTrue(all(c['estimate'] is None and c['complete_recent_days']==0 for c in payload['business']['customers']))
        self.assertEqual(self.server.review,before)
        historical=self.request('/api/review',headers=self.headers)['body']
        self.assertEqual(historical['snapshot_id'],before['snapshot_id']);self.assertEqual(historical['customers'],before['customers'])
    def test_refresh_failure_retains_last_good_temperatures_and_marks_stale(self):
        first=self.current();self.store.ingest(Path(self.tmp.name)/'missing')
        payload=self.current();self.assertEqual(payload['status']['reason'],'refresh_failed')
        self.assertEqual(payload['weather_snapshot_sha256'],first['weather_snapshot_sha256']);self.assertEqual(payload['days'],first['days'])
        self.assertFalse(payload['current_customer_estimates_available'])
    def test_age_stale_and_missing_snapshot_remain_seven_days_with_blank_estimates(self):
        self.server.clock=lambda:NOW+timedelta(hours=25)
        self.assertEqual(self.current()['temperature_display'],'saved_stale_temperatures_only')
        self.server.public_weather=PublicWeatherStore(Path(self.tmp.name)/'empty',Path(self.tmp.name)/'absent',clock=lambda:NOW)
        payload=self.current();self.assertEqual(len(payload['days']),7)
        self.assertTrue(all(d['max_temp'] is None and d['min_temp'] is None for d in payload['days']))
        self.assertTrue(all(c['estimate'] is None for c in payload['business']['customers']))
    def test_missing_hour_and_after_cutoff_load_cannot_become_zero_or_forecast_values(self):
        raw=json.loads(INPUT.read_bytes());f=raw['localities'][0]['forecast']['hourly'];f['temperature_2m'][f['time'].index('2026-10-30T12:00')]=None
        file=Path(self.tmp.name)/'partial.json';file.write_text(json.dumps(raw))
        self.assertTrue(self.store.ingest(file,upstream_status=False)['succeeded'])
        payload=self.current();self.assertIsNone(payload['days'][0]['max_temp']);self.assertEqual(payload['status']['complete_target_days'],6)
        self.store.context_clock=lambda:NOW+timedelta(hours=1);self.store.ingest(INPUT,upstream_status=False)
        payload=self.current();self.assertEqual(payload['status']['reason'],'source_not_available_to_adapter_at_review');self.assertTrue(all(d['max_temp'] is None for d in payload['days']))
    def test_restart_records_actual_new_load_preserving_snapshot_not_old_availability(self):
        original=self.current();later=NOW+timedelta(minutes=5)
        restarted=PublicWeatherStore(self.weather_root,Path(self.tmp.name)/'absent',clock=lambda:later)
        self.server.public_weather=restarted;self.server.clock=lambda:later
        payload=self.current();self.assertEqual(payload['weather_snapshot_sha256'],original['weather_snapshot_sha256']);self.assertEqual(payload['availability']['adapter_loaded_at'],later.isoformat())
        self.server.clock=lambda:NOW;self.assertEqual(self.current()['status']['reason'],'source_not_available_to_adapter_at_review')
    def test_current_dates_without_report_metadata_never_admit_estimates(self):
        tables={'customers':[{'customer_id':'C1','locality':'Fitzroy Crossing','postcode':'6765'}],
                'consumption_daily':[{'customer_id':'C1','date':'2026-10-'+str(d),'import_kwh':'10','supply_status':'connected','outage_hours':'0'} for d in range(22,29)]}
        with patch('prototype.live.load_business',return_value=(tables,{'files':[]})):
            payload=self.current()
        row=payload['business']['customers'][0];self.assertEqual(row['history_status'],'availability_unverified');self.assertEqual(row['complete_recent_days'],0);self.assertIsNone(row['estimate']);self.assertFalse(payload['current_customer_estimates_available'])
    def test_strict_live_replay_outputs_stay_unavailable_and_unauthenticated_reads_denied(self):
        for mode in ('strict','live'):
            self.server.review=load_snapshot(ROOT/'replay-data/cohort.json',source_root=DEFAULT_SOURCE,availability_mode=mode)
            self.server.demo_revision=self.server.review['snapshot_id'];self.server.live_coverage={}
            self.assertTrue(all(p['predicted'] is None for row in self.server.review['customers'] for p in row['predictions']))
            self.assertFalse(self.current()['current_customer_estimates_available'])
        with patch.object(self.store,'context_source',side_effect=AssertionError('read before auth')):
            self.assertEqual(self.request('/api/live-weather')['status'],401)
    def test_context_source_is_a_copy_and_cannot_mutate_the_saved_snapshot(self):
        context=self.store.context_source();before=self.store.context_source()
        context['snapshot']['hourly'][0]['temperature_c']=999
        self.assertEqual(self.store.context_source(),before)

if __name__=='__main__':unittest.main()
