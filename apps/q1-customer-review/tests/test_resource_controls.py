"""Security regressions use disposable synthetic stores, never active uploads."""
import hashlib,json,threading,time,uuid,unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from prototype.uploads import UploadStore,UploadError,RetentionLimits,SPECS,METADATA_RESERVATION,validate_files
from prototype.jobs import UploadJobs
from prototype.inputs import DEFAULT_SOURCE,load_business
from prototype.review import build_review,customer_index,records_at
from prototype.work import WorkControl,WorkCancelled,WorkLimit,work_scope,checkpoint
from tests.make_upload_fixtures import fixture_parts,mutate,encode_rows

def operation():return uuid.uuid4().hex
def small_review(path):
    return {'input_validation':{},'customers':[],'events':[],'review_date':'2024-11-02','method':{'id':'resource-regression-fixture'}}

def generated_cohort(n):
    """Schema-valid synthetic cohort; all payment rows belong to the first ID."""
    customers=[]
    for i in range(n):
        row={h:'' for h in SPECS[0]['ordered_headers']}
        row.update(customer_id=f'Q{i:07}',postcode='6765',locality='Fitzroy Crossing',account_open_date='2023-01-01')
        for key in ('prepayment_meter','has_solar','concession_card','life_support','medical_cooling_subsidy','interpreter_required'):row[key]='False'
        customers.append(row)
    result=[]
    for spec in SPECS:
        rows=customers if spec['table']=='customers' else []
        if spec['table']=='payments':
            rows=[{h:{'payment_id':f'QP{i:07}','customer_id':'Q0000000','date':'2024-01-01','amount':'0','status':'cleared'}.get(h,'') for h in spec['ordered_headers']} for i in range(2*n)]
        result.append((spec['filename'],encode_rows(spec['filename'],spec['ordered_headers'],rows)))
    return result

class CountedRows(list):
    def __init__(self,rows):super().__init__(rows);self.visits=0
    def __iter__(self):
        for row in super().__iter__():self.visits+=1;yield row

class ResourceControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.parts=fixture_parts()
    def wait(self,jobs,op):
        end=time.monotonic()+10
        while time.monotonic()<end:
            result=jobs.status(op)
            if result['state'] not in ('queued','running'):return result
            time.sleep(.002)
        self.fail('Temporary fixture worker did not finish')

    def test_132_stages_cannot_grow_disk_or_store_metadata_beyond_limits(self):
        with TemporaryDirectory() as root:
            store=UploadStore(root,builder=small_review);jobs=UploadJobs(store);ready=0;rejected=0
            try:
                for _ in range(132):
                    op=operation();jobs.submit(self.parts,op,'none');result=self.wait(jobs,op)
                    ready+=result['state']=='ready';rejected+=result['state']=='failed'
                status=store.status();self.assertEqual(ready,store.limits.snapshots);self.assertEqual(rejected,132-ready)
                self.assertLessEqual(status['retention']['snapshots'],store.limits.snapshots);self.assertLessEqual(status['retention']['bytes'],store.limits.bytes)
                self.assertLessEqual(len(store.jobs),128);self.assertLessEqual(len(jobs.jobs),128);self.assertLessEqual(len(store.cache),2)
                self.assertIsNone(status['active_batch'])
            finally:jobs.close()

    def test_direct_stage_byte_reservation_rejects_before_a_second_copy(self):
        reservation=sum(len(raw) for _,raw in self.parts)+4096+METADATA_RESERVATION
        limits=replace(RetentionLimits(),bytes=reservation+10,review_bytes=4096)
        with TemporaryDirectory() as root:
            store=UploadStore(root,builder=small_review,limits=limits);store.stage(self.parts,operation(),'none')
            before=store.status()['retention']
            with self.assertRaises(UploadError) as error:store.stage(self.parts,operation(),'none')
            self.assertEqual(error.exception.status,429);self.assertEqual(store.status()['retention'],before)

    def test_inflight_reservations_are_charged_before_files_are_complete(self):
        reservation=sum(len(raw) for _,raw in self.parts)+4096+METADATA_RESERVATION
        limits=replace(RetentionLimits(),bytes=reservation+10,review_bytes=4096)
        entered=threading.Event();release=threading.Event();errors=[]
        def held(path):entered.set();release.wait(2);return small_review(path)
        with TemporaryDirectory() as root:
            store=UploadStore(root,builder=held,limits=limits)
            def run():
                try:store.stage(self.parts,operation(),'none')
                except Exception as error:errors.append(error)
            worker=threading.Thread(target=run);worker.start()
            try:
                self.assertTrue(entered.wait(1))
                with self.assertRaises(UploadError) as error:store.stage(self.parts,operation(),'none')
                self.assertEqual(error.exception.status,429)
            finally:release.set();worker.join(3)
            self.assertFalse(errors)

    def test_expiry_is_recoverable_and_quarantine_still_counts_against_quota(self):
        now=[1000];limits=replace(RetentionLimits(),snapshots=1,stage_ttl_seconds=10)
        with TemporaryDirectory() as root:
            store=UploadStore(root,builder=small_review,limits=limits,clock=lambda:now[0]);jobs=UploadJobs(store);op=operation()
            try:
                jobs.submit(self.parts,op,'none');self.assertEqual(self.wait(jobs,op)['state'],'ready')
                before={str(p.relative_to(store.staging/op)):p.read_bytes() for p in (store.staging/op).rglob('*') if p.is_file()}
                now[0]+=11;status=store.status();self.assertEqual(jobs.status(op)['state'],'expired');self.assertNotIn(op,store.jobs)
                saved=store.quarantine/('stage-'+op);self.assertTrue(saved.is_dir());self.assertFalse((store.staging/op).exists())
                self.assertEqual(before,{str(p.relative_to(saved)):p.read_bytes() for p in saved.rglob('*') if p.is_file()})
                self.assertEqual(status['retention']['quarantined'],1)
                with self.assertRaises(UploadError):store.activate(op,'none')
                with self.assertRaises(UploadError) as error:store.stage(self.parts,operation(),'none')
                self.assertEqual(error.exception.status,429)
            finally:jobs.close()

    def test_restart_preserves_unknown_staging_in_quarantine(self):
        with TemporaryDirectory() as root:
            store=UploadStore(root);op=operation();folder=store.staging/op;folder.mkdir();(folder/'original-upload.bin').write_bytes(b'preserve these bytes')
            restarted=UploadStore(root);self.assertEqual((restarted.quarantine/('stage-'+op)/'original-upload.bin').read_bytes(),b'preserve these bytes')
            self.assertEqual(restarted.status()['retention']['snapshots'],1)

    def test_disappearing_scratch_stat_does_not_fail_status_or_release_reservation(self):
        import os
        reservation=sum(len(raw) for _,raw in self.parts)+4096+METADATA_RESERVATION
        limits=replace(RetentionLimits(),bytes=reservation+10,review_bytes=4096);entered=threading.Event();release=threading.Event();errors=[]
        def held(path):entered.set();release.wait(2);return small_review(path)
        with TemporaryDirectory() as root:
            store=UploadStore(root,builder=held,limits=limits);op=operation()
            def run():
                try:store.stage(self.parts,op,'none')
                except Exception as error:errors.append(error)
            worker=threading.Thread(target=run);worker.start();original=os.stat
            def vanished(path,*args,**kwargs):
                if Path(path).name=='customers.csv' and kwargs.get('follow_symlinks') is False:raise FileNotFoundError('Atomic scratch rename fixture')
                return original(path,*args,**kwargs)
            try:
                self.assertTrue(entered.wait(1))
                with patch('prototype.uploads.os.stat',side_effect=vanished):
                    self.assertIsNone(store.status()['active_batch'])
                    with self.assertRaises(UploadError) as error:store.stage(self.parts,operation(),'none')
                    self.assertEqual(error.exception.status,429)
            finally:release.set();worker.join(3)
            self.assertFalse(errors)

    def test_moved_precommit_retry_is_pinned_past_stage_expiry(self):
        now=[1000]
        with TemporaryDirectory() as root:
            store=UploadStore(root,clock=lambda:now[0],limits=replace(RetentionLimits(),stage_ttl_seconds=1));r=store.stage(self.parts,operation(),'none')
            def fail(phase):
                if phase=='snapshot_ready':raise OSError('Precommit retry fixture')
            store.fault=fail
            with self.assertRaises(OSError):store.activate(r['stage_id'],'none')
            now[0]+=10;self.assertIsNone(store.status()['active_batch']);self.assertIn(r['stage_id'],store.jobs)
            self.assertTrue((store.batches/r['stage_id']).is_dir());store.fault=lambda phase:None
            result=store.activate(r['stage_id'],'none');self.assertEqual(result['active_batch'],r['stage_id'])

    def test_distinct_batch_quota_cache_restart_and_rollback_keep_all_references(self):
        with TemporaryDirectory() as root:
            limits=replace(RetentionLimits(),snapshots=4);store=UploadStore(root,limits=limits);states=[]
            for i in range(4):
                parts=mutate(self.parts,'payments.csv',lambda h,rows:[row.update(amount=str(i)) for row in rows])
                r=store.stage(parts,operation(),store.status()['revision']);states.append(store.activate(r['stage_id'],r['expected_revision']))
                self.assertLessEqual(len(store.cache),2)
            paths={bid:{str(p.relative_to(store.batches/bid)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.batches/bid).rglob('*') if p.is_file()} for bid in [s['active_batch'] for s in states]}
            with self.assertRaises(UploadError):store.stage(self.parts,operation(),store.state['revision'])
            restarted=UploadStore(root,limits=limits);self.assertEqual(restarted.status()['active_batch'],states[-1]['active_batch'])
            rollback=restarted.rollback(operation(),restarted.state['revision']);self.assertEqual(rollback['active_batch'],states[-2]['active_batch'])
            for bid,hashes in paths.items():self.assertEqual(hashes,{str(p.relative_to(store.batches/bid)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.batches/bid).rglob('*') if p.is_file()})
            self.assertLessEqual(len(restarted.cache),2)

    def test_terminal_metadata_and_generated_review_size_are_bounded(self):
        with TemporaryDirectory() as root:
            store=UploadStore(root,builder=small_review,limits=replace(RetentionLimits(),jobs=8))
            bad=mutate(self.parts,'customers.csv',lambda headers,rows:headers.reverse())
            for _ in range(20):
                with self.assertRaises(UploadError):store.stage(bad,operation(),'none')
            self.assertLessEqual(len(store.jobs),8);self.assertEqual(store.status()['retention']['snapshots'],0)
            store.limits=replace(store.limits,review_bytes=100)
            with self.assertRaises(UploadError) as error:store.stage(self.parts,operation(),'none')
            self.assertEqual(error.exception.status,413);self.assertEqual(store.status()['retention']['snapshots'],0)

    def test_real_review_payment_visits_are_linear_and_source_order_is_preserved(self):
        visits=[]
        for n in (50,100,200):
            with TemporaryDirectory() as root:
                validate_files(generated_cohort(n),Path(root));tables,audit=load_business(root);counted=CountedRows(tables['payments']);tables['payments']=counted
                with patch('prototype.review.load_business',return_value=(tables,audit)):review=build_review(root,weather_root=DEFAULT_SOURCE)
                self.assertEqual(len(review['customers']),n);self.assertEqual(counted.visits,2*n);visits.append(counted.visits)
                self.assertEqual([r['id'] for r in review['customers'][0]['records']],[r['payment_id'] for r in list.__iter__(counted)])
        self.assertEqual(visits,[100,200,400])

    def test_cancellation_during_real_indexing_releases_both_slots_without_marker_eviction(self):
        parts=generated_cohort(5000);gate=threading.Barrier(3);original=load_business
        class GatedRows(list):
            def __iter__(self):
                for i,row in enumerate(super().__iter__()):
                    if i==256:gate.wait(5)
                    yield row
        def loaded(*args,**kwargs):
            tables,audit=original(*args,**kwargs);tables['payments']=GatedRows(tables['payments']);return tables,audit
        with TemporaryDirectory() as root:
            store=UploadStore(root);r=store.stage(self.parts,operation(),'none');store.activate(r['stage_id'],'none')
            state=(Path(root)/'state.json').read_bytes();backup=(Path(root)/'last-good.json').read_bytes();revision=store.state['revision'];jobs=UploadJobs(store);ops=[operation(),operation()]
            try:
                with patch('prototype.review.load_business',side_effect=loaded):
                    for op in ops:jobs.submit(parts,op,revision)
                    gate.wait(5);start=time.monotonic()
                    for op in ops:jobs.cancel(op)
                    for _ in range(200):store.cancel(operation())
                    until=time.monotonic()+2
                    while jobs.inflight and time.monotonic()<until:time.sleep(.002)
                    self.assertFalse(jobs.inflight);self.assertLess(time.monotonic()-start,2)
                for op in ops:self.assertEqual(jobs.status(op)['state'],'cancelled')
                next_op=operation();jobs.submit(self.parts,next_op,revision);self.assertEqual(self.wait(jobs,next_op)['state'],'ready')
                self.assertEqual((Path(root)/'state.json').read_bytes(),state);self.assertEqual((Path(root)/'last-good.json').read_bytes(),backup)
                self.assertEqual(store.view()['batch_revision'],revision)
            finally:jobs.close()

    def test_deadline_work_limit_and_loader_cancel_are_cooperative(self):
        with TemporaryDirectory() as root:
            validate_files(generated_cohort(100),Path(root));cancel=threading.Event();control=WorkControl(cancel.is_set,max_steps=10)
            with work_scope(control),self.assertRaises(WorkLimit):build_review(root,weather_root=DEFAULT_SOURCE)
            ticks=[0]
            def clock():ticks[0]+=.01;return ticks[0]
            with work_scope(WorkControl(cancel.is_set,seconds=.05,clock=clock)),self.assertRaises(WorkLimit):build_review(root,weather_root=DEFAULT_SOURCE)
            original_validate=__import__('prototype.inputs',fromlist=['validate_row']).validate_row;seen=[0]
            def validate(*args):
                original_validate(*args);seen[0]+=1
                if seen[0]==20:cancel.set()
            with patch('prototype.inputs.validate_row',side_effect=validate),work_scope(WorkControl(cancel.is_set)),self.assertRaises(WorkCancelled):load_business(root)

    def test_calculation_deadline_failure_releases_worker_and_preserves_current_pointers(self):
        class ExpiredCalculation(WorkControl):
            def calculation(self):super().calculation();self.deadline=self.clock()-1
        with TemporaryDirectory() as root:
            store=UploadStore(root);r=store.stage(self.parts,operation(),'none');store.activate(r['stage_id'],'none');revision=store.state['revision']
            saved={name:(Path(root)/name).read_bytes() for name in ('state.json','last-good.json')};jobs=UploadJobs(store)
            try:
                with patch('prototype.uploads.WorkControl',ExpiredCalculation):
                    op=operation();jobs.submit(self.parts,op,revision);result=self.wait(jobs,op)
                    self.assertEqual(result['state'],'failed');self.assertIn('budget',result['error'])
                until=time.monotonic()+2
                while jobs.inflight and time.monotonic()<until:time.sleep(.002)
                self.assertFalse(jobs.inflight)
                op=operation();jobs.submit(self.parts,op,revision);self.assertEqual(self.wait(jobs,op)['state'],'ready')
                for name,raw in saved.items():self.assertEqual((Path(root)/name).read_bytes(),raw)
                self.assertEqual(store.view()['batch_revision'],revision)
            finally:jobs.close()

    def test_large_index_has_bounded_visits_and_workload_limits_reject_safely(self):
        rows=CountedRows([{'customer_id':f'Q{i%50000:07}','payment_id':str(i),'date':'2024-01-01','status':'cleared','amount':'0'} for i in range(100000)])
        tables={name:[] for name in ('payments','payment_arrangements','hardship_programs','hugs_grants','support_needs_history')};tables['payments']=rows
        start=time.monotonic();index=customer_index(tables)
        for i in range(50000):self.assertEqual(len(records_at(tables,f'Q{i:07}','2024-11-01',index=index)),2)
        self.assertEqual(rows.visits,100000);self.assertLess(time.monotonic()-start,5)
        with TemporaryDirectory() as root,patch('prototype.uploads.MAX_BATCH_ROWS',100):
            store=UploadStore(root)
            with self.assertRaises(UploadError) as error:store.stage(generated_cohort(50),operation(),'none')
            self.assertEqual(error.exception.status,413);self.assertIsNone(store.status()['active_batch'])
