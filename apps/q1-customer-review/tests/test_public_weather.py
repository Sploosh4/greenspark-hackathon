"""Synthetic public-cache fixtures. No network, new listener or shifted source dates."""
import copy,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from prototype.public_weather import normalise,window,PublicWeatherStore,WeatherError,PERTH,LAT,LON
from prototype.weather_job import DailyCacheJob,next_daily
from prototype.live import business_coverage
from prototype.prediction import InferenceContext,predict_context,Recent7HeatOffsetBaseline

NOW=datetime(2026,10,28,20,tzinfo=PERTH)
def cache(days=8):
    start=NOW.replace(hour=0)
    stamps=[(start+timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M') for i in range(days*24)]
    return {'schema_version':1,'dataset_kind':'live_forecast','provider':'Open-Meteo','source_url':'https://api.open-meteo.com/v1/forecast?latitude=-18.19714&longitude=125.56663','requested_at':NOW.isoformat(),'retrieved_at':NOW.isoformat(),'model_issued_at':None,'localities':[{'location':{'name':'Fitzroy Crossing','postcode':'6765','latitude':LAT,'longitude':LON},'valid_from':start.isoformat(),'valid_until_exclusive':(start+timedelta(days=days)).isoformat(),'forecast':{'timezone':'Australia/Perth','utc_offset_seconds':28800,'latitude':LAT,'longitude':LON,'hourly_units':{'temperature_2m':'°C'},'hourly':{'time':stamps,'temperature_2m':[20+i%24/2 for i in range(days*24)]}}}]}

class PublicWeatherTests(unittest.TestCase):
    def test_explicit_timing_and_exact_seven_days(self):
        source=normalise(cache());result=window(source,NOW)
        self.assertIsNone(source['model_issued_at']);self.assertNotEqual(source['requested_at'],source['valid_from'])
        self.assertEqual(result['horizon_start'],'2026-10-29');self.assertEqual(result['horizon_end'],'2026-11-04');self.assertEqual(len(result['days']),7)
        self.assertEqual(result['status']['complete_target_days'],7);self.assertEqual(result['days'][0]['max_temp'],31.5)
        self.assertEqual(source['heat_classification']['status'],'unavailable');self.assertFalse(result['current_customer_estimates_available'])
    def test_original_seven_calendar_day_cache_has_only_six_target_days(self):
        result=window(normalise(cache(7)),NOW)
        self.assertEqual(result['status']['complete_target_days'],6);self.assertIsNone(result['days'][-1]['max_temp'])
    def test_missing_null_hour_never_becomes_zero_or_daily_extrema(self):
        value=cache();value['localities'][0]['forecast']['hourly']['temperature_2m'][30]=None
        result=window(normalise(value),NOW);self.assertIsNone(result['days'][0]['min_temp'])
        self.assertEqual(result['days'][0]['status'],'unavailable')
    def test_invalid_units_grid_timezone_duplicate_and_reversed_hours_rejected(self):
        for kind in ['units','grid','timezone','duplicate','sequence','boolean','nan']:
            value=cache();f=value['localities'][0]['forecast']
            if kind=='units':f['hourly_units']['temperature_2m']='°F'
            elif kind=='grid':f['longitude']=110
            elif kind=='timezone':f['utc_offset_seconds']=0
            elif kind=='duplicate':f['hourly']['time'][2]=f['hourly']['time'][1]
            elif kind=='sequence':f['hourly']['time'].reverse()
            else:f['hourly']['temperature_2m'][2]=True if kind=='boolean' else float('nan')
            with self.subTest(kind=kind),self.assertRaises(WeatherError):normalise(value)
    def test_age_expiry_clock_and_failed_refresh(self):
        source=normalise(cache())
        for now,reason in [(NOW-timedelta(seconds=1),'clock_before_retrieval'),(NOW+timedelta(hours=24),'older_than_24_hours'),(NOW+timedelta(days=9),'coverage_expired')]:
            self.assertEqual(window(source,now)['status']['reason'],reason)
        self.assertEqual(window(source,NOW,'network_failed')['status']['reason'],'refresh_failed')
    def test_midnight_uses_perth_dates_and_does_not_relabel_stale_hours(self):
        result=window(normalise(cache()),datetime(2026,10,28,17,tzinfo=timezone.utc))
        self.assertEqual(result['review_date'],'2026-10-29');self.assertEqual(result['days'][0]['date'],'2026-10-30')
        self.assertIsNone(result['days'][-1]['max_temp'])
    def test_atomic_import_failure_restart_and_repeated_ingestion(self):
        with TemporaryDirectory() as root:
            folder=Path(root);source=folder/'shared.json';source.write_text(json.dumps(cache()));source.with_name('status.json').write_text(json.dumps({'last_attempt_succeeded':True}))
            store=PublicWeatherStore(folder/'own',source);first=store.refresh();self.assertTrue(first['succeeded']);self.assertEqual(first,store.refresh())
            self.assertEqual(len(list((folder/'own/snapshots').iterdir())),1)
            source.write_text('{broken');self.assertFalse(store.refresh()['succeeded'])
            self.assertEqual(store.view(NOW)['status']['reason'],'refresh_failed')
            restored=PublicWeatherStore(folder/'own',source);self.assertEqual(restored.view(NOW)['status']['reason'],'refresh_failed');self.assertEqual(restored.view(NOW)['status']['complete_target_days'],7)
    def test_corrupt_saved_source_is_not_loaded(self):
        with TemporaryDirectory() as root:
            folder=Path(root);source=folder/'shared.json';source.write_text(json.dumps(cache()));store=PublicWeatherStore(folder/'own',source);receipt=store.refresh()
            (folder/'own/snapshots'/receipt['sha256']).write_text('{}')
            self.assertIsNone(PublicWeatherStore(folder/'own',source).view(NOW)['source'])
    def test_upstream_failure_is_visible_even_with_valid_last_good(self):
        with TemporaryDirectory() as root:
            source=Path(root)/'shared.json';source.write_text(json.dumps(cache()));source.with_name('status.json').write_text(json.dumps({'last_attempt_succeeded':False}))
            store=PublicWeatherStore(Path(root)/'own',source);self.assertTrue(store.refresh()['succeeded']);self.assertEqual(store.view(NOW)['status']['last_error'],'upstream_refresh_failed')
    def test_scheduler_once_due_retry_and_restart_without_new_network_job(self):
        with TemporaryDirectory() as root:
            store=PublicWeatherStore(Path(root)/'own',Path(root)/'absent');job=DailyCacheJob(store,'06:00')
            first=job.tick(NOW);self.assertTrue(first['ran']);self.assertFalse(first['last_attempt_succeeded']);self.assertFalse(first['network_fetch'])
            self.assertFalse(job.tick(NOW+timedelta(minutes=1))['ran']);self.assertTrue(job.tick(NOW+timedelta(minutes=15))['ran'])
            self.assertFalse(DailyCacheJob(store,'06:00').tick(NOW+timedelta(minutes=16))['ran'])
            with patch.object(store,'refresh',return_value={'succeeded':True}):
                result=job.tick(NOW+timedelta(minutes=30));self.assertEqual(result['next_run_at'],'2026-10-28T22:00:00Z')
        for bad in ['6:00','25:00','06:90','bad']:
            with self.assertRaises(ValueError):next_daily(NOW,bad)
    def test_scheduler_new_time_and_corrupt_saved_state_do_not_keep_old_due(self):
        with TemporaryDirectory() as root:
            store=PublicWeatherStore(root,Path(root)/'absent');job=DailyCacheJob(store,'06:00')
            with patch.object(store,'refresh',return_value={'succeeded':True}):job.tick(NOW)
            changed=DailyCacheJob(store,'21:00')
            with patch.object(store,'refresh',return_value={'succeeded':True}):result=changed.tick(NOW)
            self.assertTrue(result['ran']);self.assertEqual(result['daily_time'],'21:00');self.assertEqual(result['next_run_at'],'2026-10-28T13:00:00Z')
            (Path(root)/'job.json').write_text('[]')
            self.assertTrue(DailyCacheJob(store).tick(NOW)['ran'])
    def test_malformed_nested_cache_does_not_escape_ingestion_or_retry(self):
        with TemporaryDirectory() as root:
            source=Path(root)/'source.json';value=cache();value['localities'][0]['location']=None;source.write_text(json.dumps(value))
            store=PublicWeatherStore(Path(root)/'own',source);result=DailyCacheJob(store).tick(NOW)
            self.assertFalse(result['last_attempt_succeeded']);self.assertEqual(result['next_run_at'],'2026-10-28T12:15:00Z')
    def test_historical_usage_dates_do_not_move_to_current_review(self):
        tables={'customers':[{'customer_id':'A'}],'consumption_daily':[{'customer_id':'A','date':'2025-06-30','supply_status':'connected','outage_hours':'0'}]}
        with patch('prototype.live.load_business',return_value=(tables,{'files':[]})):result=business_coverage('unused',NOW)
        customer=result['customers'][0];self.assertEqual(customer['latest_usage_date'],'2025-06-30');self.assertEqual(customer['complete_recent_days'],0);self.assertEqual(customer['history_status'],'stale');self.assertIsNone(customer['estimate'])

class AccessAndProviderTests(unittest.TestCase):
    def test_baseline_and_future_context_provider_boundary(self):
        context=InferenceContext('2026-10-28T17:00:00Z','2026-10-28','2026-10-30','2026-11-05','public_weather_forecast','2026-10-28T16:59:00Z')
        self.assertEqual(predict_context(Recent7HeatOffsetBaseline(),[],[],[],context),[])
        class Future:
            def predict_with_context(self,*args,context):return context.forecast_track
        self.assertIsNone(predict_context(Future(),[],[],[],context))
        with self.assertRaises(ValueError):predict_context(Future(),[],[],[{'start':'2026-10-29','end':'2026-10-30'}],context)
        with self.assertRaises(ValueError):predict_context(Future(),[],[],[],InferenceContext('2026-10-28T17:00:00Z','2026-10-28','2026-10-30','2026-11-05','public_weather_forecast','2026-10-28T18:00:00Z'))
    def test_public_context_cannot_use_a_historical_business_cutoff(self):
        context=InferenceContext('2026-10-28T17:00:00Z','2024-11-01','2026-10-30','2026-11-05','public_weather_forecast')
        with self.assertRaisesRegex(ValueError,'through yesterday'):predict_context(Recent7HeatOffsetBaseline(),[],[],[],context)
