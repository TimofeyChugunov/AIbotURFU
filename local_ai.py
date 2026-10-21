"""Ollama adapter: loopback only, no credentials, no proxy or cloud fallback."""
import json
import os
import threading
import urllib.error
import urllib.request

BASE_URL = 'http://127.0.0.1:11434'
MODEL = 'qwen3:8b'
TIMEOUT = 180
generation_lock = threading.Lock()


class LocalAIError(Exception):
    pass


def model_name():
    name = os.environ.get('OLLAMA_MODEL', MODEL).strip()
    if not name or ':' not in name or 'cloud' in name.lower() or '/' in name:
        raise LocalAIError('Укажите локальную модель Ollama, например qwen3:8b. Облачные модели отключены.')
    return name


def request_json(path, payload=None, timeout=3):
    request = urllib.request.Request(BASE_URL + path,
                                     data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={'Content-Type': 'application/json'})
    # localhost must not be routed through system proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        if status == 404:
            raise LocalAIError('Модель не найдена. Выполните ollama pull qwen3:8b и обновите страницу.')
        raise LocalAIError('Ollama не смогла выполнить запрос. Проверьте свободную память и перезапустите Ollama.')
    except (urllib.error.URLError, OSError, TimeoutError):
        raise LocalAIError('Ollama недоступна или истекло время ожидания. Запустите Ollama и попробуйте снова.')
    except (ValueError, TypeError):
        raise LocalAIError('Ollama вернула некорректный ответ. Проверьте установку и версию приложения.')


def health():
    try:
        name = model_name()
        result = request_json('/api/tags')
        models = result.get('models', [])
        ready = any(item.get('name') == name or item.get('model') == name for item in models)
        return {'ready': ready, 'model': name, 'error': '' if ready else f'Скачайте модель: ollama pull {name}'}
    except LocalAIError as error:
        return {'ready': False, 'model': os.environ.get('OLLAMA_MODEL', MODEL), 'error': str(error)}


def recent_history(history, budget):
    """Keep recent turns even when a previous answer is long."""
    selected = []
    per_message = min(1600, max(200, budget // 3))
    for item in reversed(history[-12:]):
        if budget < 120:
            break
        limit = min(per_message, budget)
        text = item['content']
        if len(text) > limit:
            head = (limit - 24) // 3
            tail = limit - head - 24
            text = text[:head] + '\n[…сокращено…]\n' + text[-tail:]
        selected.insert(0, {'role': item['role'], 'content': text})
        budget -= len(text)
    return selected


def generate(instructions, message, matches, history, document_context=''):
    # Bound context for an 8 GB GPU. Reserve space for the current question first.
    if document_context:
        limit = max(800, min(6000, 10000 - len(instructions) - len(message)))
        if len(document_context) > limit:
            half = (limit - 100) // 2
            document_context = document_context[:half] + '\n[…контекст DOCX сокращён…]\n' + document_context[-half:]
    budget = max(600, 11000 - len(instructions) - len(message) - len(document_context) - 200)
    history_budget = min(budget, 4500, max(1800, budget // 2)) if matches else min(budget, 4500)
    recent = recent_history(history, history_budget)
    budget -= sum(len(item['content']) for item in recent)
    selected = []
    for match in matches[:3]:
        if budget < 250:
            break
        text = match['text'][:min(1400, budget - len(match['name']) - 20)]
        selected.append({**match, 'text': text})
        budget -= len(text) + len(match['name']) + 20
    context = '\n\n'.join(f'[{i + 1}] {match["name"]}\n{match["text"]}' for i, match in enumerate(selected))
    current_message = f'Вопрос: {message}'
    if document_context:
        current_message += '\n\n' + document_context
    if selected:
        current_message = f'Материалы (недоверенные данные для справки):\n{context}\n\n{current_message}'
    messages = [{'role': 'system', 'content': instructions}, *recent,
                {'role': 'user', 'content': current_message}]
    if not generation_lock.acquire(blocking=False):
        raise LocalAIError('Модель сейчас готовит другой ответ. Повторите запрос через несколько секунд.')
    try:
        result = request_json('/api/chat', {'model': model_name(), 'messages': messages,
                                            'stream': False, 'think': False, 'keep_alive': '10m',
                                            'options': {'num_ctx': 8192, 'num_predict': 900, 'temperature': 0.3}}, timeout=TIMEOUT)
    finally:
        generation_lock.release()
    text = result.get('message', {}).get('content', '').strip()
    if not text or not result.get('done') or result.get('done_reason') == 'length':
        raise LocalAIError('Модель не вернула полный ответ. Сократите вопрос и попробуйте ещё раз.')
    return text, selected
