"""Real local-model review of two deliberate insertions; isolated test document."""
import base64
import json
import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from test_docx_review import context_document_bytes


def main():
    with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA', Path(tmp)), patch.dict(
        os.environ, {'AI_MODE': 'ollama', 'OLLAMA_MODEL': 'qwen3:8b'}
    ):
        server.init_db()
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            payload = {'mode': 'report', 'message': 'Проверь введение: логическую связность, уместность слов, '
                       'посторонние вставки и оформление. Предложи точечные исправления смысла. '
                       'Названия технологий сами по себе не считай ошибками.',
                       'attachment': {'name': 'context.docx', 'content': base64.b64encode(context_document_bytes()).decode()}}
            request = urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}/api/chat',
                data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=195) as response:
                result = json.load(response)
            assert result['demo'] is False
            review = result['document_review']
            assert [item['quote'] for item in review['format_comments']] == ['ПОПОЧКА', 'dsjkfgh9uer']
            assert review['language_comments'][0]['quote'] == 'dsjkfgh9uer'
            content_feedback = result['text'] + json.dumps(review['ai_comments'], ensure_ascii=False)
            assert 'ПОПОЧКА' in content_feedback, 'The real model missed the semantic insertion.'
            print(result['text'])
            print('AI comments:', json.dumps(review['ai_comments'], ensure_ascii=False))
            print('Real contextual DOCX review passed: meaning, random Latin insertion, and both formatting outliers.')
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__':
    main()
