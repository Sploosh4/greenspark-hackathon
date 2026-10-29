"""Private-store rejection and session-cookie regression; temporary fixture only."""
from pathlib import Path
import sys,unittest,tempfile,sqlite3
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'));sys.path.insert(0,str(ROOT.parents[1]/'apps/q3-community-planning/server'))
from private_identity import ReadOnlyIdentity,session_service_class,PARAMS
import local_auth
class PrivateIdentityTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'auth.sqlite3'
  with closing(sqlite3.connect(self.path)) as db, db:
   db.executescript('PRAGMA user_version=1;CREATE TABLE instance_meta(instance TEXT);CREATE TABLE accounts(account_id TEXT,username TEXT,role TEXT,salt BLOB,digest BLOB,enabled INTEGER,credential_version INTEGER,kdf TEXT);')
   db.execute('INSERT INTO instance_meta VALUES(?)',('q3',));db.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?)',('ephemeral','fixture','manager',b's'*16,b'd'*32,1,1,PARAMS))
  self.path.chmod(0o600)
 def test_other_instance_and_unsupported_cost_rejected(self):
  with self.assertRaises(ValueError):ReadOnlyIdentity(self.path,'q1',local_auth)
  with closing(sqlite3.connect(self.path)) as db, db:db.execute('UPDATE accounts SET kdf=?',('scrypt:N=16,r=1,p=1',))
  with self.assertRaises(ValueError):ReadOnlyIdentity(self.path,'q3',local_auth)
 def test_permissions_and_symlink_rejected(self):
  self.path.chmod(0o644)
  with self.assertRaises(ValueError):ReadOnlyIdentity(self.path,'q3',local_auth)
  self.path.chmod(0o600);link=self.path.with_name('alias.sqlite3');link.symlink_to(self.path)
  with self.assertRaises(ValueError):ReadOnlyIdentity(link,'q3',local_auth)
 def test_role_and_credential_changes_are_reloaded(self):
  lookup=ReadOnlyIdentity(self.path,'q3',local_auth);self.assertEqual(lookup('fixture').credential_version,1)
  self.assertIsNone(lookup("fixture' OR 1=1 --"))
  with closing(sqlite3.connect(self.path)) as db, db:db.execute('UPDATE accounts SET enabled=0,credential_version=2')
  self.assertFalse(lookup('fixture').enabled);self.assertEqual(lookup('fixture').credential_version,2)
  with closing(sqlite3.connect(self.path)) as db, db:db.execute('UPDATE accounts SET role=?',('officer',))
  self.assertIsNone(lookup('fixture'))
 def test_all_nonempty_cookies_are_session_only(self):
  auth=session_service_class(local_auth)('q1',lambda _:None)
  for name in ['tc_q1_session','tc_q1_challenge']:
   cookie=auth._cookie(name,'ephemeral',28800)[1]
   self.assertIn('HttpOnly; SameSite=Strict',cookie);self.assertNotIn('Max-Age',cookie);self.assertNotIn('Expires',cookie)
  self.assertIn('Max-Age=0',auth._cookie('tc_q1_session','',0)[1])
if __name__=='__main__':unittest.main()
