"""Correctness checks for bounded caches and revision-only export checks."""
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from prototype.inputs import iso,InputError,_canonical_date,_date_fields,validate_row
from prototype.uploads import UploadStore,UploadError
from serve import Handler

class OptimisationTests(unittest.TestCase):
    def test_date_cache_preserves_canonical_and_invalid_date_distinctions(self):
        self.assertEqual(iso('2024-02-29',field='a'),date(2024,2,29))
        self.assertIsNone(iso('',field='a'))
        for value in ['2023-02-29','2024-2-9','2024-02-29T10:00',[1],123]:
            with self.subTest(value=value),self.assertRaises(InputError):iso(value,field='a')
        with self.assertRaisesRegex(InputError,'not canonical'):iso('20240229',field='a')
        with self.assertRaisesRegex(InputError,'missing required date'):iso('',field='a',required=True)
        with self.assertRaisesRegex(InputError,'second: invalid'):iso('invalid',field='second')
    def test_caches_are_bounded_and_date_columns_follow_actual_headers(self):
        start=date(2000,1,1)
        for i in range(5000):iso((start+timedelta(days=i)).isoformat(),field='date')
        self.assertLessEqual(_canonical_date.cache_info().currsize,4096)
        for i in range(100):_date_fields(('customer_id',f'field{i}_date'))
        self.assertLessEqual(_date_fields.cache_info().currsize,64)
        validate_row('example',{'customer_id':'A','extra_date':'2024-01-01'},{'A'})
        with self.assertRaises(InputError):validate_row('example',{'customer_id':'A','other_date':'bad'},{'A'})
    def test_revision_only_check_does_not_copy_or_read_a_snapshot(self):
        with TemporaryDirectory() as root:
            store=UploadStore(Path(root));store.state.update(revision='A',active='batch')
            with patch.object(store,'_get',side_effect=AssertionError('snapshot read')),patch('prototype.uploads.copy.deepcopy',side_effect=AssertionError('copy')):
                store.assert_revision('A')
                with self.assertRaises(UploadError) as error:store.assert_revision('old')
                self.assertEqual(error.exception.status,409)
                store.state['active']=None
                with self.assertRaises(UploadError) as error:store.assert_revision('A')
                self.assertEqual(error.exception.status,404)
    def test_handler_revision_check_retains_mode_and_demo_failure_semantics(self):
        handler=Handler.__new__(Handler);handler.server=SimpleNamespace(review={'customers':[]},demo_revision='demo-A',uploads=SimpleNamespace(assert_revision=lambda revision:revision))
        self.assertEqual(handler.assert_revision('upload','A'),'A')
        handler.assert_revision('demo','demo-A')
        for mode,revision,status in [('demo','old',409),('unknown','demo-A',400)]:
            with self.assertRaises(UploadError) as error:handler.assert_revision(mode,revision)
            self.assertEqual(error.exception.status,status)
        handler.server.review=None
        with self.assertRaises(UploadError) as error:handler.assert_revision('demo','demo-A')
        self.assertEqual(error.exception.status,503)
