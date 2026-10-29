"""Controlled decoder ordering/identity regressions; byte fixtures are not GRIBs."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_climate_refresh import messages
from climate_pack import decode_grib,LATS,LONS
from source_adapter import SourceError,digest

class ControlledDecoder:
 def __init__(self,path=None,replace=None):
  self.metadata=messages('mean');self.path=path;self.replace=replace;self.index=0;self.observed=None;self.arrays=[];self.released=[];self.encoded_calls=0
 def codes_grib_new_from_file(self,f):
  if self.observed is None:
   if self.replace is not None:self.path.write_bytes(self.replace)
   self.observed=f.read()
  if self.index==len(self.metadata):return None
  handle=self.index;self.index+=1;return handle
 def codes_get(self,h,k):return 1 if k=='bitmapPresent' else self.metadata[h]['metadata'][k]
 def codes_get_message(self,h):self.encoded_calls+=1;return self.observed[h*8:(h+1)*8]
 def codes_get_values(self,h):self.arrays.append('values');return self.metadata[h]['valuesK']
 def codes_get_array(self,h,key):
  self.arrays.append(key)
  return {'latitudes':[lat for lat in LATS for _ in LONS],'longitudes':LONS*len(LATS),'bitmap':[0]+[1]*413}[key]
 def codes_release(self,h):self.released.append(h)

class GribBoundary(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'issue.grib';self.raw=b'GRIB7777'*6;self.path.write_bytes(self.raw)
 def decode(self,ec):return decode_grib(self.path,'mean','2026-11',digest(self.raw),ec)
 def test_oversized_grid_is_rejected_before_any_array_or_message_expansion(self):
  ec=ControlledDecoder();ec.metadata[0]['metadata'].update(Ni=1000,Nj=100,numberOfDataPoints=100000)
  with self.assertRaisesRegex(SourceError,'model_units_dates_or_grid'):self.decode(ec)
  self.assertEqual(ec.arrays,[]);self.assertEqual(ec.encoded_calls,0);self.assertEqual(ec.released,[0])
 def test_wrong_model_dates_units_and_missingness_fail_before_arrays(self):
  for key,value in [('systemNumber',52),('dataDate',20261102),('units','degC'),('numberOfMissing',415)]:
   with self.subTest(key=key):
    ec=ControlledDecoder();ec.metadata[0]['metadata'][key]=value
    with self.assertRaises(SourceError):self.decode(ec)
    self.assertEqual(ec.arrays,[]);self.assertEqual(ec.released,[0])
 def test_replacing_inbox_after_verification_does_not_change_decoder_bytes(self):
  replacement=b'GRIB'+b'x'*4096+b'7777';ec=ControlledDecoder(self.path,replacement);out=self.decode(ec)
  self.assertEqual(self.path.read_bytes(),replacement);self.assertEqual(ec.observed,self.raw);self.assertEqual(len(out['fields']),6);self.assertEqual(out['gribSha256'],digest(self.raw));self.assertEqual(len(ec.released),6)
 def test_legitimate_six_leads_and_native_missingness_are_preserved(self):
  ec=ControlledDecoder();ec.metadata[0]['metadata']['numberOfMissing']=1;out=self.decode(ec)
  self.assertIsNone(out['fields'][0]['valuesC'][0][0]);self.assertAlmostEqual(out['fields'][1]['valuesC'][0][0],26.975);self.assertIn('bitmap',ec.arrays);self.assertEqual(len(ec.released),6)
 def test_unparsed_bytes_and_too_many_messages_cannot_be_accepted(self):
  ec=ControlledDecoder();ec.metadata.pop()
  with self.assertRaisesRegex(SourceError,'unparsed'):self.decode(ec)
  ec=ControlledDecoder();ec.metadata.append(copy.deepcopy(ec.metadata[-1]))
  with self.assertRaisesRegex(SourceError,'six_complete'):self.decode(ec)
  self.assertEqual(ec.released[-1],6)
 def test_hash_and_request_rejected_without_creating_decoder_copy(self):
  with patch('climate_pack.TemporaryFile',side_effect=AssertionError('must not allocate decoder copy')):
   with self.assertRaisesRegex(SourceError,'hash_or_size'):decode_grib(self.path,'mean','2026-11','0'*64,ControlledDecoder())
   with self.assertRaisesRegex(SourceError,'request_contract'):decode_grib(self.path,'other','2026-11',digest(self.raw),ControlledDecoder())
