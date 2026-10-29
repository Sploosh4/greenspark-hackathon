import copy
import csv
import gzip
import json
import math
import unittest
from datetime import date,timedelta
from pathlib import Path
from prototype.inputs import InputError,number,validate_row,DEFAULT_SOURCE
from prototype.prediction import Recent7HeatOffsetBaseline,observed_event,complete_mean
from prototype.review import build_review,known_support_links
from prototype.weather import load_weather,event_windows,derive

def usage(start,end,value=10):
    a=date.fromisoformat(start);b=date.fromisoformat(end)
    return [{'date':(a+timedelta(days=i)).isoformat(),'import_kwh':str(value),'supply_status':'connected','outage_hours':'0'} for i in range((b-a).days+1)]
def event(id,start,end,**kw):
    return {'id':id,'start':start,'end':end,'start_boundary':'known_start','end_boundary':'known_end',**kw}

class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.rows=usage('2024-01-01','2024-01-07',10)+usage('2024-01-08','2024-01-10',15)+usage('2024-01-11','2024-01-17',20)
        self.past=[event('P','2024-01-08','2024-01-10')]
        self.future=[event('A','2024-01-19','2024-01-21')]
        self.model=Recent7HeatOffsetBaseline()
    def predict(self,rows=None,events=None):
        return self.model.predict(self.rows if rows is None else rows,self.past,self.future if events is None else events,cutoff='2024-01-17')
    def test_independent_additive_arithmetic(self):
        p=self.predict()[0]
        self.assertEqual((p['baseline'],p['offset_kwh_per_day'],p['predicted'],p['increase'],p['predicted_event_total']),(20,5,25,25,75))
        self.assertEqual(p['past_event_inputs'][0]['increase_percent'],50)
    def test_stable_usage_is_real_zero(self):
        p=self.predict(usage('2024-01-01','2024-01-17',10))[0]
        self.assertEqual(p['increase'],0);self.assertEqual(p['predicted'],10)
    def test_missing_day_is_no_estimate(self):
        p=self.predict(self.rows[:-1])[0]
        self.assertIsNone(p['predicted']);self.assertIsNone(p['increase']);self.assertEqual(p['reason'],'missing_usage_day')
    def test_null_outage_and_interruption_are_not_zero_fill(self):
        for key,value in [('import_kwh',''),('outage_hours','1'),('supply_status','disconnected_non_payment')]:
            rows=copy.deepcopy(self.rows);rows[-1][key]=value
            self.assertIsNone(self.predict(rows)[0]['increase'])
    def test_future_business_rows_cannot_change_estimate(self):
        rows=self.rows+usage('2024-01-18','2024-01-25',99999)
        self.assertEqual(self.predict(rows),self.predict())
    def test_multiple_events_remain_separate_with_duration(self):
        p=self.predict(events=self.future+[event('B','2024-01-23','2024-01-26')])
        self.assertEqual([x['event_id'] for x in p],['A','B']);self.assertEqual([x['predicted_event_total'] for x in p],[75,100])
    def test_partial_target_boundary_is_unavailable(self):
        p=self.predict(events=[event('A','2024-01-19','2024-01-21',end_boundary='continuation_unknown')])[0]
        self.assertEqual(p['reason'],'partial_event_boundary');self.assertIsNone(p['predicted'])
    def test_missing_past_prebaseline_does_not_become_zero_offset(self):
        p=self.predict(self.rows[1:])[0]
        self.assertEqual(p['reason'],'no_complete_past_heat_comparison');self.assertIsNone(p['offset_kwh_per_day'])
    def test_zero_denominator_is_not_zero_percent(self):
        p=self.predict(usage('2024-01-01','2024-01-17',0))[0]
        self.assertEqual(p['reason'],'zero_current_baseline');self.assertIsNone(p['increase'])
    def test_duplicate_and_nonfinite_input_rejected(self):
        with self.assertRaises(InputError):self.predict(self.rows+[self.rows[-1]])
        with self.assertRaises(InputError):number('nan',field='test')
        with self.assertRaises(InputError):number('-1',field='test',nonnegative=True)
    def test_inconsistent_business_row_rejected(self):
        row={'customer_id':'X','date':'2024-01-01','import_kwh':'10','import_peak_kwh':'7','import_offpeak_kwh':'7','import_superoffpeak_kwh':'0','export_kwh':'0','outage_hours':'0','supply_status':'connected'}
        with self.assertRaisesRegex(InputError,'reconcile'):validate_row('consumption_daily',row,{'X'})
    def test_unlinked_and_future_support_do_not_qualify(self):
        tables={'support_needs_history':[],'payment_arrangements':[],'hardship_programs':[],'hugs_grants':[]}
        self.assertEqual(known_support_links(tables,'X',self.past[0],'2024-01-17'),[])
        tables['hugs_grants']=[{'customer_id':'X','hugs_id':'H','application_date':'2024-01-19'}]
        self.assertEqual(known_support_links(tables,'X',self.past[0],'2024-01-17'),[])

class SourceReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot=build_review();cls.weather,cls.provenance=load_weather()
    def test_real_source_and_active_cohort(self):
        r=self.snapshot
        self.assertEqual(len(r['input_validation']['files']),12)
        self.assertEqual(sum(f['source_rows'] for f in r['input_validation']['files']),437278)
        self.assertEqual(len(r['customers']),37)
        self.assertNotIn('C103653',[x['customer']['customer_id'] for x in r['customers']])
        self.assertEqual([(e['start'],e['end']) for e in r['events']],[('2024-11-03','2024-11-05')])
        self.assertIsNone(r['status']['official_bom_category']);self.assertFalse(r['status']['prediction_accuracy_validated'])
    def test_source_calculation_reconciles_independently(self):
        row=next(x for x in self.snapshot['customers'] if x['customer']['customer_id']=='C103794')
        with gzip.open(DEFAULT_SOURCE/'candidate-business-data/consumption_daily.csv.gz','rt') as f:
            values={r['date']:float(r['import_kwh']) for r in csv.DictReader(f) if r['customer_id']=='C103794'}
        recent=[values[(date(2024,10,26)+timedelta(days=i)).isoformat()] for i in range(7)]
        self.assertAlmostEqual(math.fsum(recent)/7,30.755428571428574)
        deltas=[]
        for e in self.snapshot['past_events']:
            a=date.fromisoformat(e['start']);b=date.fromisoformat(e['end'])
            mean_before=math.fsum(values[(a-timedelta(days=i)).isoformat()] for i in range(1,8))/7
            mean_event=math.fsum(values[(a+timedelta(days=i)).isoformat()] for i in range((b-a).days+1))/((b-a).days+1)
            deltas.append(mean_event-mean_before)
        expected=math.fsum(recent)/7+math.fsum(deltas)/len(deltas)
        self.assertAlmostEqual(expected,30.79099107142857)
        self.assertAlmostEqual(row['predictions'][0]['predicted'],expected)
        self.assertAlmostEqual(row['predictions'][0]['increase'],0.11562999331127255)
    def test_no_future_business_or_complete_two_year_claim(self):
        r=self.snapshot
        for row in r['customers']:
            self.assertTrue(all(p['date']<=r['history_cutoff'] for p in row['usage']))
            self.assertTrue(all(p['date']<=r['history_cutoff'] for p in row['records']+row['financial']))
            self.assertEqual(row['history_coverage']['status'],'partial')
            self.assertGreater(row['history_coverage']['missing_days'],0)
        self.assertTrue(r['hindsight_weather']);self.assertEqual(r['status']['current_live_status'],'stale_for_current_use')
    def test_prior_comparisons_are_observed_changes_not_fixture_percentages(self):
        linked=[r for r in self.snapshot['customers'] if r['episodes']]
        self.assertEqual([r['customer']['customer_id'] for r in linked],['C103794'])
        e=linked[0]['episodes'][0]
        self.assertEqual(e['start'],'2024-10-22');self.assertEqual(e['provenance'],'derived_temporal_overlap')
        self.assertAlmostEqual(e['increase_percent'],-7.083573387696418)
        self.assertTrue(e['source_links']);self.assertNotIn('expected_percent_fixture',linked[0])
    def test_january_fixture_events_are_not_falsely_reused(self):
        _,replay,_=event_windows(self.weather,self.provenance,'2025-01-02')
        self.assertEqual(replay['events'],[])
    def test_missing_weather_tail_stays_unknown(self):
        raw=derive(self.weather,self.provenance,'2024-11-03','2024-11-09',weather_cutoff='2024-11-04')
        unknown=[d for d in raw['days'] if d['presence']=='unavailable']
        self.assertTrue(unknown);self.assertTrue(all(d['intensity_k2'] is None for d in unknown))
    def test_missing_bills_are_not_zero_financial_evidence(self):
        row=next(x for x in self.snapshot['customers'] if x['customer']['customer_id']=='C105072')
        self.assertEqual(row['financial'],[])
        self.assertTrue(any(r['kind']=='Support need recorded' for r in row['records']))
    def test_extension_retained_as_assistance_without_lateness_inference(self):
        row=next(x for x in self.snapshot['customers'] if x['customer']['customer_id']=='C102502')
        extension=next(r for r in row['records'] if r['id']=='AR0000857')
        self.assertEqual(extension['kind'],'Bill extension');self.assertEqual(extension['date'],'2024-09-05')
        with (DEFAULT_SOURCE/'candidate-business-data/bills.csv').open() as f:
            bill=next(r for r in csv.DictReader(f) if r['bill_id']=='BI0028116')
        self.assertEqual(bill['original_due_date'],'2024-09-07');self.assertEqual(bill['due_date'],'2024-09-21')
        self.assertEqual(bill['paid_in_full_date'],'2024-09-19');self.assertLessEqual(bill['paid_in_full_date'],bill['due_date'])
        self.assertEqual(row['episodes'],[])
        self.assertFalse(any('late' in r['kind'].lower() for r in row['records']))
        # Policy-only synthetic heat window: proves an extension is not rejected
        # because payment met its adjusted terms. This is NOT a real EHF event.
        tables={'support_needs_history':[],'payment_arrangements':[{'customer_id':'C102502','arrangement_id':'AR0000857','start_date':'2024-09-05'}],'hardship_programs':[],'hugs_grants':[]}
        links=known_support_links(tables,'C102502',event('POLICY-TEST-ONLY','2024-09-05','2024-09-07'),'2024-11-01')
        self.assertEqual(links[0]['source_id'],'AR0000857')

if __name__=='__main__':unittest.main()
