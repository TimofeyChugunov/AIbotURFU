"""Admin account management in an isolated database; no model calls."""
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import expect, sync_playwright


def main():
    with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA', Path(tmp)), patch.dict(
        os.environ, {'AI_MODE': 'demo', 'ADMIN_PASSWORD': 'browser-admin-password'}
    ):
        server.init_db()
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{httpd.server_port}'
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge', headless=True)
                try:
                    student = browser.new_context()
                    response = student.request.post(url + '/api/auth/register', data={
                        'username': 'student_729', 'password': 'old-password-729'})
                    assert response.status == 201
                    context = browser.new_context()
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(url + '/admin')
                    expect(page.locator('#users-panel')).to_be_hidden()
                    page.locator('#password').fill('browser-admin-password')
                    page.locator('#login-form .primary-button').click()
                    expect(page.locator('#users-panel')).to_be_visible()
                    expect(page.locator('#admin-users .file-info strong')).to_have_text('student_729')
                    page.locator('.reset-user-password').click()
                    page.locator('#new-user-password').fill('new-password-729')
                    page.locator('#confirm-user-password').fill('mismatch-729')
                    page.locator('#save-user-password').click()
                    expect(page.locator('#password-feedback')).not_to_be_empty()
                    page.locator('#confirm-user-password').fill('new-password-729')
                    page.locator('#save-user-password').click()
                    expect(page.locator('#reset-password-dialog')).not_to_be_visible()
                    expect(page.locator('#users-feedback')).not_to_be_empty()
                    assert (student.request.get(url + '/api/auth/me').json())['user'] is None
                    assert student.request.post(url + '/api/auth/login', data={
                        'username': 'student_729', 'password': 'old-password-729'}).status == 401
                    assert student.request.post(url + '/api/auth/login', data={
                        'username': 'student_729', 'password': 'new-password-729'}).status == 200
                    page.reload()
                    expect(page.locator('.user-row')).to_have_count(1)
                    page.locator('[data-theme-toggle]').click()
                    page.set_viewport_size({'width': 390, 'height': 844})
                    expect(page.locator('.delete-user')).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.once('dialog', lambda dialog: dialog.dismiss())
                    page.locator('.delete-user').click()
                    expect(page.locator('.user-row')).to_have_count(1)
                    page.once('dialog', lambda dialog: dialog.accept())
                    page.locator('.delete-user').click()
                    expect(page.locator('.user-row')).to_have_count(0)
                    expect(page.locator('#users-total')).to_have_text('0')
                    assert (student.request.get(url + '/api/auth/me').json())['user'] is None
                    page.locator('#logout').click()
                    expect(page.locator('#users-panel')).to_be_hidden()
                    expect(page.locator('#admin-users')).to_be_empty()
                    assert not errors, errors
                    print('Admin users browser QA passed: list, reset, revoked sessions, delete/cancel, logout, mobile/dark.')
                finally:
                    browser.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()


if __name__ == '__main__':
    main()
