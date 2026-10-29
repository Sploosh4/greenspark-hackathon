"""Local-prototype server authentication. No credential persistence or bootstrap.

The application supplies an authoritative, thread-safe lookup(username)->Account.
This module stores sessions/challenges/rate limits only in bounded process memory.
It must be wired before every private data, static, map and mutation handler.
"""
from collections import OrderedDict, deque
from dataclasses import dataclass
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import json
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

AUTH_PATHS = {'/api/auth/challenge', '/api/auth/login', '/api/auth/logout', '/api/session'}
MUTATIONS = {'POST', 'PUT', 'PATCH', 'DELETE'}
CAPABILITIES = {'q1': {'officer': {'review', 'upload', 'export'}, 'manager': {'review', 'upload', 'export', 'settings'}},
                'q3': {'manager': {'q3'}}}


class AuthError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


@dataclass(frozen=True)
class PasswordRecord:
    salt: bytes
    digest: bytes


@dataclass(frozen=True)
class Account:
    account_id: str
    username: str
    role: str
    password: PasswordRecord
    enabled: bool = True
    credential_version: int = 1


@dataclass(frozen=True)
class Principal:
    account_id: str
    username: str
    role: str
    csrf_token: str


@dataclass(frozen=True)
class Reply:
    status: int
    body: dict
    headers: tuple = ()


def canonical_username(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}', value):
        return None
    return value.casefold()


def password_digest(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 256 or len(password.encode('utf-8')) > 1024:
        raise ValueError('Password must contain 12–256 characters and at most 1024 UTF-8 bytes')
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=131072, r=8, p=1, dklen=32, maxmem=256 * 1024**2)


def hash_password(password):
    salt = secrets.token_bytes(16)
    return PasswordRecord(salt, password_digest(password, salt))


def header(headers, name):
    if hasattr(headers, 'get_all'):
        values = headers.get_all(name) or []
    else:
        values = [v for k, v in headers.items() if k.casefold() == name.casefold()]
    if len(values) > 1:
        raise AuthError(400, 'Duplicate security header')
    if values and not isinstance(values[0], str):
        raise AuthError(400, 'Invalid security header')
    return values[0] if values else ''


def equal_token(value, expected):
    return isinstance(value, str) and value.isascii() and hmac.compare_digest(value, expected)


def cookie_value(headers, name):
    raw = header(headers, 'Cookie')
    if len(raw) > 8192:
        raise AuthError(400, 'Invalid cookie')
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except CookieError:
        raise AuthError(400, 'Invalid cookie') from None
    value = cookie.get(name)
    return value.value if value else ''


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    """One instance per server, with canonical port 8891 (Q1) or 8797 (Q3)."""
    def __init__(self, instance, lookup_account, *, clock=time.time, idle_seconds=1800, absolute_seconds=28800):
        if instance not in CAPABILITIES:
            raise ValueError('Unknown application instance')
        self.instance, self.lookup, self.clock = instance, lookup_account, clock
        self.port = {'q1': 8891, 'q3': 8797}[instance]
        self.idle, self.absolute = idle_seconds, absolute_seconds
        if not 1 <= self.idle <= self.absolute <= 28800:
            raise ValueError('Invalid session expiry configuration')
        self.cookie = f'tc_{instance}_session'
        self.pre_cookie = f'tc_{instance}_prelogin'
        self.sessions, self.challenges = {}, OrderedDict()
        self.attempts, self.global_attempts = OrderedDict(), deque()
        self.lock, self.verifier = threading.RLock(), threading.BoundedSemaphore(1)
        self.dummy = hash_password(secrets.token_urlsafe(24))

    def _host(self, headers):
        host = header(headers, 'Host')
        if host not in {f'127.0.0.1:{self.port}', f'localhost:{self.port}'}:
            raise AuthError(403, 'Canonical local host required')
        if header(headers, 'Sec-Fetch-Site') == 'cross-site':
            raise AuthError(403, 'Same-origin request required')
        return host

    def _origin(self, headers):
        host = self._host(headers)
        if header(headers, 'Origin') != 'http://' + host:
            raise AuthError(403, 'Same-origin request required')

    def _cookie(self, name, value, age):
        # Deliberate local HTTP profile. HTTPS integration must add Secure.
        return ('Set-Cookie', f'{name}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}')

    def _prune(self):
        now = self.clock()
        self.sessions = {key: value for key, value in self.sessions.items()
                         if now - value['created'] < self.absolute and now - value['seen'] < self.idle}
        for key in list(self.challenges):
            if now - self.challenges[key]['created'] >= 300:
                del self.challenges[key]

    def _rate(self, username):
        now = self.clock()
        with self.lock:
            while self.global_attempts and now - self.global_attempts[0] >= 60:
                self.global_attempts.popleft()
            recent = self.attempts.pop(username, deque())
            while recent and now - recent[0] >= 60:
                recent.popleft()
            blocked = len(recent) >= 5 or len(self.global_attempts) >= 20
            if not blocked:
                recent.append(now)
                self.global_attempts.append(now)
            self.attempts[username] = recent
            while len(self.attempts) > 1024:
                self.attempts.popitem(last=False)
            if blocked:
                raise AuthError(429, 'Sign-in temporarily unavailable')

    def _principal(self, headers):
        self._host(headers)
        token = cookie_value(headers, self.cookie)
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise AuthError(401, 'Sign-in required')
        with self.lock:
            self._prune()
            key = token_hash(token)
            state = self.sessions.get(key)
            if state is None:
                raise AuthError(401, 'Sign-in required')
            account = self.lookup(state['username'])
            if (not account or not account.enabled or account.account_id != state['account_id']
                    or account.credential_version != state['version'] or account.role != state['role']
                    or account.role not in CAPABILITIES[self.instance]):
                self.sessions.pop(key, None)
                raise AuthError(401, 'Sign-in required')
            state['seen'] = self.clock()
            return Principal(account.account_id, account.username, account.role, state['csrf']), key

    def authorize(self, method, target, headers, capability):
        """Call before reading an upload/body or returning any private resource."""
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or method not in {'GET', 'HEAD'} | MUTATIONS:
            raise AuthError(400, 'Unsupported request target or method')
        principal, _ = self._principal(headers)
        if capability not in CAPABILITIES[self.instance][principal.role]:
            raise AuthError(403, 'Access denied')
        if method in MUTATIONS:
            self._origin(headers)
            if not equal_token(header(headers, 'X-Team-Connect-CSRF'), principal.csrf_token):
                raise AuthError(403, 'Request verification failed')
        return principal

    def auth_route(self, method, target, headers, body=b''):
        """Return Reply for known auth APIs; None for an application-owned route.

        Caller must bound HTTP transport read to 4096 bytes before supplying body,
        reject chunked/ambiguous framing, and emit every Reply header verbatim.
        """
        parsed = urlsplit(target)
        if parsed.path not in AUTH_PATHS:
            return None
        try:
            if parsed.scheme or parsed.netloc:
                raise AuthError(400, 'Unsupported request target')
            self._host(headers)
            path = parsed.path
            if path == '/api/auth/challenge' and method == 'GET':
                nonce, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                with self.lock:
                    self._prune()
                    self.challenges[token_hash(nonce)] = {'csrf': csrf, 'created': self.clock()}
                    while len(self.challenges) > 256:
                        self.challenges.popitem(last=False)
                return Reply(200, {'csrf_token': csrf}, (self._cookie(self.pre_cookie, nonce, 300),))
            if path == '/api/session' and method == 'GET':
                principal, _ = self._principal(headers)
                return Reply(200, {'authenticated': True, 'account_id': principal.account_id,
                                  'username': principal.username, 'role': principal.role, 'csrf_token': principal.csrf_token,
                                  'capabilities': sorted(CAPABILITIES[self.instance][principal.role]),
                                  'idle_seconds': self.idle, 'absolute_seconds': self.absolute})
            if path == '/api/auth/login' and method == 'POST':
                self._origin(headers)
                if header(headers, 'Content-Type').split(';')[0].strip() != 'application/json' or not isinstance(body, bytes) or not 0 < len(body) <= 4096:
                    raise AuthError(400, 'Invalid sign-in request')
                with self.lock:
                    challenge = self.challenges.pop(token_hash(cookie_value(headers, self.pre_cookie)), None)
                if not challenge or self.clock() - challenge['created'] >= 300 or not equal_token(header(headers, 'X-Team-Connect-CSRF'), challenge['csrf']):
                    raise AuthError(403, 'Request verification failed')
                def object_pairs(pairs):
                    value = {}
                    for key, item in pairs:
                        if key in value:
                            raise ValueError('Duplicate field')
                        value[key] = item
                    return value
                try:
                    data = json.loads(body, object_pairs_hook=object_pairs)
                    if not isinstance(data, dict) or set(data) != {'username', 'password'}:
                        raise ValueError('Fields')
                    username = canonical_username(data['username'])
                    password = data['password']
                    if username is None or not isinstance(password, str):
                        raise ValueError('Credentials')
                except (ValueError, UnicodeError):
                    raise AuthError(400, 'Invalid sign-in request') from None
                self._rate(username)
                if not self.verifier.acquire(blocking=False):
                    raise AuthError(429, 'Sign-in temporarily unavailable')
                try:
                    account = self.lookup(username)
                    record = account.password if account else self.dummy
                    try:
                        valid = hmac.compare_digest(password_digest(password, record.salt), record.digest)
                    except ValueError:
                        # Still perform the configured dummy KDF for a malformed password.
                        password_digest('invalid-' + secrets.token_urlsafe(24), self.dummy.salt)
                        valid = False
                    if not valid or not account or not account.enabled or account.role not in CAPABILITIES[self.instance]:
                        raise AuthError(401, 'Invalid sign-in details')
                finally:
                    self.verifier.release()
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                with self.lock:
                    self._prune()
                    if len(self.sessions) >= 256:
                        raise AuthError(503, 'Session capacity reached')
                    now = self.clock()
                    self.sessions[token_hash(token)] = {'account_id': account.account_id, 'username': account.username,
                                                        'role': account.role, 'version': account.credential_version,
                                                        'csrf': csrf, 'created': now, 'seen': now}
                return Reply(200, {'authenticated': True, 'role': account.role, 'csrf_token': csrf},
                             (self._cookie(self.cookie, token, self.absolute), self._cookie(self.pre_cookie, '', 0)))
            if path == '/api/auth/logout' and method == 'POST':
                capability = 'review' if self.instance == 'q1' else 'q3'
                self.authorize(method, target, headers, capability)
                with self.lock:
                    self.sessions.pop(token_hash(cookie_value(headers, self.cookie)), None)
                return Reply(200, {'authenticated': False}, (self._cookie(self.cookie, '', 0),))
            raise AuthError(405, 'Method not allowed')
        except AuthError as error:
            return Reply(error.status, {'error': error.message})
