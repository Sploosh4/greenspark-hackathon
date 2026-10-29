"""Adapt Q1 paths, PDF interpreter and container binding in this process only."""
import argparse
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from support import bind_server, health_handler, load_module, require_demo_opt_in


def create_server(app_root, source_root, runtime_dir, listen='127.0.0.1', port=8891, weather_source='cache', auth_store=None, session_idle_seconds=1800, session_absolute_seconds=28800):
    app_root, source_root = Path(app_root).resolve(), Path(source_root).resolve()
    sys.path.insert(0, str(app_root))
    module = load_module('q1_container_app', app_root / 'serve.py')
    from prototype import uploads
    # UploadStore's lambda reads this global when deriving uploaded reviews.
    # Uploaded business data remains separate from immutable baseline weather.
    uploads.DEFAULT_SOURCE = source_root
    build_review = module.build_review
    module.build_review = lambda: build_review(source_root)
    module.PDF_PYTHON = Path(sys.executable)
    module.Handler = health_handler(module.Handler, 'q1')
    module.ThreadingHTTPServer = bind_server(listen)
    auth=None
    if auth_store is not None:
        from private_identity import ReadOnlyIdentity,session_service_class
        from prototype.vendor.auth import local_auth
        auth=session_service_class(local_auth)('q1',ReadOnlyIdentity(auth_store,'q1',local_auth),idle_seconds=session_idle_seconds,absolute_seconds=session_absolute_seconds)
    return module.make_server(port=port, store_root=Path(runtime_dir), weather_source=weather_source, auth=auth)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--listen', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8891)
    parser.add_argument('--weather-source', choices=['cache', 'public'], default='cache')
    parser.add_argument('--auth-store', type=Path)
    parser.add_argument('--session-idle-seconds', type=int, default=1800)
    parser.add_argument('--session-absolute-seconds', type=int, default=28800)
    args = parser.parse_args()
    if args.auth_store is None:require_demo_opt_in()
    elif os.environ.get('TEAM_CONNECT_UNAUTHENTICATED_DEMO')=='1':raise SystemExit('Choose authenticated mode or explicit preview, not both')
    server = create_server(**vars(args))
    if args.weather_source=='public':
        start=getattr(server,'start_weather_updates',None)
        if not callable(start):raise SystemExit('This source does not expose the approved weather lifecycle hooks')
        start()
    try:
        server.serve_forever()
    finally:
        stop=getattr(server,'stop_weather_updates',None)
        if callable(stop):stop()
        server.upload_jobs.close()
        server.server_close()


if __name__ == '__main__':
    main()
