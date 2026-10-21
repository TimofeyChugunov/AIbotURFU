"""Account UI integration with isolated database and browser storage; no model calls."""
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import sync_playwright, expect


def main():
    artifacts = server.ROOT / 'artifacts'; artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary, patch.object(server, 'DATA', Path(temporary)), patch.dict(os.environ, {'AI_MODE': 'demo'}):
        server.init_db()
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        url = f'http://127.0.0.1:{httpd.server_port}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='msedge', headless=True)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page(); errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.locator('#mode-status')).to_contain_text('Деморежим')
                page.locator('#prompt').fill('Гостевой вопрос')
                page.locator('#send').click()
                expect(page.locator('.message.assistant')).to_be_visible()
                page.locator('#account-link').click()
                expect(page.locator('#auth-form')).to_be_visible()
                page.screenshot(path=str(artifacts / 'login-light.png'), full_page=True)
                page.get_by_role('tab', name='Регистрация', exact=True).click()
                page.locator('#username').fill('Студент_01')
                page.locator('#account-password').fill('browser-test-password')
                page.locator('#password-confirm').fill('different-password')
                page.locator('#auth-submit').click()
                expect(page.locator('#auth-feedback')).to_contain_text('не совпадают')
                page.locator('#password-confirm').fill('browser-test-password')
                page.screenshot(path=str(artifacts / 'register-light.png'), full_page=True)
                page.locator('#auth-submit').click()
                expect(page.locator('#profile-username')).to_have_text('Студент_01')
                expect(page.locator('#history .history-open')).to_have_count(0)
                page.locator('#prompt').fill('Личный вопрос первого пользователя')
                page.locator('#send').click()
                expect(page.locator('.message.assistant')).to_be_visible()
                page.reload()
                expect(page.locator('#profile-username')).to_have_text('Студент_01')
                expect(page.locator('#history .history-open')).to_have_count(1)
                page.screenshot(path=str(artifacts / 'account-chat.png'), full_page=True)
                peer = context.new_page(); peer.goto(url)
                expect(peer.locator('#profile-username')).to_have_text('Студент_01')
                peer.locator('#user-logout').click()
                expect(peer.locator('#profile-username')).to_have_text('Гость')
                page.bring_to_front()
                expect(page.locator('#profile-username')).to_have_text('Гость')
                expect(page.locator('#history .history-open')).to_have_text('Гостевой вопрос')
                page.locator('#account-link').click()
                page.get_by_role('tab', name='Регистрация', exact=True).click()
                page.locator('#username').fill('student_02')
                page.locator('#account-password').fill('browser-test-password')
                page.locator('#password-confirm').fill('browser-test-password')
                page.locator('#auth-submit').click()
                expect(page.locator('#profile-username')).to_have_text('student_02')
                expect(page.locator('#history .history-open')).to_have_count(0)
                page.locator('#user-logout').click()
                expect(page.locator('#profile-username')).to_have_text('Гость')
                page.locator('#account-link').click()
                page.locator('#username').fill('студент_01')
                page.locator('#account-password').fill('wrong-test-password')
                page.locator('#auth-submit').click()
                expect(page.locator('#auth-feedback')).to_contain_text('Неверный Username или пароль')
                page.locator('#account-password').fill('browser-test-password')
                page.locator('#auth-submit').click()
                expect(page.locator('#profile-username')).to_have_text('Студент_01')
                expect(page.locator('#history .history-open')).to_have_text('Личный вопрос первого пользователя')
                page.locator('#account-link').click()
                expect(page.locator('#account-session')).to_be_visible()
                page.locator('#account-signout').click()
                expect(page.locator('#auth-form')).to_be_visible()
                page.get_by_role('button', name='Включить тёмную тему').click()
                page.screenshot(path=str(artifacts / 'login-dark.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.get_by_role('tab', name='Регистрация', exact=True).click()
                page.screenshot(path=str(artifacts / 'register-mobile-dark.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
                new_context = browser.new_context()
                fresh = new_context.new_page(); fresh.goto(url + '/auth')
                fresh.locator('#username').fill('Студент_01')
                fresh.locator('#account-password').fill('browser-test-password')
                fresh.locator('#auth-submit').click()
                expect(fresh.locator('#profile-username')).to_have_text('Студент_01')
                expect(fresh.locator('#history .history-open')).to_have_count(0)
                assert not errors, errors
                browser.close()
                print('Account browser QA passed: register, password confirmation, later login, logout, sessions, two accounts, isolated histories, cross-tab logout, new browser login, light/dark/mobile.')
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__':
    main()
