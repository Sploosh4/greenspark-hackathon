import copy,csv,json,unittest
from pathlib import Path
from io import StringIO
from prototype.exports import csv_bytes,selected_rows,iter_csv_chunks
from unittest.mock import patch
from prototype.uploads import UploadError

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.r=json.loads((Path(__file__).resolve().parents[1]/'prototype/reports/current-review.json').read_text())
        self.r.update(batch_id='test-batch',batch_revision='test-revision',data_mode='upload')
        self.row=next(x for x in self.r['customers'] if x['customer']['customer_id']=='C103794')
    def read(self,ids):return list(csv.DictReader(StringIO(csv_bytes(self.r,ids).decode('utf-8-sig'))))
    def test_numeric_negatives_remain_numbers_and_text_is_guarded(self):
        self.row['predictions'][0]['increase']=-1.5;self.row['episodes'][0]['increase_percent']=-7.0
        self.row['customer']['locality']='=malicious-text'
        row=self.read(['C103794'])[0]
        self.assertEqual(float(row['expected_increase_percent']),-1.5);self.assertEqual(float(row['past_comparison_percent']),-7)
        self.assertTrue(row['locality'].startswith("'="));self.assertEqual(row['batch_revision'],'test-revision')
    def test_unavailable_values_stay_empty_in_csv(self):
        self.row['predictions'][0].update(increase=None,predicted=None)
        row=self.read(['C103794'])[0];self.assertEqual(row['expected_increase_percent'],'');self.assertEqual(row['estimated_daily_import_kwh'],'')
    def test_filtered_csv_is_not_limited_to_pdf_selection_size(self):
        self.r['customers']=[]
        for i in range(101):
            row=copy.deepcopy(self.row);row['customer']['customer_id']='TEST'+str(i);self.r['customers'].append(row)
        ids=[r['customer']['customer_id'] for r in self.r['customers']]
        self.assertEqual(len(self.read(ids)),101)
        with self.assertRaises(UploadError):selected_rows(self.r,ids)
    def test_chunked_output_is_identical_and_output_limit_is_enforced(self):
        ids=['C103794'];self.assertEqual(b''.join(iter_csv_chunks(self.r,ids)),csv_bytes(self.r,ids))
        with patch('prototype.exports.MAX_CSV_BYTES',10),self.assertRaises(UploadError) as error:csv_bytes(self.r,ids)
        self.assertEqual(error.exception.status,413)
    def test_explicit_customer_and_reference_caps_remain_in_force(self):
        for ids in [['C103794']*50001,['X'*129]]:
            with self.assertRaises(UploadError):csv_bytes(self.r,ids)

if __name__=='__main__':unittest.main()
