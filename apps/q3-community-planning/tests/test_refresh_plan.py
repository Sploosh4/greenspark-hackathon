import unittest
import test_source_adapter as fixtures
from datetime import date
from refresh_plan import plan_release,replacement_decision,months
from source_adapter import SourceError

class RefreshPlan(unittest.TestCase):
 def plan(self,**kwargs):return plan_release(date(2026,11,8),'2026-10','2026-11',{'mean':True,'anomaly':True},**kwargs)
 def test_no_configuration_no_retrieval(self):self.assertEqual(self.plan()['action'],'configuration_review_required');self.assertFalse(self.plan()['submitJob'])
 def test_nominal_release_and_configurable_lag(self):self.assertEqual(self.plan(reviewed_lag_days=3)['action'],'wait_for_nominal_release_plus_lag');self.assertEqual(self.plan(reviewed_lag_days=2)['action'],'ready_for_reviewed_retrieval')
 def test_wait_for_both_products(self):self.assertEqual(plan_release(date(2026,11,10),'2026-10','2026-11',{'mean':True,'anomaly':False},reviewed_lag_days=1)['action'],'wait_for_both_sources')
 def test_deduplicate_success_and_inflight(self):
  key=self.plan()['key'];self.assertEqual(self.plan(successful=[key])['action'],'already_successful_or_older');self.assertEqual(self.plan(in_flight=[key])['action'],'already_in_flight')
 def test_existing_download_not_submitted(self):self.assertEqual(plan_release(date(2026,10,28),'2026-10','2026-10',{'mean':True,'anomaly':True})['action'],'already_successful_or_older')
 def test_year_boundary_months(self):self.assertEqual(months('2026-11'),['2026-11','2026-12','2027-01','2027-02','2027-03','2027-04'])
 def test_mixed_or_invalid_pack_rejected(self):
  candidate={'issueMonth':'2026-11','meanIssueMonth':'2026-11','anomalyIssueMonth':'2026-10','validMonths':months('2026-11'),'gridAligned':True,'unitsValidated':True,'hashesVerified':True,'missingnessValidated':True}
  with self.assertRaisesRegex(SourceError,'mixed_issue_pack'):replacement_decision(candidate,'2026-10')
  candidate['anomalyIssueMonth']='2026-11';self.assertEqual(replacement_decision(candidate,'2026-10'),'candidate_ready_for_atomic_validation');candidate['missingnessValidated']=False
  with self.assertRaises(SourceError):replacement_decision(candidate,'2026-10')
 def test_invalid_lag_and_availability_rejected(self):
  with self.assertRaises(SourceError):self.plan(reviewed_lag_days=-1)
  with self.assertRaises(SourceError):plan_release(date(2026,11,10),'2026-10','2026-11',{'mean':'yes','anomaly':True},reviewed_lag_days=1)
