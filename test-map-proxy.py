"""Offline checks for the local map proxy's credential and resource boundary."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('demo_server', Path(__file__).with_name('serve-demo.py'))
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class QuietHandler(demo.Handler):
    def log_message(self, *_):
        pass


class MapProxyTests(unittest.TestCase):
    def setUp(self):
        self.server = demo.ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.server.maptiler_key = 'test-key-never-returned-to-browser'
        self.server.missing_data = self.server.missing_map = self.server.missing_basemap = False
        self.server.map_cache = demo.OrderedDict()
        self.server.map_lock = threading.Lock()
        self.server.map_stats = {'upstream_successes': 0, 'upstream_failures': 0,
                                 'cache_hits': 0, 'last_failure_status': None}
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_reads_only_approved_variable_without_executing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / '.env.local'
            env.write_text('OTHER_SECRET=unrelated\nexport MAPTILER_API_KEY="approved-value" # local\n')
            self.assertEqual(demo.read_maptiler_key(env), 'approved-value')
            self.assertEqual(demo.read_maptiler_key(Path(folder) / 'missing'), '')

    def test_worker_resources_are_absolute_and_credential_free(self):
        source = {'glyphs': 'https://api.maptiler.com/fonts/{fontstack}/{range}.pbf?key=secret',
                  'tiles': ['https://api.maptiler.com/tiles/v4/{z}/{x}/{y}?key=secret']}
        result = demo.rewrite_map_urls(source, self.origin)
        self.assertTrue(result['glyphs'].startswith(self.origin + '/maptiler/'))
        self.assertIn('{z}/{x}/{y}', result['tiles'][0])
        self.assertNotIn('secret', json.dumps(result))
        self.assertNotIn('api.maptiler.com', json.dumps(result))

    def test_proxy_keeps_key_upstream_and_preserves_attribution(self):
        document = {'tiles': ['https://api.maptiler.com/tiles/v4/{z}/{x}/{y}?key=' + self.server.maptiler_key],
                    'attribution': '© MapTiler © OpenStreetMap contributors'}
        response = io.BytesIO(json.dumps(document).encode())
        response.headers = {'Content-Type': 'application/json'}
        with patch.object(demo, 'urlopen', return_value=response) as upstream:
            with urlopen(self.origin + '/maptiler/tiles/v4/tiles.json') as result:
                body = result.read().decode()
            self.assertNotIn(self.server.maptiler_key, body)
            self.assertIn('OpenStreetMap', body)
            request = upstream.call_args.args[0]
            self.assertIn('key=' + self.server.maptiler_key, request.full_url)
            self.assertEqual(request.headers['Origin'], self.origin)

    def test_environment_traversal_and_foreign_hosts_are_denied(self):
        for path in ['/.env.local', '/maptiler/maps/%2e%2e/%2e%2e/.env.local']:
            with self.assertRaises(HTTPError) as failure:
                urlopen(self.origin + path)
            self.assertEqual(failure.exception.code, 404)
            failure.exception.close()
        with self.assertRaises(HTTPError) as failure:
            urlopen(Request(self.origin + '/map-health.json', headers={'Host': 'unrelated.example'}))
        self.assertEqual(failure.exception.code, 403)
        failure.exception.close()

    def test_upstream_errors_do_not_disclose_urls_or_credentials(self):
        error = HTTPError('https://api.maptiler.com/?key=' + self.server.maptiler_key,
                          403, 'rejected', {}, io.BytesIO(b'private upstream body'))
        with patch.object(demo, 'urlopen', side_effect=error):
            with self.assertRaises(HTTPError) as failure:
                urlopen(self.origin + '/maptiler/maps/streets-v4/style.json')
            self.assertEqual(failure.exception.code, 502)
            body = failure.exception.read().decode()
            self.assertNotIn(self.server.maptiler_key, body)
            self.assertNotIn('private upstream body', body)
            failure.exception.close()
            self.assertEqual(self.server.map_stats['last_failure_status'], 403)


if __name__ == '__main__':
    unittest.main()
