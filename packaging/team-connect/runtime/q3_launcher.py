"""Adapt Q3 bind address without changing its input/cache/proxy implementation."""
import argparse
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from support import bind_server, health_handler, load_module, require_demo_opt_in


def main():
    require_demo_opt_in()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, required=True)
    parser.add_argument('--listen', default='127.0.0.1')
    args, app_args = parser.parse_known_args()
    module = load_module('q3_container_app', args.app_root / 'run.py')
    module.Q3Handler = health_handler(module.Q3Handler, 'q3')
    module.ThreadingHTTPServer = bind_server(args.listen)
    sys.argv = [str(args.app_root / 'run.py'), *app_args]
    module.main()


if __name__ == '__main__':
    main()
