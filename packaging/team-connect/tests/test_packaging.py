"""Scaffold checks; no Docker daemon, accounts, secrets or application writes."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
import support


class PackagingTests(unittest.TestCase):
    def test_demo_start_fails_closed_without_opt_in(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            support.require_demo_opt_in()
        with patch.dict(os.environ, {'TEAM_CONNECT_UNAUTHENTICATED_DEMO': '1'}, clear=True):
            support.require_demo_opt_in()

    def test_only_expected_listen_addresses(self):
        for host in ['localhost', '::', '192.168.1.1']:
            with self.assertRaises(ValueError):
                support.bind_server(host)

    def test_bind_adapter_changes_only_listener(self):
        calls = []
        with patch.object(support.ThreadingHTTPServer, '__init__', lambda self, address, handler: calls.append((address, handler))):
            server = support.bind_server('0.0.0.0')(('127.0.0.1', 8891), object)
        self.assertEqual(calls, [(('0.0.0.0', 8891), object)])
        self.assertTrue(server.daemon_threads)

    def test_health_has_no_data_or_token_and_checks_host(self):
        class Base:
            def do_GET(self):
                self.delegated = True
        handler = object.__new__(support.health_handler(Base, 'q1'))
        handler.server = type('Server', (), {'server_port': 8891})()
        handler.path = '/healthz'
        handler.headers = {'Host': '127.0.0.1:8891'}
        handler.wfile = io.BytesIO()
        handler.send_response = lambda status: setattr(handler, 'status', status)
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        handler.send_error = lambda status: setattr(handler, 'status', status)
        handler.do_GET()
        self.assertEqual(json.loads(handler.wfile.getvalue()), {'service': 'q1', 'alive': True})
        handler.headers = {'Host': 'attacker.invalid'}
        handler.do_GET()
        self.assertEqual(handler.status, 403)
        handler.path = '/api/review'
        handler.do_GET()
        self.assertTrue(handler.delegated)

    def test_resilience_context_retains_pinned_boundary_and_helper(self):
        import hashlib
        spec = importlib.util.spec_from_file_location('stage_boundary_test', ROOT / 'stage.py')
        stage = importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);version='a'*64;source=base/('season-ahead-frozen-'+version[:12]);(source/'web/modules').mkdir(parents=True)
            files={'web/wa-boundary.geojson':b'{"type":"FeatureCollection","features":[]}', 'web/modules/local-basemap.mjs':b'export const boundary="local";'}
            for name,raw in files.items():(source/name).write_bytes(raw)
            receipt=base/'receipt.json';receipt.write_text(json.dumps({'codeVersionSha256':version,'frozenSnapshot':str(source),'runtimeFilesSha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}))
            output=base/'context';stage.stage_q3_receipt(receipt,output)
            for name,raw in files.items():self.assertEqual((output/'app'/name).read_bytes(),raw)

    def test_stage_rejects_symlink(self):
        spec = importlib.util.spec_from_file_location('stage', ROOT / 'stage.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'real').write_text('fixture')
            (root / 'link').symlink_to(root / 'real')
            with self.assertRaises(ValueError):
                module.copy_file(root / 'link', root / 'out', {})

    def test_snapshots_exclude_secrets_and_runtime(self):
        for name in ['q1', 'q3']:
            context = ROOT / 'build' / name
            self.assertTrue(context.is_dir(), 'Run stage.py first')
            files = [p.relative_to(context) for p in context.rglob('*') if p.is_file()]
            for file in files:
                self.assertFalse(any(p in {'.env', '.env.local', '.runtime', 'uploads', 'node_modules', '__pycache__'} for p in file.parts), file)
                self.assertNotEqual(file.name, 'last-good.json')
            dockerfile = (context / 'Dockerfile').read_text()
            self.assertIn('@sha256:', dockerfile)
            self.assertIn('USER 1000', dockerfile)
            self.assertNotIn('apt-get', dockerfile)
        self.assertFalse((ROOT / 'build/q1/app/prototype/reports').exists())

    def test_pdf_dependency_urls_have_explicit_hashes(self):
        from urllib.parse import urlsplit
        lines = [l for l in (ROOT / 'requirements-q1.txt').read_text().splitlines() if l and not l.startswith('#')]
        self.assertEqual(len(lines), 3)
        for line in lines:
            parts = line.split()
            self.assertEqual(parts[1], '@')
            self.assertEqual(urlsplit(parts[2]).hostname, 'files.pythonhosted.org')
            self.assertTrue(parts[2].endswith('.whl'))
            self.assertRegex(parts[3], r'^--hash=sha256:[0-9a-f]{64}$')
        self.assertIn('--require-hashes', (ROOT / 'Dockerfile.q1').read_text())
        self.assertIn('--no-index', (ROOT / 'Dockerfile.q1').read_text())

    def test_owner_receipt_cannot_escape_its_frozen_snapshot(self):
        spec = importlib.util.spec_from_file_location('stage_receipt', ROOT / 'stage.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);version = 'a' * 64
            frozen = root / ('season-ahead-frozen-' + version[:12]);frozen.mkdir()
            receipt = root / 'receipt.json'
            receipt.write_text(json.dumps({'frozenSnapshot': str(frozen), 'codeVersionSha256': version,
                                            'runtimeFilesSha256': {'server/../../outside.py': 'never-read'}}))
            with self.assertRaises(ValueError):
                module.stage_q3_receipt(receipt, root / 'context')
            self.assertFalse((root / 'context').exists())


if __name__ == '__main__':
    unittest.main()
