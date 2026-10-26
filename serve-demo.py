"""Loopback-only, allowlisted demo server. No credentials or directory listings."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import mimetypes

ROOT=Path(__file__).resolve().parent/'teamconnect'
FILES={'index.html','styles.css','app.mjs','core.mjs','review.mjs','scenario.json','provenance.json','checks.html','checks.mjs','vendor/maplibre-gl.js','vendor/maplibre-gl.css','vendor/maplibre-LICENSE.txt'}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name=urlsplit(self.path).path
        name='index.html' if name=='/' else name.removeprefix('/')
        if name not in FILES or (self.server.missing_data and name=='scenario.json') or (self.server.missing_map and name=='vendor/maplibre-gl.js'):
            self.send_error(404,'Demo asset unavailable');return
        path=ROOT/name
        if not path.is_file():self.send_error(404);return
        payload=path.read_bytes();self.send_response(200)
        self.send_header('Content-Type', 'text/javascript' if name.endswith('.mjs') else mimetypes.guess_type(name)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers();self.wfile.write(payload)
    def log_message(self,fmt,*args):
        # Only path/status for this credential-free allowlist.
        print(fmt%args)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8787);p.add_argument('--missing-data',action='store_true',help='QA only: scenario requests return 404');p.add_argument('--missing-map',action='store_true',help='QA only: map library requests return 404');a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.missing_data=a.missing_data;server.missing_map=a.missing_map
    print(f'Team Connect: http://127.0.0.1:{a.port}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
