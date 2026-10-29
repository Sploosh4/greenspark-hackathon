import threading,time,unittest,uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from prototype.jobs import UploadJobs
from prototype.uploads import UploadStore,UploadError
from tests.make_upload_fixtures import fixture_parts,mutate

class UploadJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.parts=fixture_parts()
    def setUp(self):self.tmp=TemporaryDirectory();self.store=UploadStore(Path(self.tmp.name));self.jobs=UploadJobs(self.store)
    def tearDown(self):self.jobs.close();self.tmp.cleanup()
    def wait(self,operation):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            status=self.jobs.status(operation)
            if status['state'] not in ('queued','running'):return status
            time.sleep(.01)
        self.fail('Job timed out')
    def test_ack_and_status_remain_fast_while_validation_is_blocked(self):
        entered=threading.Event();release=threading.Event();original=self.store.builder
        def build(path):entered.set();release.wait(3);return original(path)
        self.store.builder=build;operation=uuid.uuid4().hex;start=time.monotonic();self.jobs.submit(self.parts,operation,'none');ack=time.monotonic()-start
        self.assertLess(ack,2);self.assertTrue(entered.wait(2));start=time.monotonic();self.assertEqual(self.jobs.status(operation)['state'],'running');self.assertLess(time.monotonic()-start,2);self.assertIsNone(self.store.status()['active_batch'])
        release.set();self.assertEqual(self.wait(operation)['state'],'ready');self.assertIsNone(self.store.status()['active_batch'])
    def test_repeat_mismatch_and_cancel_are_safe(self):
        operation=uuid.uuid4().hex;self.jobs.submit(self.parts,operation,'none');ready=self.wait(operation);self.assertEqual(ready['state'],'ready')
        self.assertEqual(self.jobs.submit(self.parts,operation,'none')['state'],'ready')
        bad=mutate(self.parts,'customers.csv',lambda h,r:h.reverse())
        with self.assertRaises(UploadError):self.jobs.submit(bad,operation,'none')
        self.jobs.cancel(operation);self.jobs.cancel(operation);self.assertEqual(self.jobs.status(operation)['state'],'cancelled')
        with self.assertRaises(UploadError):self.store.activate(operation,'none')
    def test_failed_validation_and_bounded_worker_queue_preserve_active_data(self):
        bad=mutate(self.parts,'customers.csv',lambda h,r:h.reverse());operation=uuid.uuid4().hex;self.jobs.submit(bad,operation,'none');self.assertEqual(self.wait(operation)['state'],'failed');self.assertIsNone(self.store.status()['active_batch'])
        entered=threading.Event();release=threading.Event()
        def hold(*args,**kwargs):entered.set();release.wait(3);raise UploadError('Stopped test job')
        with patch.object(self.store,'stage',hold):
            a,b=uuid.uuid4().hex,uuid.uuid4().hex;self.jobs.submit(self.parts,a,'none');self.jobs.submit(self.parts,b,'none');self.assertTrue(entered.wait(2))
            with self.assertRaises(UploadError) as error:self.jobs.submit(self.parts,uuid.uuid4().hex,'none')
            self.assertEqual(error.exception.status,429);release.set();self.wait(a);self.wait(b)
    def test_cancelled_running_work_still_counts_until_it_releases_parts(self):
        entered=threading.Barrier(3);release=threading.Event()
        def hold(*args,**kwargs):entered.wait(3);release.wait(3);raise UploadError('Stopped test job')
        with patch.object(self.store,'stage',hold):
            a,b=uuid.uuid4().hex,uuid.uuid4().hex;self.jobs.submit(self.parts,a,'none');self.jobs.submit(self.parts,b,'none');entered.wait(3)
            self.jobs.cancel(a);self.jobs.cancel(b)
            for _ in range(20):
                with self.assertRaises(UploadError) as error:self.jobs.submit(self.parts,uuid.uuid4().hex,'none')
                self.assertEqual(error.exception.status,429)
            self.assertEqual(len(self.jobs.inflight),2);self.assertEqual(len(self.jobs.jobs),2);release.set()
