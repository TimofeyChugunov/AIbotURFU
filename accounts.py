"""Persistent student accounts; separate from administrator credentials."""
import hashlib
import re
import secrets
import sqlite3
import time
import unicodedata

PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 30 * 24 * 3600
COOKIE_NAME = 'aibot_user'


class AccountError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL, created REAL NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS user_sessions (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires REAL NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS user_session_expiry ON user_sessions(expires)')


def normalize_username(value):
    if not isinstance(value, str) or len(value) > 64:
        raise AccountError('Username должен содержать от 3 до 32 символов.')
    username = unicodedata.normalize('NFKC', value).strip()
    if not re.fullmatch(r'[A-Za-zА-Яа-яЁё0-9_.-]{3,32}', username):
        raise AccountError('Username: 3–32 символа, русские или латинские буквы, цифры, точка, дефис и подчёркивание.')
    return username, username.casefold()


def validate_password(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 128 or not password.strip():
        raise AccountError('Пароль должен содержать от 8 до 128 символов и не состоять только из пробелов.')
    try:
        password.encode('utf-8')
    except UnicodeError:
        raise AccountError('Пароль содержит некорректные символы.')


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PASSWORD_ITERATIONS)
    return f'pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password, encoded):
    algorithm, rounds, salt, expected = encoded.split('$')
    if algorithm != 'pbkdf2_sha256':
        return False
    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(rounds))
    return secrets.compare_digest(actual, bytes.fromhex(expected))


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def revoke_session(db, token):
    if token:
        db.execute('DELETE FROM user_sessions WHERE token_hash=?', (token_hash(token),))


def create_session(db, user_id, previous_token=''):
    revoke_session(db, previous_token)
    db.execute('DELETE FROM user_sessions WHERE expires<=?', (time.time(),))
    token = secrets.token_urlsafe(32)
    db.execute('INSERT INTO user_sessions (token_hash,user_id,expires) VALUES (?,?,?)',
               (token_hash(token), user_id, time.time() + SESSION_SECONDS))
    return token


def current_user(db, token):
    if not token or len(token) > 128:
        return None
    row = db.execute('''SELECT users.id, users.username FROM user_sessions
        JOIN users ON users.id=user_sessions.user_id WHERE token_hash=? AND expires>?''',
        (token_hash(token), time.time())).fetchone()
    return dict(row) if row else None


def register(db, username, password, previous_token=''):
    username, key = normalize_username(username)
    validate_password(password)
    user = {'id': secrets.token_hex(16), 'username': username}
    encoded = hash_password(password)
    try:
        db.execute('INSERT INTO users (id,username,username_key,password_hash,created) VALUES (?,?,?,?,?)',
                   (user['id'], username, key, encoded, time.time()))
    except sqlite3.IntegrityError:
        raise AccountError('Этот Username уже занят. Выберите другой.', 409)
    return user, create_session(db, user['id'], previous_token)


def login(db, username, password, previous_token=''):
    try:
        _, key = normalize_username(username)
        validate_password(password)
    except AccountError:
        raise AccountError('Неверный Username или пароль.', 401)
    row = db.execute('SELECT id,username,password_hash FROM users WHERE username_key=?', (key,)).fetchone()
    # Keep unknown-user checks computationally comparable to password checks.
    encoded = row['password_hash'] if row else f'pbkdf2_sha256${PASSWORD_ITERATIONS}${"00" * 16}${"00" * 32}'
    verified = verify_password(password, encoded)
    if not row or not verified:
        raise AccountError('Неверный Username или пароль.', 401)
    user = {'id': row['id'], 'username': row['username']}
    return user, create_session(db, user['id'], previous_token)
