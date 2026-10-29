"""PDF validity, selection, missing values and actual text geometry."""
import copy
from io import BytesIO
import json
from pathlib import Path
import unittest
import pdfplumber
from pypdf import PdfReader
from pdf_export import create_summary,create_condensed_summary

ROOT=Path(__file__).resolve().parents[1]

class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review=json.loads((ROOT/'prototype/reports/current-review.json').read_text())
        cls.fixture=json.loads((ROOT/'assets/review-fixture.json').read_text())
    def text(self,raw):
        self.assertTrue(raw.startswith(b'%PDF-'));self.assertTrue(raw.rstrip().endswith(b'%%EOF'))
        return '\n'.join(p.extract_text() for p in PdfReader(BytesIO(raw)).pages)
    def assert_geometry(self,raw):
        with pdfplumber.open(BytesIO(raw)) as doc:
            for page in doc.pages:
                for char in page.chars:
                    self.assertGreaterEqual(char['x0'],43)
                    self.assertLessEqual(char['x1'],page.width-43)
                    self.assertGreaterEqual(char['top'],20)
                    self.assertLessEqual(char['bottom'],page.height-20)
    def test_single_customer_and_actual_amounts(self):
        raw=create_summary(self.review,['C103794']);text=self.text(raw)
        self.assertIn('C103794',text);self.assertNotIn('C102502',text)
        for value in ['30.8 kWh','92.4 kWh','+0.1%','-7.1%','Payment recorded']:self.assertIn(value,text)
        self.assert_geometry(raw)
    def test_multiple_selection_deduplicates_and_preserves_order(self):
        text=self.text(create_summary(self.review,['C102502','C105072','C102502']))
        self.assertEqual(text.count('C102502\n'),1)
        self.assertLess(text.index('C102502'),text.index('C105072'))
        self.assertIn('No bill records were supplied.',text)
        self.assertIn('amount owed cannot be checked',text)
    def test_unavailable_and_genuine_zero_in_multi_event_fixture(self):
        raw=create_summary(self.fixture,['C105017','C101456']);text=self.text(raw)
        before,stable=text.split('C101456',1)
        self.assertIn('Unavailable',before);self.assertNotIn('0.0%',before.split('Recent daily grid use:')[0])
        self.assertIn('0.0%',stable);self.assert_geometry(raw)
    def test_long_values_and_many_rows_paginate_without_overflow(self):
        d=copy.deepcopy(self.review);row=next(r for r in d['customers'] if r['customer']['customer_id']=='C103794')
        row['customer']['locality']='Long locality '+('longunbrokentext'*18)
        row['records']=[{'kind':'Payment recorded','date':'2024-10-30','id':str(i)+'R'*200} for i in range(70)]
        raw=create_summary(d,['C103794']);self.text(raw)
        self.assertGreater(len(PdfReader(BytesIO(raw)).pages),3);self.assert_geometry(raw)
    def test_empty_unknown_selection_rejected(self):
        for ids in [[],['unknown'],['C103794']*101,'C103794']:
            with self.assertRaises(ValueError):create_summary(self.review,ids)

    def test_selected_projection_is_byte_identical_for_single_and_multiple_accounts(self):
        from prototype.exports import selected_rows
        for ids in [['C103794'],['C102502','C105072','C102502']]:
            projected={**self.review,'customers':selected_rows(self.review,ids)}
            self.assertEqual(create_summary(self.review,ids),create_summary(projected,ids))
    def test_condensed_preserves_selection_events_missing_zero_and_geometry(self):
        raw=create_condensed_summary(self.fixture,['C105017','C101456','C105017']);text=self.text(raw)
        self.assertEqual(text.count('C105017'),1);self.assertEqual(text.count('C101456'),1)
        self.assertIn('Unavailable',text);self.assertIn('0.0%',text);self.assertIn('Latest dated records only',text)
        self.assert_geometry(raw)
    def test_condensed_100_customers_are_each_present_once(self):
        from copy import deepcopy
        review=deepcopy(self.review);base=review['customers'][0]
        review['customers']=[{**base,'customer':{**base['customer'],'customer_id':f'PERF-{i:05}'}} for i in range(100)]
        ids=[row['customer']['customer_id'] for row in review['customers']];raw=create_condensed_summary(review,ids);text=self.text(raw)
        for cid in ids:self.assertEqual(text.count(cid),1)
        self.assert_geometry(raw)
    def test_uploaded_blank_optional_bill_amount_stays_unavailable_in_both_formats(self):
        from tempfile import TemporaryDirectory
        from prototype.uploads import UploadStore
        from tests.make_upload_fixtures import fixture_parts,mutate
        import uuid
        parts=mutate(fixture_parts(),'bills.csv',lambda headers,rows:[row.update(amount_due='') for row in rows])
        with TemporaryDirectory() as root:
            store=UploadStore(root);operation=uuid.uuid4().hex;store.stage(parts,operation,'none');store.activate(operation,'none');review=store.view()
            self.assertTrue(review['customers'][0]['financial']);self.assertTrue(all(row['amount']=='' for row in review['customers'][0]['financial']))
            for renderer in [create_summary,create_condensed_summary]:
                raw=renderer(review,['C103794']);text=self.text(raw);self.assertIn('Unavailable',text);self.assertNotIn('$0.00',text);self.assert_geometry(raw)

if __name__=='__main__':unittest.main()
