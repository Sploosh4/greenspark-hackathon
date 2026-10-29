"""Exercise launcher boundaries with temporary identities and no listening socket."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
import support
from private_identity import PARAMS


class AuthenticatedLaunchers(unittest.TestCase):
    def identity(self, folder, instance):
        path = folder / 'auth.sqlite3'
        with sqlite3.connect(path) as db:
            db.executescript('PRAGMA user_version=1;CREATE TABLE instance_meta(instance TEXT);CREATE TABLE accounts(account_id TEXT,username TEXT,role TEXT,salt BLOB,digest BLOB,enabled INTEGER,credential_version INTEGER,kdf TEXT);')
            db.execute('INSERT INTO instance_meta VALUES(?)', (instance,))
            db.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?)', ('temporary', 'fixture', 'manager', b's' * 16, b'd' * 32, 1, 1, PARAMS))
        path.chmod(0o600)
        return path

    def test_cli_refuses_missing_store_and_ambiguous_or_implicit_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for instance, app in [('q1', 'q1-customer-review'), ('q3', 'q3-community-planning')]:
                launcher = ROOT / 'runtime' / (instance + '_launcher.py')
                args = [sys.executable, '-B', str(launcher), '--app-root', str(REPO / 'apps' / app), '--runtime-dir', str(folder / 'state')]
                if instance == 'q1':
                    args += ['--source-root', str(folder / 'absent-inputs')]
                for mode in ['implicit_preview', 'missing_store', 'ambiguous_preview']:
                    env = dict(os.environ)
                    env.pop('TEAM_CONNECT_UNAUTHENTICATED_DEMO', None)
                    call = list(args)
                    if mode != 'implicit_preview':
                        call += ['--auth-store', str(folder / 'missing.sqlite3')]
                    if mode == 'ambiguous_preview':
                        env['TEAM_CONNECT_UNAUTHENTICATED_DEMO'] = '1'
                    result = subprocess.run(call, env=env, capture_output=True, text=True, timeout=10)
                    with self.subTest(instance=instance, mode=mode):
                        self.assertNotEqual(result.returncode, 0)
                        expected = {'implicit_preview': 'Explicit local synthetic demo opt-in is required', 'ambiguous_preview': 'Choose authenticated mode or explicit preview'}.get(mode, 'Existing approved private identity store required' if instance == 'q1' else 'Approved Q3 account store unavailable')
                        self.assertIn(expected, result.stderr)
                        self.assertFalse((folder / 'state').exists())

    def test_q1_injects_actual_readonly_session_service_before_server_creation(self):
        spec = importlib.util.spec_from_file_location('publication_q1_launcher', ROOT / 'runtime/q1_launcher.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        captured = {}
        app = SimpleNamespace(build_review=lambda source: {}, Handler=object, make_server=lambda **kw: captured.update(kw) or captured)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            store = self.identity(folder, 'q1')
            before = store.read_bytes()
            with patch.object(launcher, 'load_module', return_value=app):
                launcher.create_server(REPO / 'apps/q1-customer-review', folder / 'inputs', folder / 'state', auth_store=store)
            auth = captured['auth']
            self.assertEqual(auth.instance, 'q1')
            self.assertEqual((auth.idle, auth.absolute), (1800, 28800))
            cookie = auth._cookie('tc_q1_session', 'temporary-session', 28800)[1]
            self.assertIn('HttpOnly; SameSite=Strict', cookie)
            self.assertNotIn('Max-Age', cookie)
            self.assertNotIn('Expires', cookie)
            self.assertEqual(store.read_bytes(), before)
            self.assertFalse((folder / 'state').exists())

    def test_q3_forces_enforced_mode_and_actual_readonly_session_service(self):
        captured = {}
        app = SimpleNamespace(Q3Handler=object)
        def main():
            captured['args'] = list(sys.argv)
            captured['auth'] = app.AuthService('q3', app.ReadOnlyAccounts(captured['store']))
        app.main = main
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            captured['store'] = self.identity(folder, 'q3')
            before = captured['store'].read_bytes()
            args = ['q3_launcher.py', '--app-root', str(REPO / 'apps/q3-community-planning'), '--auth-store', str(captured['store'])]
            with patch.object(sys, 'argv', args), patch.object(support, 'load_module', return_value=app), patch.dict(os.environ, {'TEAM_CONNECT_UNAUTHENTICATED_DEMO': '0'}):
                runpy.run_path(str(ROOT / 'runtime/q3_launcher.py'), run_name='__main__')
            at = captured['args'].index('--auth-mode')
            self.assertEqual(captured['args'][at + 1], 'enforced')
            auth = captured['auth']
            self.assertEqual(auth.instance, 'q3')
            self.assertEqual((auth.idle, auth.absolute), (1800, 28800))
            self.assertNotIn('Max-Age', auth._cookie('tc_q3_session', 'temporary-session', 28800)[1])
            self.assertEqual(captured['store'].read_bytes(), before)

    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose CLI unavailable; no daemon is required')
    def test_composed_auth_mode_removes_preview_and_keeps_identity_volumes_readonly(self):
        env = dict(os.environ, Q1_SOURCE_DIR='/tmp/publication-input-placeholder', Q1_IDENTITY_VOLUME='publication-q1-placeholder', Q3_IDENTITY_VOLUME='publication-q3-placeholder')
        env.pop('TEAM_CONNECT_UNAUTHENTICATED_DEMO', None)
        for isolated in [False, True]:
            args = ['docker', 'compose', '-f', 'compose.yaml', '-f', 'compose.authenticated.yaml']
            if isolated:
                args += ['-f', 'compose.authenticated-test.yaml']
            value = json.loads(subprocess.check_output(args + ['config', '--format', 'json'], cwd=ROOT, env=env))
            for name, uid, port in [('q1', '10001:10001', 8891), ('q3', '10002:10002', 8797)]:
                service = value['services'][name]
                self.assertFalse(service.get('environment'))
                self.assertIn('--auth-store', service['command'])
                identity = next(v for v in service['volumes'] if v['target'] == '/identity')
                self.assertTrue(identity['read_only'])
                self.assertEqual(identity['source'], name + '_identity')
                self.assertTrue(value['volumes'][name + '_identity']['external'])
                self.assertEqual(service['user'], uid)
                self.assertTrue(service['read_only'])
                self.assertEqual(service['cap_drop'], ['ALL'])
                if isolated:
                    self.assertFalse(service.get('ports'))
                else:
                    self.assertEqual(service['ports'][0]['host_ip'], '127.0.0.1')
                    self.assertEqual(service['ports'][0]['target'], port)

    def test_staged_q1_has_exact_signout_asset(self):
        self.assertEqual((ROOT / 'build/q1/app/assets/auth-session.mjs').read_bytes(), (REPO / 'apps/q1-customer-review/assets/auth-session.mjs').read_bytes())
        for instance in ['q1', 'q3']:
            self.assertEqual((ROOT / 'build' / instance / 'runtime/private_identity.py').read_bytes(), (ROOT / 'runtime/private_identity.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
