import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import accounts
import server


class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.data_patch = patch.object(server, 'DATA', Path(cls.temp.name)); cls.data_patch.start()
        cls.env_patch = patch.dict(os.environ, {'AI_MODE': 'demo', 'ADMIN_PASSWORD': 'test-admin-password'}); cls.env_patch.start()
        server.init_db()
        cls.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = f'http://127.0.0.1:{cls.httpd.server_port}'
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close(); cls.thread.join()
        cls.data_patch.stop(); cls.env_patch.stop(); cls.temp.cleanup()

    def setUp(self):
        self.cookie = ''
        server.Handler.user_attempts.clear()
        server.Handler.sessions.clear(); server.Handler.attempts.clear()
        with server.connect() as db:
            db.execute('DELETE FROM user_sessions'); db.execute('DELETE FROM users')

    def request(self, path, data=None, headers=None, method=None):
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json', 'Cookie': self.cookie, **(headers or {})}, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            result = json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw.decode()
            return response.status, result, response.headers

    def register(self, username='Student_01', password='student-test-password'):
        status, result, headers = self.request('/api/auth/register', {'username': username, 'password': password})
        if status == 201:
            self.cookie = headers['Set-Cookie'].split(';')[0]
        return status, result, headers

    def admin_cookie(self):
        status, _, headers = self.request('/api/login', {'password': 'test-admin-password'})
        self.assertEqual(status, 200)
        return headers['Set-Cookie'].split(';')[0]

    def test_admin_user_routes_reject_guests_and_students(self):
        for registered in (False, True):
            if registered:
                self.register()
            for path, data, method in [
                ('/api/admin/users', None, 'GET'),
                ('/api/admin/users/' + 'a' * 32, None, 'DELETE'),
                ('/api/admin/users/' + 'a' * 32 + '/password', {'password': 'new-password-729'}, 'POST'),
            ]:
                self.assertEqual(self.request(path, data, method=method)[0], 401)

    def test_admin_list_exposes_only_public_account_metadata(self):
        self.register()
        cookie = self.admin_cookie()
        status, users, _ = self.request('/api/admin/users', headers={'Cookie': cookie})
        self.assertEqual(status, 200)
        self.assertEqual(len(users), 1)
        self.assertEqual(set(users[0]), {'id', 'username', 'created'})
        self.assertEqual(users[0]['username'], 'Student_01')

    def test_admin_password_reset_revokes_all_target_sessions(self):
        _, result, _ = self.register()
        user_id = result['user']['id']
        first_session = self.cookie
        _, _, headers = self.request('/api/auth/login', {'username': 'Student_01', 'password': 'student-test-password'}, headers={'Cookie': ''})
        second_session = headers['Set-Cookie'].split(';')[0]
        self.cookie = ''  # Another browser must not rotate the first user's session.
        self.register('Other_user')
        other_session = self.cookie
        admin_cookie = self.admin_cookie()
        path = '/api/admin/users/' + user_id + '/password'
        self.assertEqual(self.request(path, {'password': 'short'}, headers={'Cookie': admin_cookie})[0], 400)
        self.assertIsNotNone(self.request('/api/auth/me', headers={'Cookie': first_session})[1]['user'])
        self.assertEqual(self.request(path, {'password': 'new-password-729'}, headers={'Cookie': admin_cookie})[0], 200)
        for cookie in (first_session, second_session):
            self.assertIsNone(self.request('/api/auth/me', headers={'Cookie': cookie})[1]['user'])
        self.assertIsNotNone(self.request('/api/auth/me', headers={'Cookie': other_session})[1]['user'])
        self.assertEqual(self.request('/api/auth/login', {'username': 'Student_01', 'password': 'student-test-password'})[0], 401)
        self.assertEqual(self.request('/api/auth/login', {'username': 'Student_01', 'password': 'new-password-729'})[0], 200)
        with server.connect() as db:
            stored = db.execute('SELECT password_hash FROM users WHERE id=?', (user_id,)).fetchone()[0]
        self.assertNotEqual(stored, 'new-password-729')
        self.assertTrue(accounts.verify_password('new-password-729', stored))

    def test_admin_delete_cascades_sessions_and_preserves_other_users(self):
        _, result, _ = self.register()
        user_id = result['user']['id']
        old_session = self.cookie
        self.register('Other_user')
        cookie = self.admin_cookie()
        path = '/api/admin/users/' + user_id
        self.assertEqual(self.request(path, headers={'Cookie': cookie}, method='DELETE')[0], 200)
        self.assertIsNone(self.request('/api/auth/me', headers={'Cookie': old_session})[1]['user'])
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_sessions WHERE user_id=?', (user_id,)).fetchone()[0], 0)
        self.assertEqual(self.request('/api/auth/login', {'username': 'Student_01', 'password': 'student-test-password'})[0], 401)
        self.assertEqual(self.request('/api/admin/users', headers={'Cookie': cookie})[1][0]['username'], 'Other_user')
        self.assertEqual(self.request(path, headers={'Cookie': cookie}, method='DELETE')[0], 404)
        self.assertEqual(self.request(path + '/password', {'password': 'valid-password-729'}, headers={'Cookie': cookie})[0], 404)

    def test_register_login_and_private_cookie(self):
        status, result, headers = self.register()
        self.assertEqual(status, 201)
        self.assertEqual(result['user']['username'], 'Student_01')
        for flag in ('HttpOnly', 'SameSite=Strict', 'Path=/', 'Max-Age=2592000'):
            self.assertIn(flag, headers['Set-Cookie'])
        self.assertNotIn('password', json.dumps(result))
        self.assertEqual(self.request('/api/auth/me')[1]['user'], result['user'])
        raw_token = self.cookie.split('=', 1)[1]
        with server.connect() as db:
            stored = db.execute('SELECT * FROM users').fetchone()
            session = db.execute('SELECT * FROM user_sessions').fetchone()
        self.assertNotEqual(stored['password_hash'], 'student-test-password')
        self.assertTrue(accounts.verify_password('student-test-password', stored['password_hash']))
        self.assertNotEqual(session['token_hash'], raw_token)
        self.assertEqual(session['token_hash'], accounts.token_hash(raw_token))
        self.assertFalse(self.request('/api/status')[1]['admin'])

    def test_username_casefold_uniqueness(self):
        self.assertEqual(self.register('Студент_01')[0], 201)
        self.assertEqual(self.register('студент_01')[0], 409)
        status, result, _ = self.request('/api/auth/login', {'username': 'СТУДЕНТ_01', 'password': 'student-test-password'})
        self.assertEqual(status, 200); self.assertEqual(result['user']['username'], 'Студент_01')
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 1)

    def test_passwords_have_distinct_salts(self):
        self.register('student_a'); self.register('student_b')
        with server.connect() as db:
            hashes = [r[0] for r in db.execute('SELECT password_hash FROM users')]
        self.assertEqual(len(set(hashes)), 2)
        self.assertTrue(all(accounts.verify_password('student-test-password', encoded) for encoded in hashes))

    def test_invalid_inputs_do_not_create_users(self):
        for username, password in [('ab', 'testpassword'), ('user name', 'testpassword'), ("a'; DROP TABLE users;--", 'testpassword'), ('user1', 'short'), ('user2', ' ' * 9), ('user3', ['invalid']), ('user4', 'bad\ud800password'), ('x' * 33, 'testpassword')]:
            self.assertEqual(self.register(username, password)[0], 400)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 0)

    def test_wrong_credentials_have_generic_error(self):
        self.register()
        self.cookie = ''
        incorrect = self.request('/api/auth/login', {'username': 'Student_01', 'password': 'incorrect-password'})
        missing = self.request('/api/auth/login', {'username': 'missing_user', 'password': 'incorrect-password'})
        self.assertEqual(incorrect[0], 401); self.assertEqual(missing[0], 401)
        self.assertEqual(incorrect[1], missing[1])
        self.assertNotIn('Set-Cookie', incorrect[2])

    def test_logout_revokes_copied_cookie(self):
        self.register(); copied_cookie = self.cookie
        self.assertEqual(self.request('/api/auth/logout', {})[0], 200)
        self.cookie = copied_cookie
        self.assertIsNone(self.request('/api/auth/me')[1]['user'])
        status, _, headers = self.request('/api/auth/login', {'username': 'Student_01', 'password': 'student-test-password'})
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.assertIsNotNone(self.request('/api/auth/me')[1]['user'])

    def test_login_rotates_session_and_accounts_are_independent(self):
        self.register('student_one'); cookie_one = self.cookie
        self.register('student_two'); cookie_two = self.cookie
        self.assertNotEqual(cookie_one, cookie_two)
        self.cookie = cookie_one
        self.assertIsNone(self.request('/api/auth/me')[1]['user'])
        self.cookie = cookie_two
        self.assertEqual(self.request('/api/auth/me')[1]['user']['username'], 'student_two')

    def test_expired_and_tampered_sessions(self):
        self.register()
        self.cookie += 'forged'
        self.assertIsNone(self.request('/api/auth/me')[1]['user'])
        with server.connect() as db:
            db.execute('UPDATE user_sessions SET expires=?', (time.time() - 1,))
        self.cookie = self.cookie[:-6]
        self.assertIsNone(self.request('/api/auth/me')[1]['user'])

    def test_database_survives_new_server_and_migration(self):
        self.register(); original_user = self.request('/api/auth/me')[1]['user']
        with server.connect() as db:
            db.execute('INSERT INTO materials (id,name,size,text,original) VALUES (?,?,?,?,?)',
                       ('test-preserved', 'keep.txt', 4, 'keep', b'keep'))
        server.init_db()
        second_server = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        second_thread = threading.Thread(target=second_server.serve_forever, daemon=True); second_thread.start()
        old_url = self.url
        try:
            self.url = f'http://127.0.0.1:{second_server.server_port}'
            self.assertEqual(self.request('/api/auth/me')[1]['user'], original_user)
            self.assertEqual(self.request('/api/auth/login', {'username': 'Student_01', 'password': 'student-test-password'})[0], 200)
            self.assertTrue(any(row['name'] == 'keep.txt' for row in self.request('/api/materials')[1]))
        finally:
            self.url = old_url; second_server.shutdown(); second_server.server_close(); second_thread.join()

    def test_user_cannot_become_administrator(self):
        self.register('admin')
        self.assertFalse(self.request('/api/status')[1]['admin'])
        self.assertEqual(self.request('/api/materials', {'name': 'a.txt', 'content': 'dGVzdA=='})[0], 401)
        self.assertEqual(self.request('/api/auth/register', {'username': 'cross_site', 'password': 'test-password'}, headers={'Origin': 'https://example.com'})[0], 403)

    def test_auth_rate_limit(self):
        for _ in range(30):
            self.assertEqual(self.request('/api/auth/login', {'username': 'bad', 'password': 'short'})[0], 401)
        self.assertEqual(self.request('/api/auth/login', {'username': 'bad', 'password': 'short'})[0], 429)


if __name__ == '__main__':
    unittest.main()
