"""Read-only native identity adapter and session-cookie profile. No provisioning."""
from pathlib import Path
import os,sqlite3,stat
from contextlib import closing
PARAMS='scrypt:N=131072,r=8,p=1,dklen=32'
def session_service_class(module):
    class SessionOnly(module.AuthService):
        def _cookie(self,name,value,age):
            if value:
                return ('Set-Cookie',f'{name}={value}; Path=/; HttpOnly; SameSite=Strict')
            return super()._cookie(name,value,age)
    return SessionOnly
class ReadOnlyIdentity:
    def __init__(self,path,instance,module):self.path=Path(path);self.instance=instance;self.module=module;self._check()
    def _check(self):
        if self.path.is_symlink() or not self.path.is_file():raise ValueError('Existing approved private identity store required')
        for p in [self.path,self.path.parent]:
            info=p.stat()
            if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:raise ValueError('Private owner-only identity store required')
        with closing(self._connect()) as db:
            if db.execute('PRAGMA user_version').fetchone()[0]!=1 or db.execute('SELECT instance FROM instance_meta').fetchall()!=[(self.instance,)]:raise ValueError('Wrong identity instance')
            if db.execute('SELECT DISTINCT kdf FROM accounts').fetchall()!=[(PARAMS,)]:raise ValueError('Unsupported password algorithm/cost')
    def _connect(self):return sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
    def __call__(self,username):
        self._check()
        with closing(self._connect()) as db:row=db.execute('SELECT account_id,username,role,salt,digest,enabled,credential_version,kdf FROM accounts WHERE username=?',(username,)).fetchone()
        if not row:return None
        ident,name,role,salt,digest,enabled,version,kdf=row
        if role not in ({'officer','manager'} if self.instance=='q1' else {'manager'}) or kdf!=PARAMS or not isinstance(salt,bytes) or not isinstance(digest,bytes) or len(salt)!=16 or len(digest)!=32 or enabled not in (0,1) or not isinstance(version,int) or version<1:return None
        return self.module.Account(ident,name,role,self.module.PasswordRecord(salt,digest),enabled==1,version)
