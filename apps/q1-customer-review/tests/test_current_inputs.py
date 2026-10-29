"""Explicit unit fixtures only; no business cohort generation or network."""
from copy import deepcopy
from datetime import date,datetime,time,timedelta
import json,sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from prototype.current_inputs import *

REVIEW='2026-10-29T03:00:00+08:00'
LOADED='2026-10-29T02:55:00+08:00'

def tables():
    return {'customers':[{'customer_id':'C1','locality':'Fitzroy Crossing','postcode':'6765'}],
            'consumption_daily':[{'customer_id':'C1','date':str(date(2026,10,21)+i*DAY),'import_kwh':'10','supply_status':'connected','outage_hours':'0'} for i in range(8)]}

def manifest(review=REVIEW,lag=1):
    return {'schema':'q1-synthetic-current-business/v1','synthetic_business':True,'real_customer_data':False,'genuine_as_issued':False,'review_as_of':review,'generated_at':'2026-10-29T04:00:00+08:00','timezone':'Australia/Perth','daily_window':DAILY_WINDOW,'reporting_lag_days':lag,'availability_rule_id':'unit-fixture-next-day-noon/v1','source_files_sha256':{'unit-fixture-only.csv':'a'*64}}

def sidecars(t,*,synthetic=False,m=None):
    result=[]
    for row in t['consumption_daily']:
        base={'customer_id':row['customer_id'],'date':row['date'],'row_sha256':row_hash(row)}
        when=datetime.combine(day(row['date'])+DAY,time(12 if synthetic else 2),PERTH).isoformat()
        if synthetic:base.update(basis='generator_simulated_schedule',original_available_at=None,simulated_available_at=when,source_manifest_sha256=row_hash(m),availability_rule_id=m['availability_rule_id'])
        else:base.update(basis='original_source_record',original_available_at=when,simulated_available_at=None,evidence_sha256='b'*64,timezone='Australia/Perth',daily_window=DAILY_WINDOW)
        result.append(base)
    return result

class AvailabilityTests(unittest.TestCase):
    def ready(self,t=None,**kwargs):return business_readiness(t or tables(),review_as_of=REVIEW,**kwargs)['customers'][0]
    def test_dates_alone_and_upload_time_do_not_establish_availability(self):
        t=tables();t['uploaded_at']='2026-10-29T02:00:00+08:00'
        row=self.ready(t);self.assertEqual(row['recent_eligible_days'],0);self.assertEqual(row['unknown_availability_rows'],8)
        self.assertIsNone(row['current_estimate'])
    def test_explicit_original_available_rows_and_true_zero_survive(self):
        t=tables();t['consumption_daily'][-1]['import_kwh']='0';records=sidecars(t)
        row=self.ready(t,availability_records=records);self.assertTrue(row['recent_complete']);self.assertEqual(row['recent_imports'][-1]['import_kwh'],0)
        self.assertIsNone(row['current_estimate']);self.assertEqual(row['current_estimate_reason'],'current_weather_and_model_contract_not_admitted')
    def test_late_or_before_window_closed_original_row_is_excluded(self):
        for timestamp,reason in [('2026-10-29T03:00:01+08:00','not_available_at_review'),('2026-10-28T23:59:59+08:00','availability_before_daily_window_closed')]:
            records=sidecars(tables());records[-1]['original_available_at']=timestamp
            row=self.ready(availability_records=records);self.assertEqual(row['recent_eligible_days'],6);self.assertEqual(row['excluded_counts'][reason],1)
    def test_exact_cutoff_includes_row_and_timezone_is_equivalent(self):
        records=sidecars(tables());records[-1]['original_available_at']='2026-10-28T19:00:00Z'
        self.assertTrue(self.ready(availability_records=records)['recent_complete'])
    def test_synthetic_noon_is_separate_and_does_not_leak_into_strict(self):
        t=tables();m=manifest();records=sidecars(t,synthetic=True,m=m)
        strict=self.ready(t,availability_records=records);self.assertEqual(strict['recent_eligible_days'],0)
        row=self.ready(t,availability_records=records,mode=SYNTHETIC_MODE,generation_manifest=m)
        self.assertEqual(row['recent_eligible_days'],6)
        self.assertTrue(all(r['original_available_at'] is None for r in records))
    def test_declared_two_day_lag_at03_and_one_day_after_noon(self):
        for lag,review in [(2,REVIEW),(1,'2026-10-29T13:00:00+08:00')]:
            t=tables();m=manifest(review,lag);records=sidecars(t,synthetic=True,m=m)
            result=business_readiness(t,review_as_of=review,availability_records=records,mode=SYNTHETIC_MODE,generation_manifest=m,reporting_lag_days=lag)
            self.assertTrue(result['customers'][0]['recent_complete']);self.assertFalse(result['current_estimates_available']);self.assertEqual(result['required_usage_end'],'2026-10-27' if lag==2 else '2026-10-28')
    def test_manifest_cutoff_timezone_and_lag_are_enforced(self):
        for key,value in [('review_as_of','2026-10-28T03:00:00+08:00'),('timezone','UTC'),('daily_window','following_night'),('reporting_lag_days',2),('synthetic_business',False),('genuine_as_issued',True),('source_files_sha256',{})]:
            m=manifest();m[key]=value
            with self.subTest(key=key),self.assertRaises(ContractError):self.ready(mode=SYNTHETIC_MODE,generation_manifest=m)
    def test_approval_strings_never_open_current_estimates(self):
        t=tables();m=manifest(lag=2);m.update(approved=True,release_status='approved',calibration_compatible=True)
        row=self.ready(t,mode=SYNTHETIC_MODE,generation_manifest=m,availability_records=sidecars(t,synthetic=True,m=m),reporting_lag_days=2)
        self.assertTrue(row['recent_complete']);self.assertIsNone(row['current_estimate'])
    def test_changed_row_and_wrong_manifest_fingerprints_excluded(self):
        t=tables();records=sidecars(t);t['consumption_daily'][-1]['import_kwh']='99'
        self.assertEqual(self.ready(t,availability_records=records)['excluded_counts']['row_fingerprint_mismatch'],1)
        t=tables();m=manifest();records=sidecars(t,synthetic=True,m=m);records[-1]['source_manifest_sha256']='c'*64
        self.assertEqual(self.ready(t,mode=SYNTHETIC_MODE,generation_manifest=m,availability_records=records)['excluded_counts']['invalid_simulated_lineage'],1)
    def test_missing_outage_nonfinite_unknown_and_negative_are_not_zero(self):
        for key,value in [('import_kwh',''),('import_kwh','NaN'),('import_kwh',True),('import_kwh','-1'),('outage_hours',''),('outage_hours','1'),('supply_status','disconnected')]:
            t=tables();t['consumption_daily'][-1][key]=value;row=self.ready(t,availability_records=sidecars(t))
            self.assertEqual(row['recent_eligible_days'],6);self.assertIsNone(row['recent_imports'][-1]['import_kwh'])
    def test_duplicate_or_orphan_and_cross_customer_records_rejected(self):
        t=tables();records=sidecars(t)
        with self.assertRaises(ContractError):self.ready(t,availability_records=records+[records[0]])
        t['consumption_daily'].append(t['consumption_daily'][0])
        with self.assertRaises(ContractError):self.ready(t)
        t=tables();t['consumption_daily'][0]['customer_id']='C2'
        with self.assertRaises(ContractError):self.ready(t)
        records=sidecars(tables());records[0]['date']='2026-10-20'
        with self.assertRaises(ContractError):self.ready(availability_records=records)
    def test_invalid_clock_lag_and_identity_rejected(self):
        for lag in (0,3,True):
            with self.assertRaises(ContractError):self.ready(reporting_lag_days=lag)
        with self.assertRaises(ContractError):business_readiness(tables(),review_as_of='2026-10-29T03:00:00')
        t=tables();t['customers'][0]['customer_id']='benchmark-HH'
        with self.assertRaises(ContractError):self.ready(t)
    def test_unmapped_locality_is_not_assigned_SILO_grid(self):
        t=tables();t['customers'][0]['postcode']='9999';row=self.ready(t)
        self.assertFalse(row['locality_mapped']);self.assertIsNone(row['locality_id'])
    def test_sources_are_not_mutated_and_missing_finances_do_not_gate_usage(self):
        t=tables();before=deepcopy(t);row=self.ready(t,availability_records=sidecars(t));self.assertTrue(row['recent_complete']);self.assertEqual(t,before)

class WeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.raw=json.loads((ROOT/'tests/fixtures/retained-public-wrapper.json').read_text())
    def context(self,raw=None,review=REVIEW,loaded=LOADED):return temperature_context(deepcopy(self.raw if raw is None else raw),review_as_of=review,adapter_loaded_at=loaded)
    def test_seven_calendar_days_and_exact_returned_source_identity(self):
        result=self.context();self.assertEqual(result['status']['complete_target_days'],7)
        self.assertEqual([r['date'] for r in result['days']],['2026-10-'+str(d) for d in (30,31)]+['2026-11-0'+str(d) for d in range(1,6)])
        self.assertEqual(result['spatial_context']['actual_forecast_grid'],[-18.24253,125.560974]);self.assertEqual(result['spatial_context']['actual_forecast_elevation_m'],114.0)
        self.assertIsNone(result['availability']['model_issued_at']);self.assertFalse(result['current_customer_estimates_available'])
        self.assertTrue(all(not d['observed'] and d['heat_classification'] is None for d in result['days']))
    def test_snapshot_or_actual_adapter_load_after_review_hides_all_values(self):
        for review,loaded in [('2026-10-29T02:00:00+08:00',LOADED),(REVIEW,'2026-10-29T04:07:51+08:00')]:
            result=self.context(review=review,loaded=loaded);self.assertEqual(result['status']['reason'],'source_not_available_to_adapter_at_review');self.assertTrue(all(d['max_temp'] is None for d in result['days']))
    def test_loaded_before_retrieval_rejected(self):
        with self.assertRaises(ContractError):self.context(loaded='2026-10-29T02:00:00+08:00')
    def test_null_hour_unavailable_but_genuine_zero_temperature_numeric(self):
        raw=deepcopy(self.raw);h=raw['localities'][0]['forecast']['hourly'];i=h['time'].index('2026-10-30T12:00');h['temperature_2m'][i]=None
        self.assertIsNone(self.context(raw)['days'][0]['max_temp'])
        for i,s in enumerate(h['time']):
            if s.startswith('2026-10-30'):h['temperature_2m'][i]=0
        self.assertEqual(self.context(raw)['days'][0]['max_temp'],0)
    def test_duplicate_hour_wrong_units_and_remote_grid_fail_closed(self):
        for kind in ('duplicate','units','grid','issue'):
            raw=deepcopy(self.raw);f=raw['localities'][0]['forecast']
            if kind=='duplicate':f['hourly']['time'][1]=f['hourly']['time'][0]
            if kind=='units':f['hourly_units']['temperature_2m']='K'
            if kind=='grid':f['latitude']=-33.8
            if kind=='issue':raw['model_issued_at']=raw['retrieved_at']
            r=self.context(raw);self.assertEqual(r['temperature_display'],'unavailable');self.assertTrue(all(d['max_temp'] is None for d in r['days']));self.assertEqual(r['heat_classification']['status'],'unavailable')
    def test_close_grid_change_stays_explicit_and_never_admits_scoring(self):
        raw=deepcopy(self.raw);raw['localities'][0]['forecast']['latitude']=-18.25;raw.update(approved=True,calibration_compatible=True)
        r=self.context(raw);self.assertEqual(r['spatial_context']['actual_forecast_grid'][0],-18.25);self.assertFalse(r['spatial_context']['spatial_bridge_admitted']);self.assertEqual(r['heat_classification']['status'],'unavailable')
    def test_stale_snapshot_is_marked_and_modelled_past_is_never_observed(self):
        r=self.context(review='2026-10-30T04:00:00+08:00');self.assertEqual(r['temperature_display'],'saved_stale_temperatures_only');self.assertEqual(r['source']['warmup_kind'],'archived_model_forecast');self.assertFalse(r['source']['observed_warmup_available'])
    def test_matching_locality_not_first_controls_returned_elevation(self):
        raw=deepcopy(self.raw);raw['localities'].insert(0,{'location':{'postcode':'9999'},'forecast':{'elevation':9999}})
        self.assertEqual(self.context(raw)['spatial_context']['actual_forecast_elevation_m'],114.0)
    def test_source_is_not_modified(self):
        before=deepcopy(self.raw);self.context();self.assertEqual(self.raw,before)
    def test_refresh_failure_keeps_saved_context_explicitly_stale_not_successful(self):
        r=temperature_context(self.raw,review_as_of=REVIEW,adapter_loaded_at=LOADED,source_last_error='provider_failed')
        self.assertEqual(r['status']['reason'],'refresh_failed');self.assertEqual(r['temperature_display'],'saved_stale_temperatures_only');self.assertEqual(r['status']['complete_target_days'],7);self.assertFalse(r['current_customer_estimates_available'])

class ObservationAndModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.observations=json.loads((ROOT/'tests/fixtures/retained-observed-windows.json').read_text())
    def test_0300_cannot_see_0407_snapshot_or_0427_staging_load(self):
        r=observed_context(self.observations,review_as_of=REVIEW);self.assertEqual(r['complete_windows'],0);self.assertIsNone(r['app_ingested_at'])
    def test_later_cutoff_separately_admits34_windows_not_a_mixed_indicator(self):
        r=observed_context(self.observations,review_as_of='2026-10-29T05:00:00+08:00');self.assertEqual(r['complete_windows'],34);self.assertEqual((r['first_window'],r['last_window']),('2026-09-24','2026-10-27'));self.assertFalse(r['combined_with_forecasts']);self.assertFalse(r['calibration_admitted'])
    def test_output_retains_source_times_component_hashes_and_adapter_identity(self):
        r=observed_context(self.observations,review_as_of='2026-10-29T05:00:00+08:00');source=self.observations['windows'][0];meta=r['windows'][0]['source_provenance']
        for key in ('snapshot_available_at','staged_loaded_at','app_ingested_at','adapter_reference_version','day_window_reference_version'):self.assertEqual(meta[key],source.get(key))
        for role,component in source['components'].items():
            for key in ('source_url','source_bundle_sha256','identity_kind','retrieved_at','native_representation'):self.assertEqual(meta['components'][role][key],component[key])
    def test_wrong_component_URL_or_range_hash_is_rejected(self):
        for key,value in [('source_url','https://example.invalid/source.tif'),('source_bundle_sha256','unknown')]:
            rows=deepcopy(self.observations);rows['windows'][0]['components']['tmax'][key]=value
            with self.assertRaises(ContractError):observed_context(rows,review_as_of='2026-10-29T05:00:00+08:00')
    def test_second_shift_grid_change_and_source_code_invention_rejected(self):
        for key,value in [('date','2026-09-23'),('grid',[-18.25,125.55]),('source_codes',25)]:
            rows=deepcopy(self.observations);rows['windows'][0]['components']['tmax'][key]=value
            with self.assertRaises(ContractError):observed_context(rows,review_as_of='2026-10-29T05:00:00+08:00')
    def test_inversion_and_zero_are_distinct_and_unknown_codes_preserved(self):
        rows=deepcopy(self.observations);r=rows['windows'][0];r['components']['tmax']['value_c']=0
        self.assertEqual(observed_context(rows,review_as_of='2026-10-29T05:00:00+08:00')['complete_windows'],33)
        r['components']['following_tmin']['value_c']=0;r['dmt_c']=0
        out=observed_context(rows,review_as_of='2026-10-29T05:00:00+08:00');self.assertEqual(out['windows'][0]['max_temp_c'],0);self.assertIsNone(out['windows'][0]['source_codes'])
    def test_component_retrieval_and_snapshot_load_chronology_are_enforced(self):
        for when in ('2026-09-24T08:00:00+08:00','2026-10-29T06:00:00+08:00'):
            rows=deepcopy(self.observations);rows['windows'][0]['components']['tmax']['retrieved_at']=when
            with self.assertRaises(ContractError):observed_context(rows,review_as_of='2026-10-29T05:00:00+08:00')
        rows=deepcopy(self.observations);rows['windows'][0]['staged_loaded_at']='2026-10-29T02:00:00+08:00'
        with self.assertRaises(ContractError):observed_context(rows,review_as_of='2026-10-29T05:00:00+08:00')
    def test_frozen_horizon_is_six_Q1_days_with_day7_explicitly_uncovered(self):
        r=model_contract_gaps(review_as_of=REVIEW);self.assertEqual(len(r['overlap_dates']),6);self.assertEqual(r['uncovered_q1_dates'],['2026-11-05']);self.assertEqual(r['frozen_horizon'],{'start':'2026-10-29','end':'2026-11-04'});self.assertFalse(r['EHF_is_a_frozen_M5_feature']);self.assertFalse(r['scoring_interface_present'])
    def test_combined_payload_current_rows_never_open_gate_or_mutate_sources(self):
        raw=WeatherTests.raw if hasattr(WeatherTests,'raw') else json.loads((ROOT/'tests/fixtures/retained-public-wrapper.json').read_text());t=tables();before=deepcopy(t)
        r=current_payload(raw,t,review_as_of=REVIEW,adapter_loaded_at=LOADED,availability_records=sidecars(t),observations=self.observations)
        self.assertEqual(r['business']['customers'][0]['complete_recent_days'],7);self.assertIsNone(r['business']['customers'][0]['estimate']);self.assertFalse(r['current_customer_estimates_available']);self.assertEqual(t,before)

if __name__=='__main__':unittest.main()
