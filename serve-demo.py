"""Loopback demo with an allowlisted, credential-redacting MapTiler resource proxy."""
import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent / 'teamconnect'
FILES = {
    'index.html', 'styles.css', 'app.mjs', 'core.mjs', 'scenario.json',
    'provenance.json', 'checks.html', 'checks.mjs', 'area-boundaries.geojson',
    'area-boundaries-source.json', 'area-boundaries.mjs',
    'geography/poa2021.geojson', 'geography/poa2021.provenance.json', 'vendor/maplibre-gl.js', 'vendor/maplibre-gl.css',
    'vendor/maplibre-LICENSE.txt', 'vendor/maptiler-logo.svg',
}
MAP_ROOTS = {'maps', 'tiles', 'fonts', 'sprites', 'resources'}
MAX_RESOURCE_BYTES = 16 * 1024 * 1024


def read_maptiler_key(path):
    """Read only the approved variable; never execute or serve the environment file."""
    try:
        for line in path.read_text().splitlines():
            match = re.match(r'^\s*(?:export\s+)?MAPTILER_API_KEY\s*=\s*(.*?)\s*$', line)
            if match:
                value = match[1]
                if value[:1] in {'"', "'"}:
                    quote = value[0]
                    value = value[1:].split(quote, 1)[0]
                else:
                    value = value.split(' #', 1)[0].strip()
                return value
    except OSError:
        pass
    return ''


def rewrite_map_urls(value, origin):
    """Keep style, TileJSON, glyphs and sprites same-origin; omit upstream keys."""
    if isinstance(value, dict):
        return {key: rewrite_map_urls(item, origin) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_map_urls(item, origin) for item in value]
    if isinstance(value, str) and value.startswith('https://api.maptiler.com/'):
        parsed = urlsplit(value)
        query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if k != 'key'] + [('demo_v', '1')])
        return origin + '/maptiler' + parsed.path + ('?' + query if query else '')
    return value


class Handler(BaseHTTPRequestHandler):
    def reply(self, payload, content_type, status=200, cache=False):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'private, max-age=3600' if cache else 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data: blob:; connect-src 'self'; "
                         "worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A removed map can cancel in-flight tiles normally.

    def json_reply(self, value, status=200):
        self.reply(json.dumps(value).encode(), 'application/json', status)

    def proxy_map(self, parsed):
        if not self.server.maptiler_key:
            self.json_reply({'error': 'Map key unavailable'}, 503)
            return
        if self.server.missing_basemap:
            self.json_reply({'error': 'Basemap unavailable'}, 503)
            return
        # No user-supplied host, traversal, credential or arbitrary upstream route.
        path = parsed.path.removeprefix('/maptiler/')
        decoded = unquote(path)
        if (len(path) > 1800 or decoded.split('/')[0] not in MAP_ROOTS or
                any(part in {'.', '..'} for part in decoded.split('/')) or
                not re.fullmatch(r'[\w /.,@+%{}\-]+', decoded) or '\\' in decoded):
            self.json_reply({'error': 'Map resource not allowed'}, 404)
            return
        query = [(k, v) for k, v in parse_qsl(parsed.query) if k in {'language', 'variant'}]
        origin = 'http://' + self.headers.get('Host', '')
        cache_id = (path, tuple(query), origin)
        with self.server.map_lock:
            cached = self.server.map_cache.get(cache_id)
            if cached:
                self.server.map_stats['cache_hits'] += 1
        if cached:
            self.reply(*cached, cache='json' not in cached[1])
            return
        query.append(('key', self.server.maptiler_key))
        request = Request('https://api.maptiler.com/' + path + '?' + urlencode(query), headers={
            'Referer': origin + '/', 'Origin': origin,
            'User-Agent': 'TeamConnectLocalDemo/1.0', 'Accept-Encoding': 'identity',
        })
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read(MAX_RESOURCE_BYTES + 1)
                content_type = response.headers.get('Content-Type', 'application/octet-stream')
            if len(payload) > MAX_RESOURCE_BYTES:
                raise ValueError('Oversized map resource')
            if 'json' in content_type or path.endswith('.json'):
                document = json.loads(payload)
                if path == 'maps/streets-v4/style.json':
                    # The provider's generic road shield expression needs a route ref.
                    # Keep unnumbered streets in road/name layers, without an empty shield.
                    for layer in document.get('layers', []):
                        if layer.get('id') == 'Road shields':
                            layer['filter'] = ['all', layer['filter'], ['has', 'ref_length'],
                                               ['>', ['to-number', ['get', 'ref_length'], 0], 0]]
                payload = json.dumps(rewrite_map_urls(document, origin)).encode()
                content_type = 'application/json'
                if self.server.maptiler_key.encode() in payload:
                    raise ValueError('Unexpected credential in upstream JSON')
            with self.server.map_lock:
                self.server.map_stats['upstream_successes'] += 1
                self.server.map_cache[cache_id] = (payload, content_type)
                while len(self.server.map_cache) > 256:
                    self.server.map_cache.popitem(last=False)
            self.reply(payload, content_type, cache='json' not in content_type)
        except (HTTPError, URLError, OSError, ValueError) as error:
            with self.server.map_lock:
                self.server.map_stats['upstream_failures'] += 1
                self.server.map_stats['last_failure_status'] = getattr(error, 'code', None)
            # Never return upstream bodies, exception text, or credential-bearing URLs.
            if isinstance(error, HTTPError):
                error.close()
            self.json_reply({'error': 'Basemap resource unavailable'}, 502)

    def do_GET(self):
        parsed = urlsplit(self.path)
        try:
            hostname = urlsplit('http://' + self.headers.get('Host', '')).hostname
        except ValueError:
            hostname = None
        if hostname not in {'127.0.0.1', 'localhost'}:
            self.json_reply({'error': 'Local demo host required'}, 403)
            return
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.json_reply({'error': 'Same-origin request required'}, 403)
            return
        if parsed.path.startswith('/maptiler/'):
            self.proxy_map(parsed)
            return
        if parsed.path == '/map-health.json':
            with self.server.map_lock:
                result = dict(self.server.map_stats)
            self.json_reply({'configured': bool(self.server.maptiler_key), **result})
            return
        name = 'index.html' if parsed.path == '/' else parsed.path.removeprefix('/')
        if (name not in FILES or
                (self.server.missing_data and name == 'scenario.json') or
                (self.server.missing_map and name == 'vendor/maplibre-gl.js')):
            self.send_error(404, 'Demo asset unavailable')
            return
        path = ROOT / name
        if not path.is_file():
            self.send_error(404)
            return
        content_type = ('text/javascript' if name.endswith('.mjs') else
                        'application/geo+json' if name.endswith('.geojson') else
                        mimetypes.guess_type(name)[0] or 'application/octet-stream')
        self.reply(path.read_bytes(), content_type)

    def log_message(self, fmt, *args):
        # Log status/path only, never query strings, headers or upstream URLs.
        print(f'{self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ""}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--missing-data', action='store_true', help='QA: scenario returns 404')
    parser.add_argument('--missing-map', action='store_true', help='QA: MapLibre returns 404')
    parser.add_argument('--missing-basemap', action='store_true', help='QA: map proxy returns 503')
    parser.add_argument('--maptiler-env', type=Path,
                        default=Path.home() / 'Projects/team-connect/.env.local',
                        help='Local environment file containing MAPTILER_API_KEY; never served')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.missing_data = args.missing_data
    server.missing_map = args.missing_map
    server.missing_basemap = args.missing_basemap
    server.maptiler_key = read_maptiler_key(args.maptiler_env)
    server.map_cache = OrderedDict()
    server.map_lock = threading.Lock()
    server.map_stats = {'upstream_successes': 0, 'upstream_failures': 0,
                        'cache_hits': 0, 'last_failure_status': None}
    print(f'Team Connect: http://127.0.0.1:{args.port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
