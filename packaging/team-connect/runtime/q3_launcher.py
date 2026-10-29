"""Adapt Q3 bind address without changing its input/cache/proxy implementation."""
import argparse
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from support import bind_server, health_handler, load_module, require_demo_opt_in


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, required=True)
    parser.add_argument('--listen', default='127.0.0.1')
    parser.add_argument('--auth-store', type=Path)
    parser.add_argument('--auth-mode', help=argparse.SUPPRESS)
    parser.add_argument('--session-idle-seconds', type=int, default=1800)
    parser.add_argument('--session-absolute-seconds', type=int, default=28800)
    args, app_args = parser.parse_known_args()
    if args.auth_mode is not None:raise SystemExit('Launcher selects auth mode from --auth-store; do not override it')
    if args.auth_store is None:require_demo_opt_in()
    elif os.environ.get('TEAM_CONNECT_UNAUTHENTICATED_DEMO')=='1':raise SystemExit('Choose authenticated mode or explicit preview, not both')
    module = load_module('q3_container_app', args.app_root / 'run.py')
    if args.auth_store is not None:
        import local_auth
        from private_identity import ReadOnlyIdentity,session_service_class
        module.AuthService=lambda instance,lookup:session_service_class(local_auth)(instance,lookup,idle_seconds=args.session_idle_seconds,absolute_seconds=args.session_absolute_seconds)
        module.ReadOnlyAccounts=lambda path:ReadOnlyIdentity(path,'q3',local_auth)
        app_args.extend(['--auth-mode','enforced','--auth-store',str(args.auth_store)])
    module.Q3Handler = health_handler(module.Q3Handler, 'q3')
    module.ThreadingHTTPServer = bind_server(args.listen)
    sys.argv = [str(args.app_root / 'run.py'), *app_args]
    module.main()


if __name__ == '__main__':
    main()
