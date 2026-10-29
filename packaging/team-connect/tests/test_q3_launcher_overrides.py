"""Normalize auth-mode spellings before rejecting all app-mode overrides."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime'))
import q3_launcher
class Q3AuthModeOverrideTests(unittest.TestCase):
 def test_all_override_spellings_rejected_before_app_import(self):
  for suffix in [['--auth-mode','preview'],['--auth-mode=preview'],['--auth-m=preview'],['--auth-m','enforced'],['--auth-mode','enforced']]:
   with self.subTest(suffix=suffix),patch.object(sys,'argv',['q3_launcher','--app-root','/unused','--auth-store','/unused/private.sqlite3',*suffix]),patch.object(q3_launcher,'load_module') as load:
    with self.assertRaisesRegex(SystemExit,'Launcher selects auth mode from --auth-store'):q3_launcher.main()
    load.assert_not_called()
if __name__=='__main__':unittest.main()
