"""Browser entry-point imports must also be admitted by the real static handler."""
import re,unittest
from pathlib import Path
import test_upload_http as http
import test_source_adapter as fixtures
from map_proxy import FILES

class Assets(unittest.TestCase):
 def test_every_relative_browser_import_is_served_by_the_static_allowlist(self):
  web=fixtures.ROOT/'web';pending=[web/'view.mjs',web/'business.mjs'];seen=set()
  while pending:
   file=pending.pop()
   if file in seen:continue
   seen.add(file);name=file.relative_to(web).as_posix();self.assertIn(name,FILES,name)
   for relative in re.findall(r"(?:from\s*|import\s*)['\"]([^'\"]+)['\"]",file.read_text()):
    if not relative.startswith('.'):continue
    target=(file.parent/relative).resolve();self.assertTrue(target.is_relative_to(web.resolve()));self.assertTrue(target.is_file());pending.append(target)
 def test_actual_preview_handler_serves_both_new_modules(self):
  from types import SimpleNamespace
  for path in ['/modules/climate-contract.mjs','/modules/upload-validation.mjs']:
   h=http.app.Q3Handler.__new__(http.app.Q3Handler);h.server=SimpleNamespace(auth=None,missing_data=False,missing_map=False);h.path=path;h.headers={'Host':'127.0.0.1:8797'};out=[];h.reply=lambda body,kind,status=200,**kwargs:out.append((status,kind,body));h.json_reply=lambda value,status=200:out.append((status,'application/json',value));h.do_GET();self.assertEqual(out[0][0],200,path);self.assertEqual(out[0][1],'text/javascript');self.assertGreater(len(out[0][2]),100)
 def test_local_map_assets_are_available_without_provider_requests(self):
  import json
  from types import SimpleNamespace
  for path in ['/modules/local-basemap.mjs','/wa-boundary.geojson']:
   h=http.app.Q3Handler.__new__(http.app.Q3Handler);h.server=SimpleNamespace(auth=None,missing_data=False,missing_map=False);h.path=path;h.headers={'Host':'127.0.0.1:8797'};out=[];h.reply=lambda body,kind,status=200,**kwargs:out.append((status,kind,body));h.json_reply=lambda value,status=200:out.append((status,'application/json',value));h.do_GET();self.assertEqual(out[0][0],200,path)
   if path.endswith('.geojson'):self.assertEqual(json.loads(out[0][2])['features'][0]['properties']['state_code_2021'],'5')
