"""Optional browser QA: pip install playwright; uses already installed Microsoft Edge."""
import io
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from docx import Document
from playwright.sync_api import sync_playwright, expect
from test_app import pdf_bytes


def main():
    artifacts = server.ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary, patch.object(server, 'DATA', Path(temporary)), patch.dict(os.environ, {'AI_MODE': 'demo', 'ADMIN_PASSWORD': 'browser-test-password'}):
        server.init_db()
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        url = f'http://127.0.0.1:{httpd.server_port}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='msedge', headless=True)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                errors = []
                requests = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: requests.append(request.url))
                page.goto(url)
                expect(page.locator('#mode-status')).to_contain_text('Деморежим')
                page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                expect(page.locator('html')).to_have_css('background-color', 'rgb(255, 255, 255)')
                page.get_by_role('button', name='Включить тёмную тему').click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                expect(page.locator('html')).to_have_css('background-color', 'rgb(32, 33, 35)')
                expect(page.locator('[data-theme-toggle]')).to_have_attribute('aria-pressed', 'true')
                page.screenshot(path=str(artifacts / 'dark-desktop.png'), full_page=True)
                page.reload()
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                peer = context.new_page()
                peer.goto(url + '/admin')
                expect(peer.locator('html')).to_have_attribute('data-theme', 'dark')
                peer.screenshot(path=str(artifacts / 'dark-admin.png'), full_page=True)
                peer.get_by_role('button', name='Включить светлую тему').click()
                page.bring_to_front()
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.locator('[data-theme-toggle]').focus()
                page.locator('[data-theme-toggle]').press('Space')
                peer.bring_to_front()
                expect(peer.locator('html')).to_have_attribute('data-theme', 'dark')
                peer.close()
                page.locator('#prompt').fill('Объясни производную')
                page.locator('#send').click()
                expect(page.locator('.message.assistant')).to_contain_text('Пример структуры объяснения')
                page.locator('#new-chat').click()
                page.locator('[data-mode="report"]').click()
                expect(page.locator('#current-mode')).to_have_text('Помочь с отчётом')
                page.locator('#suggestions button').first.click()
                page.locator('#prompt').press('Enter')
                expect(page.locator('.message.assistant')).to_contain_text('не ответ ИИ')
                expect(page.locator('.message.assistant')).to_contain_text('Шаблон отчёта')
                page.reload()
                page.locator('#history .history-open').first.click()
                expect(page.locator('.message.assistant')).to_contain_text('Шаблон отчёта')
                page.locator('#new-chat').click()
                page.locator('[data-mode="presentation"]').click()
                page.locator('#prompt').fill('Презентация о физике')
                page.locator('#send').click()
                expect(page.locator('.message.assistant')).to_contain_text('Шаблон презентации')
                # Delete only the chosen chat; cancellation and reload preserve the rest.
                expect(page.locator('#history .history-open')).to_have_count(3)
                page.once('dialog', lambda dialog: dialog.dismiss())
                page.locator('#history .history-delete').nth(1).click()
                expect(page.locator('#history .history-open')).to_have_count(3)
                page.once('dialog', lambda dialog: dialog.accept())
                page.locator('#history .history-delete').nth(1).click()
                expect(page.locator('#history .history-open')).to_have_count(2)
                expect(page.locator('.message.assistant')).to_contain_text('Шаблон презентации')
                page.reload()
                expect(page.locator('#history .history-open')).to_have_count(2)
                page.locator('#history .history-open').first.click()
                expect(page.locator('.message.assistant')).to_contain_text('Шаблон презентации')
                page.once('dialog', lambda dialog: dialog.accept())
                page.locator('#history .history-delete').first.click()
                expect(page.locator('#welcome')).to_be_visible()
                expect(page.locator('.message')).to_have_count(0)
                expect(page.locator('#history .history-open')).to_have_count(1)
                page.once('dialog', lambda dialog: dialog.accept())
                page.locator('#history .history-delete').click()
                expect(page.locator('#history .empty-history')).to_be_visible()
                page.reload()
                expect(page.locator('#history .history-open')).to_have_count(0)
                page.goto(url + '/admin')
                page.locator('#password').fill('browser-test-password')
                page.locator('#login-form button').click()
                expect(page.locator('#manage-panel')).to_be_visible()
                doc = Document(); doc.add_paragraph('Лабораторная работа: закон Ома')
                output = io.BytesIO(); doc.save(output)
                page.locator('#files').set_input_files([
                    {'name': 'physics.txt', 'mimeType': 'text/plain', 'buffer': 'Закон Ома: I = U / R.'.encode()},
                    {'name': 'report.docx', 'mimeType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'buffer': output.getvalue()},
                    {'name': 'lecture.pdf', 'mimeType': 'application/pdf', 'buffer': pdf_bytes()},
                ])
                page.locator('#upload-button').click()
                expect(page.locator('#total')).to_have_text('3')
                page.screenshot(path=str(artifacts / 'admin.png'), full_page=True)
                # A separate browser context has no administrator cookie.
                student_context = browser.new_context(viewport={'width': 1100, 'height': 800})
                student = student_context.new_page()
                student.goto(url)
                expect(student.locator('html')).to_have_attribute('data-theme', 'light')
                student.get_by_role('button', name='Включить тёмную тему').click()
                student.locator('#materials-button').click()
                expect(student.locator('#material-list .material-row')).to_have_count(3)
                for name in ('physics.txt', 'report.docx', 'lecture.pdf'):
                    with student.expect_download() as download_info:
                        student.get_by_role('link', name='Скачать ' + name, exact=True).click()
                    download = download_info.value
                    assert download.suggested_filename == name
                    assert download.failure() is None
                with student.expect_popup() as preview_info:
                    student.get_by_role('link', name='Открыть report.docx', exact=True).click()
                preview = preview_info.value
                expect(preview.locator('pre')).to_contain_text('Лабораторная работа: закон Ома')
                expect(preview.locator('html')).to_have_attribute('data-theme', 'dark')
                preview.close()
                with student.expect_popup() as text_info:
                    student.get_by_role('link', name='Открыть physics.txt', exact=True).click()
                text_preview = text_info.value
                expect(text_preview.locator('body')).to_contain_text('Закон Ома: I = U / R.')
                text_preview.close()
                student.locator('#close-dialog').click()
                student.locator('#prompt').fill('Объясни закон Ома')
                student.locator('#send').click()
                expect(student.locator('.message.assistant')).to_contain_text('Локальный поиск по документам')
                expect(student.locator('.message.assistant')).to_contain_text('I = U / R')
                student.locator('.sources summary').first.click()
                expect(student.locator('.sources a').first).to_have_attribute('href', __import__('re').compile(r'/api/materials/[a-f0-9]{24}/view'))
                expect(student.locator('.sources blockquote').first).to_be_visible()
                student.locator('#materials-button').click()
                student.screenshot(path=str(artifacts / 'shared-materials.png'), full_page=True)
                student_context.close()
                page.on('dialog', lambda dialog: dialog.accept())
                page.locator('#admin-materials button').first.click()
                expect(page.locator('#total')).to_have_text('2')
                page.locator('#logout').click()
                expect(page.locator('#login-panel')).to_be_visible()
                page.goto(url)
                page.locator('#materials-button').click()
                expect(page.locator('#material-list .material-row')).to_have_count(2)
                page.locator('#close-dialog').click()
                page.set_viewport_size({'width': 390, 'height': 844})
                expect(page.locator('#sidebar')).to_have_css('transform', 'matrix(1, 0, 0, 1, -224, 0)')
                page.screenshot(path=str(artifacts / 'mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                page.get_by_role('button', name='Включить светлую тему').click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                expect(page.locator('html')).to_have_css('background-color', 'rgb(255, 255, 255)')
                page.locator('#menu').click()
                expect(page.locator('#sidebar')).to_have_class('sidebar open')
                page.keyboard.press('Escape')
                assert not errors, errors
                assert all(request.startswith(url) for request in requests), 'Unexpected external request'
                browser.close()
                print('Browser QA passed: desktop, mobile, 3 modes, history, admin, PDF/DOCX/TXT upload, delete, logout; no JS errors or external page requests.')
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__':
    main()
