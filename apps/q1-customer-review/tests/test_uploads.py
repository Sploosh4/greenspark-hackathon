from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import copy,gzip,json,threading,unittest,uuid
from prototype.uploads import UploadStore,UploadError,check_extra
from tests.make_upload_fixtures import fixture_parts,mutate

def op():return uuid.uuid4().hex

class UploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=fixture_parts();cls.b=fixture_parts(('C103794','C105072'),True)
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name);self.store=UploadStore(self.root)
    def tearDown(self):self.tmp.cleanup()
    def stage(self,parts=None,store=None):
        s=store or self.store;return s.stage(parts or self.a,op(),s.status()['revision'])
    def activate(self,parts=None):
        r=self.stage(parts);return self.store.activate(r['stage_id'],r['expected_revision'])
    def test_stage_has_no_effect_then_confirmed_activation_and_exact_calculation(self):
        r=self.stage();self.assertIsNone(self.store.status()['active_batch'])
        self.assertEqual(r['summary']['source_customers'],1)
        state=self.store.activate(r['stage_id'],'none');view=self.store.view(state['revision'])
        p=view['customers'][0]['predictions'][0]
        self.assertAlmostEqual(p['predicted'],30.79099107142857)
        self.assertEqual(view['batch_id'],state['active_batch']);self.assertTrue(Path(view['input_validation']['source_root']).is_dir())
        self.assertEqual(self.store.activate(r['stage_id'],'none'),state)
    def test_new_counts_and_changed_input_are_accepted_without_demo_hash_reuse(self):
        self.activate();state=self.activate(self.b);r=self.store.view()
        self.assertEqual(len(r['customers']),2);self.assertAlmostEqual(r['customers'][0]['predictions'][0]['predicted'],31.79099107142857)
        self.assertTrue(state['previous_available'])
    def test_cancel_before_and_after_validation_never_activates(self):
        request=op();self.store.cancel(request)
        with self.assertRaises(UploadError):self.store.stage(self.a,request,'none')
        r=self.stage();self.store.cancel(r['stage_id'])
        with self.assertRaises(UploadError):self.store.activate(r['stage_id'],'none')
        self.assertIsNone(self.store.status()['active_batch'])
    def test_cancel_while_calculation_is_running(self):
        entered=threading.Event();release=threading.Event();errors=[];original=self.store.builder
        def build(path):entered.set();release.wait(3);return original(path)
        self.store.builder=build;request=op()
        def run():
            try:self.store.stage(self.a,request,'none')
            except UploadError as e:errors.append(str(e))
        t=threading.Thread(target=run);t.start();self.assertTrue(entered.wait(3));self.store.cancel(request);release.set();t.join(5)
        self.assertEqual(errors,['Upload cancelled']);self.assertIsNone(self.store.status()['active_batch'])
    def test_bad_schemas_links_dates_and_parent_links_keep_current_batch(self):
        state=self.activate()
        cases=[mutate(self.a,'customers.csv',lambda h,r:h.reverse()),
          mutate(self.a,'payments.csv',lambda h,r:r[0].update(customer_id='unknown')),
          mutate(self.a,'payments.csv',lambda h,r:r[0].update(date='2024-99-99')),
          mutate(self.a,'support_arrangement_history.csv',lambda h,r:r[0].update(arrangement_id='absent')),
          mutate(self.a,'customers.csv',lambda h,r:r[0].update(prepayment_meter='yes'))]
        for parts in cases:
            with self.assertRaises(UploadError):self.stage(parts)
            self.assertEqual(self.store.status()['revision'],state['revision'])
    def test_complete_file_set_duplicate_path_archive_and_corrupt_gzip(self):
        cases=[self.a[:-1],self.a[:-1]+[self.a[0]],[('../customers.csv',self.a[0][1])]+self.a[1:],[('all.zip',self.a[0][1])]+self.a[1:]]
        bad=list(self.a);i=next(i for i,(n,_) in enumerate(bad) if n.endswith('.gz'));bad[i]=(bad[i][0],bad[i][1][:-5]);cases.append(bad)
        for parts in cases:
            with self.assertRaises(UploadError):self.stage(parts)
        self.assertIsNone(self.store.status()['active_batch'])
    def test_decoded_limit_and_oversize_are_bounded(self):
        with patch('prototype.uploads.MAX_FILE',10):
            with self.assertRaises(UploadError):self.stage()
        with patch('prototype.uploads.MAX_DECODED',100):
            with self.assertRaises(UploadError):self.stage()
    def test_duplicate_operation_and_identical_batch_do_not_replace_twice(self):
        request=op();r=self.store.stage(self.a,request,'none');self.assertEqual(r,self.store.stage(self.a,request,'none'))
        with self.assertRaises(UploadError):self.store.stage(self.b,request,'none')
        state=self.store.activate(request,'none');second=self.stage()
        result=self.store.activate(second['stage_id'],state['revision']);self.assertTrue(result['unchanged']);self.assertEqual(result['revision'],state['revision'])
    def test_stale_activation_export_and_recovery_are_rejected(self):
        stale=self.stage();state=self.activate(self.b)
        with self.assertRaises(UploadError):self.store.activate(stale['stage_id'],'none')
        with self.assertRaises(UploadError):self.store.view('none')
        with self.assertRaises(UploadError):self.store.rollback(op(),'none')
        self.assertEqual(self.store.status()['revision'],state['revision'])
    def test_restart_and_explicit_rollback_restore_last_good(self):
        first=self.activate();second=self.activate(self.b);s=UploadStore(self.root)
        self.assertEqual(s.status()['revision'],second['revision']);self.assertEqual(len(s.view()['customers']),2)
        request=op();restored=s.rollback(request,second['revision']);self.assertEqual(restored['active_batch'],first['active_batch']);self.assertEqual(len(s.view()['customers']),1)
        self.assertEqual(s.rollback(request,second['revision']),restored)
    def test_corrupt_active_or_pointer_recovers_previous_without_demo_substitution(self):
        for corrupt in ('review','pointer','missing_pointer'):
            with self.subTest(corrupt=corrupt),TemporaryDirectory() as root:
                s=UploadStore(root);r=s.stage(self.a,op(),'none');first=s.activate(r['stage_id'],'none');r=s.stage(self.b,op(),first['revision']);second=s.activate(r['stage_id'],first['revision'])
                path=Path(root)/('state.json' if corrupt in ('pointer','missing_pointer') else 'batches/'+second['active_batch']+'/review.json')
                if corrupt=='missing_pointer':path.unlink()
                else:path.write_text('{broken')
                recovered=UploadStore(root);self.assertEqual(recovered.status()['active_batch'],first['active_batch']);self.assertTrue(recovered.status()['recovery']);self.assertEqual(recovered.view()['data_mode'],'upload')
    def test_interrupted_activation_recovers_only_complete_pointer(self):
        for phase in ('snapshot_ready','backup_written','pointer_switched'):
            with self.subTest(phase=phase),TemporaryDirectory() as root:
                s=UploadStore(root);r=s.stage(self.a,op(),'none');first=s.activate(r['stage_id'],'none');r=s.stage(self.b,op(),first['revision'])
                def fault(current):
                    if current==phase:raise RuntimeError('simulated process interruption')
                s.fault=fault
                with self.assertRaises(RuntimeError):s.activate(r['stage_id'],first['revision'])
                recovered=UploadStore(root);self.assertEqual(len(recovered.view()['customers']),2 if phase=='pointer_switched' else 1)
    def test_missing_usage_is_an_unavailable_estimate_and_topup_date_is_checked(self):
        parts=mutate(self.a,'consumption_daily.csv.gz',lambda h,r:r.__setitem__(slice(None),[x for x in r if x['date']!='2024-11-01']))
        self.activate(parts);p=self.store.view()['customers'][0]['predictions'][0];self.assertIsNone(p['increase']);self.assertEqual(p['reason'],'missing_usage_day')
        with self.assertRaises(ValueError):check_extra('prepay_topups',{'datetime':'not-a-date'})
        check_extra('prepay_topups',{'datetime':'2023-07-01 10:30:00'})
        check_extra('prepay_topups',{'datetime':'2023-07-02 14:00'})
    def test_same_process_retry_after_pre_pointer_failure(self):
        for phase in ('snapshot_ready','backup_written'):
            with self.subTest(phase=phase),TemporaryDirectory() as root:
                s=UploadStore(root);r=s.stage(self.a,op(),'none');state=s.activate(r['stage_id'],'none');r=s.stage(self.b,op(),state['revision']);failed=[]
                def fault(current):
                    if current==phase and not failed:failed.append(True);raise OSError('one transient failure')
                s.fault=fault
                with self.assertRaises(OSError):s.activate(r['stage_id'],state['revision'])
                self.assertEqual(s.status()['revision'],state['revision'])
                result=s.activate(r['stage_id'],state['revision']);self.assertEqual(len(s.view()['customers']),2)
                self.assertEqual(s.activate(r['stage_id'],state['revision']),result)
    def test_sync_error_after_atomic_rename_reports_the_committed_version(self):
        import prototype.uploads as uploads
        first=self.activate();r=self.stage(self.b);original=uploads.write_json
        def fail_after_rename(path,value):
            original(path,value)
            if Path(path).name=='state.json':raise OSError('simulated directory sync failure')
        with patch('prototype.uploads.write_json',fail_after_rename):
            with self.assertRaises(OSError):self.store.activate(r['stage_id'],first['revision'])
        self.assertNotEqual(self.store.status()['revision'],first['revision']);self.assertEqual(len(self.store.view()['customers']),2)
        self.assertTrue(self.store.status()['recovery'])
        self.assertEqual(self.store.activate(r['stage_id'],first['revision'])['revision'],self.store.status()['revision'])

if __name__=='__main__':unittest.main()
