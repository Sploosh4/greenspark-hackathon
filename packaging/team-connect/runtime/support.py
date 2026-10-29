"""Container-only wiring. Application sources are imported without rewriting them."""
import importlib.util
import json
import os
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def require_demo_opt_in():
    if os.environ.get('TEAM_CONNECT_UNAUTHENTICATED_DEMO') != '1':
        raise SystemExit('Authentication is not integrated. Explicit local synthetic demo opt-in is required.')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def health_handler(base, service):
    class Handler(base):
        def do_GET(self):
            if urlsplit(self.path).path == '/healthz':
                if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
                    self.send_error(403)
                    return
                # Liveness only; no account data, source token, upstream or secret read.
                raw = json.dumps({'service': service, 'alive': True}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(raw)
                return
            super().do_GET()
    return Handler


def bind_server(listen):
    if listen not in {'127.0.0.1', '0.0.0.0'}:
        raise ValueError('Unsupported listen address')

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def __init__(self, address, handler):
            super().__init__((listen, address[1]), handler)
    return Server
