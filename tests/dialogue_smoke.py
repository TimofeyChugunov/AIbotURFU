"""Real Qwen dialogue check without uploaded files or changes to user data."""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def main():
    with tempfile.TemporaryDirectory() as temporary, patch.object(server, 'DATA', Path(temporary)), patch.dict(os.environ, {'AI_MODE': 'ollama', 'OLLAMA_MODEL': 'qwen3:8b'}):
        server.init_db()
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        history = []
        try:
            for index, message in enumerate([
                'Что такое искусственный интеллект? Объясни в двух предложениях. Мой учебный проект называется Север-729.',
                'А чем он отличается от машинного обучения? Ответь кратко и в конце напомни название моего проекта.',
            ]):
                started = time.monotonic()
                request = urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}/api/chat',
                    data=json.dumps({'message': message, 'mode': 'explain', 'history': history}).encode(),
                    headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=195) as response:
                    result = json.load(response)
                assert result['demo'] is False and result['provider'] == 'ollama'
                assert result['sources'] == []
                assert len(result['text']) > 60
                assert 'загрузите' not in result['text'].lower(), result['text']
                if index == 1:
                    assert 'Север-729' in result['text'], result['text']
                history.extend([{'role': 'user', 'content': message}, {'role': 'assistant', 'content': result['text']}])
                print(json.dumps({'turn': index + 1, 'seconds': round(time.monotonic() - started, 1), 'text': result['text']}, ensure_ascii=True), flush=True)
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__':
    main()
