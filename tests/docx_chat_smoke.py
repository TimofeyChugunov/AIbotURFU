"""Explicit real Qwen DOCX review using temporary data, no cloud calls."""
import base64
import json
import os
import sys
import tempfile
import threading
import urllib.request
import io
from docx import Document
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from test_docx_review import document_bytes


def main():
    with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA', Path(tmp)), patch.dict(
        os.environ, {'AI_MODE': 'ollama', 'OLLAMA_MODEL': 'qwen3:8b'}
    ):
        server.init_db()
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            content = document_bytes('Введение. Цель работы — разработать учебный чат-бот. '
                                     'Задачи пока не сформулированы. Код работы: DOCX-CHECK-729.')
            payload = {'mode': 'report', 'message': 'Кратко прокомментируй введение: цель и задачи. '
                       'В конце напомни код работы из файла. Не объявляй соответствие ГОСТ.',
                       'attachment': {'name': 'sample.docx', 'content': base64.b64encode(content).decode()}}
            request = urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}/api/chat',
                data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=195) as response:
                result = json.load(response)
            assert result['demo'] is False and result['provider'] == 'ollama'
            assert result['document_review']['name'] == 'sample.docx'
            assert 'DOCX-CHECK-729' in result['text'], result['text']
            review = result['document_review']
            assert review['ai_comments'], 'Expected an anchored content comment for the missing tasks in the test file.'
            export_payload = {'attachment': payload['attachment'], 'feedback': {
                'source_hash': review['source_hash'], 'summary': result['text'],
                'comments': review['ai_comments'], 'demo': False}}
            request = urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}/api/chat/document/export',
                data=json.dumps(export_payload).encode(), headers={'Content-Type': 'application/json'})
            with opener.open(request, timeout=30) as response:
                checked = Document(io.BytesIO(response.read()))
            assert len(checked.comments) >= 1
            assert any('Рекомендация ИИ' in comment.text for comment in checked.comments)
            assert 'DOCX-CHECK-729' in checked.paragraphs[1].text
            with server.connect() as db:
                assert db.execute('SELECT count(*) FROM materials').fetchone()[0] == 0
            print(result['text'])
            print('Anchored AI comments:', len(review['ai_comments']), '; Word comments:', len(checked.comments))
            print('Real DOCX review passed; private document was not stored in materials.')
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__':
    main()
