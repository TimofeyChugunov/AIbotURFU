"""Explicit integration check against the real local qwen3:8b model; no cloud calls."""
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
        ident = 'a' * 24
        text = ('Учебная тестовая методичка для проекта Альфа. Это не ГОСТ. '
                'Во введении проекта Альфа укажите цель, две задачи и актуальность. '
                'Код согласования для введения: URFU-CHECK-729.')
        with server.connect() as db:
            db.execute('INSERT INTO materials (id,name,size,text,original) VALUES (?,?,?,?,?)',
                       (ident, 'Тестовая методичка.txt', len(text.encode()), text, text.encode()))
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        try:
            started = time.monotonic()
            request = urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}/api/chat',
                data=json.dumps({'message': 'Что указать во введении проекта Альфа? Дай два коротких совета по методичке, укажи код согласования и источник.', 'mode': 'report', 'history': []}).encode(),
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=195) as response:
                result = json.load(response)
            assert result['demo'] is False
            assert result['provider'] == 'ollama'
            assert result['sources'] and result['sources'][0]['id'] == ident
            assert 'URFU-CHECK-729' in result['text'], result['text']
            assert '[1]' in result['text'], result['text']
            print(json.dumps({'seconds': round(time.monotonic() - started, 1), 'text': result['text'], 'provider': result['provider']}, ensure_ascii=True), flush=True)
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__':
    main()
