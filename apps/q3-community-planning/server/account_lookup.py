"""Read-only Q3 account store adapter. It creates no file or account."""
from contextlib import closing
from pathlib import Path
import os,sqlite3,stat
from local_auth import Account,PasswordRecord

class ReadOnlyAccounts:
 def __init__(self,path):
  self.path=Path(path)
  self._check_path()
  with closing(self._connect()) as db:
   self._check_schema(db)
   if db.execute("SELECT COUNT(*) FROM accounts WHERE role='manager' AND enabled=1").fetchone()[0]<1:raise ValueError('Approved enabled Q3 manager bootstrap required')
 def _check_path(self):
  if self.path.is_symlink() or not self.path.is_file():raise ValueError('Approved existing Q3 account store required')
  if self.path.stat().st_uid!=os.getuid() or self.path.parent.stat().st_uid!=os.getuid() or stat.S_IMODE(self.path.stat().st_mode)&0o077 or stat.S_IMODE(self.path.parent.stat().st_mode)&0o077:raise ValueError('Q3 account store must have owner-only file/directory permissions')
 def _check_schema(self,db):
  if db.execute('PRAGMA user_version').fetchone()[0]!=1 or db.execute('SELECT instance FROM instance_meta').fetchall()!=[('q3',)]:raise ValueError('Q3-specific account schema required')
  db.execute('SELECT account_id,username,role,salt,digest,enabled,credential_version FROM accounts LIMIT 0')
 def _connect(self):
  self._check_path();return sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
 def __call__(self,username):
  with closing(self._connect()) as db:
   self._check_schema(db)
   row=db.execute('SELECT account_id,username,role,salt,digest,enabled,credential_version FROM accounts WHERE username=?',(username,)).fetchone()
  if not row:return None
  ident,name,role,salt,digest,enabled,version=row
  if not isinstance(ident,str) or name!=username or role!='manager' or not isinstance(salt,bytes) or len(salt)!=16 or not isinstance(digest,bytes) or len(digest)!=32 or enabled not in (0,1) or not isinstance(version,int) or version<1:return None
  return Account(ident,name,role,PasswordRecord(salt,digest),enabled==1,version)
