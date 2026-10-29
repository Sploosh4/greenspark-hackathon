"""No network beyond this container's loopback listener."""
import json
import sys
from urllib.request import build_opener, ProxyHandler

if __name__ == '__main__':
    port, service = sys.argv[1:]
    opener = build_opener(ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{int(port)}/healthz', timeout=3) as response:
        result = json.load(response)
    if result != {'service': service, 'alive': True}:
        raise SystemExit(1)
