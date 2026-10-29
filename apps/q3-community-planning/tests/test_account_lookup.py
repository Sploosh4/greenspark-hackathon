from contextlib import closing
import os,secrets,sqlite3,tempfile,unittest
from pathlib import Path
import test_source_adapter as fixtures
from account_lookup import ReadOnlyAccounts
from local_auth import hash_password

class AccountLookup(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.record=hash_password(secrets.token_urlsafe(24))
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);os.chmod(self.root,0o700);self.path=self.root/'ephemeral-auth.sqlite3'
  with closing(sqlite3.connect(self.path)) as db, db:
   db.executescript('PRAGMA user_version=1; CREATE TABLE instance_meta(instance TEXT NOT NULL); INSERT INTO instance_meta VALUES (\'q3\'); CREATE TABLE accounts(account_id TEXT,username TEXT UNIQUE,role TEXT,salt BLOB,digest BLOB,enabled INTEGER,credential_version INTEGER);')
   db.execute('INSERT INTO accounts VALUES (?,?,?,?,?,?,?)',('ephemeral','manager','manager',self.record.salt,self.record.digest,1,1))
  os.chmod(self.path,0o600)
 def tearDown(self):self.temp.cleanup()
 def test_readonly_lookup_and_disable_are_observed(self):
  lookup=ReadOnlyAccounts(self.path);self.assertEqual(lookup('manager').role,'manager');self.assertIsNone(lookup('absent'))
  with closing(sqlite3.connect(self.path)) as db, db:db.execute("UPDATE accounts SET enabled=0 WHERE username='manager'")
  self.assertFalse(lookup('manager').enabled)
 def test_wrong_instance_permissions_empty_and_missing_fail_without_creating(self):
  missing=self.root/'missing.sqlite3'
  with self.assertRaises(ValueError):ReadOnlyAccounts(missing)
  self.assertFalse(missing.exists());os.chmod(self.path,0o644)
  with self.assertRaises(ValueError):ReadOnlyAccounts(self.path)
  os.chmod(self.path,0o600)
  with closing(sqlite3.connect(self.path)) as db, db:db.execute("UPDATE instance_meta SET instance='q1'")
  with self.assertRaises(ValueError):ReadOnlyAccounts(self.path)
 def test_no_enabled_manager_fails_before_service_activation(self):
  with closing(sqlite3.connect(self.path)) as db, db:db.execute('DELETE FROM accounts')
  with self.assertRaises(ValueError):ReadOnlyAccounts(self.path)

 def test_runtime_changed_instance_and_permissions_fail_closed(self):
  lookup=ReadOnlyAccounts(self.path)
  with closing(sqlite3.connect(self.path)) as db, db:db.execute("UPDATE instance_meta SET instance='q1'")
  with self.assertRaises(ValueError):lookup('manager')
  with closing(sqlite3.connect(self.path)) as db, db:db.execute("UPDATE instance_meta SET instance='q3'")
  os.chmod(self.path,0o644)
  with self.assertRaises(ValueError):lookup('manager')
