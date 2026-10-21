"""Private DOCX upload, follow-ups and isolation; temporary DB, no model calls."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import expect, sync_playwright
from test_docx_review import document_bytes


def main():
    with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA', Path(tmp)), patch.dict(os.environ, {'AI_MODE': 'demo'}):
        server.init_db()
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{httpd.server_port}'
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge', headless=True)
                try:
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    requests, errors = [], []
                    page.on('request', lambda request: requests.append(request.post_data_json) if request.url.endswith('/api/chat') else None)
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(url)
                    expect(page.locator('#send')).to_be_enabled()
                    content = document_bytes('Личная работа PRIVATE-CHECK-729. Цель и задачи исследования.')
                    page.locator('#chat-document').set_input_files({'name': 'private.docx', 'mimeType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'buffer': content})
                    expect(page.locator('#chat-attachment-name')).to_have_text('private.docx')
                    page.locator('#send').click()  # No typed question: use default review request.
                    expect(page.locator('.document-review')).to_contain_text('Times New Roman')
                    expect(page.locator('.message.assistant .message-text')).to_contain_text('ДЕМО')
                    assert requests[-1]['attachment']['name'] == 'private.docx'
                    assert page.request.get(url + '/api/materials').json() == []
                    stored = page.evaluate('localStorage.getItem("aiboturfu.chats.v1")')
                    assert 'UEsDB' not in stored and 'PRIVATE-CHECK-729' not in stored
                    page.locator('#prompt').fill('А что с отступами?')
                    page.locator('#send').click()
                    expect(page.locator('.document-review')).to_have_count(2)
                    assert requests[-1]['attachment']['name'] == 'private.docx'
                    page.locator('#new-chat').click()
                    expect(page.locator('#chat-attachment')).to_be_hidden()
                    page.locator('#prompt').fill('Новый вопрос без документа')
                    page.locator('#send').click()
                    expect(page.locator('.message.assistant')).to_have_count(1)
                    assert 'attachment' not in requests[-1]
                    page.locator('#history .history-open').nth(1).click()
                    expect(page.locator('#chat-attachment-name')).to_have_text('private.docx')
                    page.locator('#remove-attachment').click()
                    expect(page.locator('#chat-attachment')).to_be_hidden()
                    page.locator('#chat-document').set_input_files({'name': 'private.docx', 'mimeType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'buffer': content})
                    expect(page.locator('#chat-attachment')).to_be_visible()
                    page.reload()
                    page.locator('#history .history-open').nth(1).click()
                    expect(page.locator('#chat-attachment')).to_be_hidden()
                    expect(page.locator('.document-review')).to_have_count(2)
                    page.locator('[data-theme-toggle]').click()
                    page.set_viewport_size({'width': 390, 'height': 844})
                    page.locator('#chat-document').set_input_files({'name': 'private.docx', 'mimeType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'buffer': content})
                    expect(page.locator('#chat-attachment')).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.request.post(url + '/api/auth/register', data={'username': 'docx_student', 'password': 'test-password-729'})
                    page.evaluate('syncAccount()')
                    expect(page.locator('#profile-username')).to_have_text('docx_student')
                    expect(page.locator('#chat-attachment')).to_be_hidden()
                    assert not errors, errors
                    Path('artifacts').mkdir(exist_ok=True)
                    print('DOCX chat QA passed: upload, review, follow-up, private storage, chat/account isolation, reload, mobile/dark.')
                finally:
                    browser.close()
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__':
    main()
