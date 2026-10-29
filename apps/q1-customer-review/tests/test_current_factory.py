"""Opt-in current integration wiring without opening a listening socket."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch,MagicMock
import unittest
import serve

class CurrentFactoryTests(unittest.TestCase):
 def test_opt_in_uses_current_builder_same_weather_and_daily_refresh_callback(self):
  with TemporaryDirectory() as root,patch.object(serve,'ThreadingHTTPServer',return_value=MagicMock()) as http:
   server=serve.make_server(store_root=Path(root),review={'snapshot_id':'demo','build':{'id':'fixture'}},current_uploads=True,current_python='/approved/isolated/python')
   try:
    http.assert_called_once_with(('127.0.0.1',8891),serve.Handler)
    self.assertIs(server.uploads.builder,server.current_calculations)
    self.assertIs(server.current_calculations.weather,server.public_weather)
    with patch.object(server.current_calculations,'refresh_active') as refresh:
     server.weather_job.on_refresh({'succeeded':True});refresh.assert_called_once_with(server.uploads)
   finally:server.current_calculations.close();server.upload_jobs.close()
 def test_disabled_default_keeps_existing_builder(self):
  with TemporaryDirectory() as root,patch.object(serve,'ThreadingHTTPServer',return_value=MagicMock()):
   server=serve.make_server(store_root=Path(root),review={'snapshot_id':'demo','build':{'id':'fixture'}})
   try:self.assertIsNone(server.current_calculations)
   finally:server.upload_jobs.close()

if __name__=='__main__':unittest.main()
