"""Hand-worked source-date trace; no change to declared following-night method."""
import copy,csv,hashlib,json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from prototype.inputs import DEFAULT_SOURCE,InputError
from prototype.weather import load_weather,WEATHER_NAME
from prototype.vendor.ehf.adapters import silo_rows,SILO_ADAPTER
from prototype.vendor.ehf.core import Source

class SiloAlignmentTests(unittest.TestCase):
    def test_afternoon_and_following_morning_use_one_declared_window(self):
        source=Source('date-fixture','SILO','synthetic date convention fixture','SYNTHETIC',-18.2,125.55,SILO_ADAPTER)
        rows=[{'YYYY-MM-DD':f'2024-01-0{i+1}','latitude':'-18.2','longitude':'125.55','max_temp_source':'25','min_temp_source':'25','max_temp':str(40+i),'min_temp':str(10+10*i)} for i in range(3)]
        values=silo_rows(rows,source).points
        self.assertEqual(values[0].date,'2024-01-01');self.assertEqual(values[0].dmt_c,30)
        self.assertEqual(values[1].dmt_c,35.5);self.assertIsNone(values[2].dmt_c)
        self.assertNotEqual(values[0].dmt_c,(40+10)/2) # morning on DayD is a different window.
    def test_source_inversion_is_rejected_without_swap_shift_or_clamp(self):
        folder=DEFAULT_SOURCE/'Fitzroy-Crossing-6765-HISTORICAL-INPUTS';meta=json.loads((folder/'PROVENANCE-AND-COVERAGE.json').read_text())
        with TemporaryDirectory() as root:
            dest=Path(root)/folder.name;dest.mkdir();text=(folder/WEATHER_NAME).read_text();reader=csv.DictReader(StringIO(text));rows=list(reader);rows[0]['min_temp']='60'
            out=StringIO(newline='');writer=csv.DictWriter(out,fieldnames=reader.fieldnames);writer.writeheader();writer.writerows(rows);raw=out.getvalue().encode();(dest/WEATHER_NAME).write_bytes(raw)
            meta['weather_sha256']=hashlib.sha256(raw).hexdigest();(dest/'PROVENANCE-AND-COVERAGE.json').write_text(json.dumps(meta))
            with self.assertRaisesRegex(InputError,'minimum exceeds maximum'):load_weather(root)
