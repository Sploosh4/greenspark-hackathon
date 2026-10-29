"""Bounded public-source transport fixtures; no actual download in tests."""
import copy,json,hashlib,threading,time
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from prototype.public_weather import PERTH,LAT,LON,PAST_DAYS,FORECAST_DAYS,normalise,window,WeatherError,PublicWeatherStore,MAX_BYTES
from prototype.public_source import PublicSourceStore,request_url,wrap,download,NoRedirect
from prototype.weather_job import DailyCacheJob

NOW=datetime(2026,10,29,3,tzinfo=PERTH)
def payload():
 start=(NOW-timedelta(days=PAST_DAYS)).replace(hour=0)
 return {'latitude':LAT,'longitude':LON,'timezone':'Australia/Perth','utc_offset_seconds':28800,'generationtime_ms':.1,'hourly_units':{'time':'iso8601','temperature_2m':'°C'},'hourly':{'time':[(start+timedelta(hours=i)).isoformat()[:16] for i in range(24*(PAST_DAYS+FORECAST_DAYS))],'temperature_2m':[20+i%24/2 for i in range(24*(PAST_DAYS+FORECAST_DAYS))]}}
def raw():return json.dumps(payload()).encode()
def fetched(url):return raw(),{'http_date':'Thu, 29 Oct 2026 00:00:00 GMT'}
def store(root,fetch=fetched):return PublicSourceStore(root,fetch=fetch,clock=lambda:NOW,source_cache=Path(root)/'absent')

class PublicSourceTests(unittest.TestCase):
 def test_exact_buffer_and_unknown_issue_not_observations(self):
  value=wrap(payload(),NOW,NOW,request_url(),'a'*64,{'http_date':NOW.isoformat()});d=normalise(value);v=window(d,NOW)
  self.assertEqual(v['status']['complete_target_days'],7);self.assertEqual(v['context_coverage']['complete_prior_calendar_days'],35)
  self.assertEqual(v['context_coverage']['nine_am_window_coverage']['prior_complete'],32);self.assertEqual(v['context_coverage']['nine_am_window_coverage']['target_complete'],7);self.assertEqual(v['context_coverage']['nine_am_window_coverage']['boundary_tail_complete'],3)
  self.assertEqual(d['valid_from'],'2026-09-24T00:00:00+08:00');self.assertEqual(d['valid_until_exclusive'],'2026-11-10T00:00:00+08:00')
  self.assertEqual(d['hourly'][0]['kind'],'archived_model_forecast');self.assertEqual(d['hourly'][-1]['kind'],'model_forecast')
  self.assertFalse(d['observed_warmup_available']);self.assertFalse(d['calibration_compatible']);self.assertIsNone(d['model_issued_at']);self.assertFalse(v['current_customer_estimates_available'])
 def test_atomic_raw_snapshot_reuse_restart_and_new_day_refresh(self):
  with TemporaryDirectory() as root:
   calls=[]
   s=store(root,lambda u:(calls.append(u) or fetched(u)));first=s.refresh();self.assertTrue(first['succeeded']);self.assertFalse(first['cache_reused'])
   saved=(Path(root)/'downloads'/(hashlib.sha256(raw()).hexdigest()+'.json'));self.assertEqual(saved.read_bytes(),raw())
   self.assertTrue(s.refresh()['cache_reused']);self.assertEqual(len(calls),1)
   job=DailyCacheJob(s).tick(NOW);self.assertFalse(job['network_fetch']);self.assertTrue(job['cache_reused']);self.assertEqual(len(calls),1)
   restored=store(root,lambda u:self.fail('Fresh saved context should be reused'));self.assertTrue(restored.refresh()['cache_reused'])
   s.clock=lambda:NOW+timedelta(days=1)
   self.assertFalse(s.refresh()['succeeded']);self.assertEqual(len(calls),2) # response is now old, never shifted
   self.assertEqual(saved.read_bytes(),raw())
 def test_failure_preserves_pointer_and_is_visible_after_restart(self):
  with TemporaryDirectory() as root:
   s=store(root);self.assertTrue(s.refresh()['succeeded']);pointer=(Path(root)/'latest.json').read_bytes()
   s.clock=lambda:NOW+timedelta(days=1)
   def fail(url):raise WeatherError('public_source_http_503')
   s.fetch=fail;result=s.refresh();self.assertFalse(result['succeeded']);self.assertEqual((Path(root)/'latest.json').read_bytes(),pointer)
   self.assertEqual(store(root).view(NOW)['status']['last_error'],'public_source_http_503')
 def test_slow_refresh_does_not_block_last_good_view_or_duplicate_download(self):
  with TemporaryDirectory() as root:
   s=store(root);self.assertTrue(s.refresh()['succeeded']);s.clock=lambda:NOW+timedelta(days=1)
   entered=threading.Event();release=threading.Event();calls=[]
   def slow(url):
    calls.append(url);entered.set();release.wait(2);raise WeatherError('public_source_transport_failed')
   s.fetch=slow;worker=threading.Thread(target=s.refresh);worker.start()
   try:
    self.assertTrue(entered.wait(1));start=time.monotonic();view=s.view(NOW)
    self.assertLess(time.monotonic()-start,.2);self.assertEqual(view['status']['complete_target_days'],7)
    self.assertEqual(s.refresh()['error'],'public_source_refresh_in_progress');self.assertEqual(len(calls),1)
   finally:release.set();worker.join(2)
   self.assertFalse(worker.is_alive());self.assertEqual(s.view(NOW)['status']['last_error'],'public_source_transport_failed')
 def test_invalid_bounds_duplicates_nulls_and_malformed_response(self):
  for kind in ['truncated','duplicate','badunit','issued','query','null','badjson','oversize']:
   with self.subTest(kind=kind),TemporaryDirectory() as root:
    p=payload()
    if kind=='truncated':p['hourly']['time']=p['hourly']['time'][:-1];p['hourly']['temperature_2m']=p['hourly']['temperature_2m'][:-1]
    if kind=='duplicate':p['hourly']['time'][1]=p['hourly']['time'][0]
    if kind=='badunit':p['hourly_units']['temperature_2m']='°F'
    if kind=='null':p['hourly']['temperature_2m'][36*24]=None
    body=b'{' if kind=='badjson' else b' '*(MAX_BYTES+1) if kind=='oversize' else json.dumps(p).encode()
    if kind in ['issued','query']:
     x=wrap(p,NOW,NOW,request_url(),'a'*64,{})
     if kind=='issued':x['model_issued_at']=NOW.isoformat()
     else:x['source_url']+='&apikey=notallowed'
     with self.assertRaises(WeatherError):normalise(x)
    else:
     s=store(root,lambda url:(body,{}));result=s.refresh();self.assertEqual(result['succeeded'],kind=='null')
     if kind=='null':self.assertEqual(s.view(NOW)['status']['complete_target_days'],6)
 def test_job_declares_network_and_retry_without_double_submission(self):
  with TemporaryDirectory() as root:
   calls=[]
   def fail(url):calls.append(url);raise WeatherError('public_source_transport_failed')
   s=store(root,fail);job=DailyCacheJob(s);result=job.tick(NOW);self.assertTrue(result['network_fetch']);self.assertEqual(result['operation'],'refresh_bounded_public_model_context')
   self.assertFalse(job.tick(NOW+timedelta(minutes=1))['ran']);self.assertEqual(len(calls),1)
   self.assertTrue(job.tick(NOW+timedelta(minutes=15))['ran']);self.assertEqual(len(calls),2)
 def test_unknown_urls_and_redirects_rejected_without_network(self):
  with self.assertRaises(WeatherError):download('http://127.0.0.1:8891/')
  with self.assertRaises(WeatherError):NoRedirect().redirect_request(None,None,None,None,None,None)
 def test_background_start_returns_while_provider_is_blocked(self):
  with TemporaryDirectory() as root:
   s=store(root);entered=threading.Event();release=threading.Event();stop=threading.Event()
   def slow(url):entered.set();release.wait(2);raise WeatherError('public_source_transport_failed')
   s.fetch=slow;job=DailyCacheJob(s);start=time.monotonic();worker=job.start(stop,force_initial=True)
   try:
    self.assertLess(time.monotonic()-start,.2);self.assertTrue(entered.wait(1));self.assertTrue(worker.is_alive());self.assertIsNone(s.view(NOW)['source'])
   finally:stop.set();release.set();worker.join(2)
   self.assertFalse(worker.is_alive())
 def test_only_one_fixed_town_no_business_identifiers_or_credentials_in_url(self):
  from urllib.parse import parse_qs,urlsplit
  u=urlsplit(request_url());q=parse_qs(u.query)
  self.assertEqual(u.hostname,'api.open-meteo.com');self.assertEqual(q['latitude'],[str(LAT)]);self.assertEqual(q['longitude'],[str(LON)])
  self.assertEqual(set(q),{'latitude','longitude','hourly','timezone','timeformat','temperature_unit','past_days','forecast_days'})

if __name__=='__main__':unittest.main()
