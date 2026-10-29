"""Current-mode constraints reject before server construction; no listener."""
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
import q1_launcher


class CurrentLauncherModes(unittest.TestCase):
    def reject(self, message, **options):
        app = SimpleNamespace(build_review=lambda: None, Handler=type('Handler', (), {}), make_server=Mock())
        prototype = ModuleType('prototype')
        prototype.uploads = SimpleNamespace()
        with patch.object(q1_launcher, 'load_module', return_value=app), patch.dict(sys.modules, {'prototype': prototype}):
            with self.assertRaisesRegex(ValueError, message):
                q1_launcher.create_server('unused-app', 'unused-inputs', 'unused-state', **options)
        app.make_server.assert_not_called()

    def test_current_uploads_require_authenticated_mode(self):
        self.reject('Current synthetic uploads require authenticated mode', current_uploads=True)

    def test_current_interpreter_cannot_enable_mode_implicitly(self):
        self.reject('Current interpreter requires current uploads', current_python='unused-python')
