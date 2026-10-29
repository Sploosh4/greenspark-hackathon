"""Runtime coverage path mapping must preserve frozen metadata and uploaded paths."""
from pathlib import Path
from unittest.mock import Mock
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from q1_launcher import runtime_coverage_reader
class ReplayPathMappingTests(unittest.TestCase):
 def test_recorded_source_maps_to_runtime_bind(self):
  reader=Mock(return_value={'available_days':0});mapped=runtime_coverage_reader(reader,'/generation/approved-source','/inputs/q1');clock=object();self.assertEqual(mapped('/generation/approved-source',clock),{'available_days':0});reader.assert_called_once_with(Path('/inputs/q1'),clock)
 def test_uploaded_batch_source_is_not_rewritten(self):
  reader=Mock();mapped=runtime_coverage_reader(reader,'/generation/approved-source','/inputs/q1');clock=object();mapped('/state/uploads/batches/test/candidate-business-data',clock);reader.assert_called_once_with('/state/uploads/batches/test/candidate-business-data',clock)
if __name__=='__main__':unittest.main()
