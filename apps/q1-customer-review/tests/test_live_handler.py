from email.message import Message
from io import BytesIO
from types import SimpleNamespace
import json,threading,unittest
from unittest.mock import patch
from serve import Handler
from tests.test_public_weather import NOW,window,normalise,cache

class LiveHandlerTests(unittest.TestCase):
    def test_concurrent_modes_retain_request_local_coverage(self):
        server=SimpleNamespace(server_port=8891,auth=None,clock=lambda:NOW,public_weather=SimpleNamespace(view=lambda now:window(normalise(cache()),now)),weather_job=SimpleNamespace(status=lambda:{'daily_time':'06:00','timezone':'Australia/Perth'}),live_coverage={},live_coverage_lock=threading.RLock())
        responses={};errors=[]
        def handle(mode):
            try:
                h=Handler.__new__(Handler);h.server=server;h.command='GET';h.path='/api/live-weather?mode='+mode;h.headers=Message();h.headers['Host']='127.0.0.1:8891';h.wfile=BytesIO()
                h.review=lambda selected:{'batch_revision':'rev-'+selected,'input_validation':{'source_root':selected}}
                h.json=lambda status,value:responses.update({mode:(status,value)})
                h.do_GET()
            except Exception as e:errors.append(e)
        with patch('serve.business_coverage',side_effect=lambda root,now:{'mode':root}):
            threads=[threading.Thread(target=handle,args=(mode,)) for mode in ['demo','upload']]
            for thread in threads:thread.start()
            for thread in threads:thread.join(3)
        self.assertFalse(errors);self.assertEqual(set(responses),{'demo','upload'})
        for mode,(status,value) in responses.items():self.assertEqual(status,200);self.assertEqual(value['business']['mode'],mode)
