import unittest
from unittest.mock import patch
import local_ai


class LocalAITests(unittest.TestCase):
    def test_private_docx_context_is_bounded_and_only_in_user_message(self):
        with patch('local_ai.request_json', return_value={'done': True, 'message': {'content': 'Ответ'}}) as endpoint:
            local_ai.generate('System instructions', 'Review this file', [], [], 'PRIVATE-DOCX-729 ' * 1500)
        messages = endpoint.call_args.args[1]['messages']
        self.assertNotIn('PRIVATE-DOCX-729', messages[0]['content'])
        self.assertIn('PRIVATE-DOCX-729', messages[-1]['content'])
        self.assertLess(len(messages[-1]['content']), 6200)

    def test_installed_model_health(self):
        with patch('local_ai.request_json', return_value={'models': [{'name': 'qwen3:8b'}]}):
            self.assertTrue(local_ai.health()['ready'])
        with patch('local_ai.request_json', return_value={'models': []}):
            self.assertFalse(local_ai.health()['ready'])
        with patch('local_ai.request_json', side_effect=local_ai.LocalAIError('offline')):
            self.assertFalse(local_ai.health()['ready'])

    def test_local_payload_has_no_key_and_uses_selected_context(self):
        matches = [{'id': '1', 'name': 'Методичка.txt', 'text': 'Во введении укажите цель и задачи.'}]
        with patch('local_ai.request_json', return_value={'done': True, 'done_reason': 'stop', 'message': {'content': 'Сформулируйте цель [1].'}}) as endpoint:
            text, selected = local_ai.generate('Отвечай кратко.', 'Как написать введение?', matches, [])
        path, payload = endpoint.call_args.args
        self.assertEqual(path, '/api/chat')
        self.assertEqual(payload['model'], 'qwen3:8b')
        self.assertFalse(payload['think'])
        self.assertFalse(payload['stream'])
        self.assertIn('[1] Методичка.txt', payload['messages'][-1]['content'])
        self.assertEqual(selected, matches)
        self.assertIn('[1]', text)

    def test_context_is_bounded(self):
        matches = [{'id': str(i), 'name': 'test.txt', 'text': 'текст ' * 1000} for i in range(5)]
        history = [{'role': 'user', 'content': 'история ' * 1000} for _ in range(12)]
        with patch('local_ai.request_json', return_value={'done': True, 'message': {'content': 'Ответ'}}) as endpoint:
            _, selected = local_ai.generate('Инструкция ' * 150, 'Вопрос ' * 800, matches, history)
        messages = endpoint.call_args.args[1]['messages']
        self.assertLess(sum(len(m['content']) for m in messages), 11500)
        self.assertLessEqual(len(selected), 3)

    def test_busy_and_incomplete_do_not_become_demo(self):
        local_ai.generation_lock.acquire()
        try:
            with self.assertRaises(local_ai.LocalAIError):
                local_ai.generate('test', 'test', [], [])
        finally:
            local_ai.generation_lock.release()
        for response in ({'done': True, 'message': {'content': ''}}, {'done': True, 'done_reason': 'length', 'message': {'content': 'partial'}}):
            with patch('local_ai.request_json', return_value=response):
                with self.assertRaises(local_ai.LocalAIError):
                    local_ai.generate('test', 'test', [], [])
        self.assertFalse(local_ai.generation_lock.locked())

    def test_cloud_model_rejected(self):
        import os
        with patch.dict(os.environ, {'OLLAMA_MODEL': 'qwen3:cloud'}):
            with self.assertRaises(local_ai.LocalAIError):
                local_ai.model_name()

    def test_long_answer_does_not_discard_conversation(self):
        history = [{'role': 'user', 'content': 'Мой проект называется Север-729. Что такое ИИ?'},
                   {'role': 'assistant', 'content': 'Определение ИИ. ' + 'Длинное пояснение. ' * 250}]
        with patch('local_ai.request_json', return_value={'done': True, 'message': {'content': 'Сравнение'}}) as endpoint:
            local_ai.generate('Ответь кратко.', 'А чем он отличается от машинного обучения?', [], history)
        messages = endpoint.call_args.args[1]['messages']
        self.assertEqual(messages[1]['role'], 'user')
        self.assertIn('Север-729', messages[1]['content'])
        self.assertEqual(messages[2]['role'], 'assistant')
        self.assertIn('сокращено', messages[2]['content'])
        self.assertLess(len(messages[2]['content']), 2000)
        self.assertNotIn('Не найдены', messages[-1]['content'])

    def test_history_has_reserved_space_with_documents(self):
        history = [{'role': 'user', 'content': 'Мы обсуждаем проект Север-729.'},
                   {'role': 'assistant', 'content': 'Предыдущий ответ. ' * 200}]
        matches = [{'id': str(i), 'name': 'test.txt', 'text': 'Материал. ' * 400} for i in range(5)]
        with patch('local_ai.request_json', return_value={'done': True, 'message': {'content': 'Ответ'}}) as endpoint:
            _, selected = local_ai.generate('Инструкция. ' * 100, 'Объясни это проще', matches, history)
        messages = endpoint.call_args.args[1]['messages']
        self.assertIn('Север-729', messages[1]['content'])
        self.assertTrue(selected)
        self.assertIn('[1]', messages[-1]['content'])

    def test_long_answer_does_not_discard_conversation(self):
        history = [{'role': 'user', 'content': 'Мой проект называется Север-729. Что такое ИИ?'},
                   {'role': 'assistant', 'content': 'Определение ИИ. ' + 'Длинное пояснение. ' * 250}]
        with patch('local_ai.request_json', return_value={'done': True, 'message': {'content': 'Сравнение'}}) as endpoint:
            local_ai.generate('Ответь кратко.', 'А чем он отличается от машинного обучения?', [], history)
        messages = endpoint.call_args.args[1]['messages']
        self.assertEqual(messages[1]['role'], 'user')
        self.assertIn('Север-729', messages[1]['content'])
        self.assertEqual(messages[2]['role'], 'assistant')
        self.assertIn('сокращено', messages[2]['content'])
        self.assertLess(len(messages[2]['content']), 2000)
        self.assertNotIn('Не найдены', messages[-1]['content'])

    def test_history_has_reserved_space_with_documents(self):
        history = [{'role': 'user', 'content': 'Мы обсуждаем проект Север-729.'},
                   {'role': 'assistant', 'content': 'Предыдущий ответ. ' * 200}]
        matches = [{'id': str(i), 'name': 'test.txt', 'text': 'Материал. ' * 400} for i in range(5)]
        with patch('local_ai.request_json', return_value={'done': True, 'message': {'content': 'Ответ'}}) as endpoint:
            _, selected = local_ai.generate('Инструкция. ' * 100, 'Объясни это проще', matches, history)
        messages = endpoint.call_args.args[1]['messages']
        self.assertIn('Север-729', messages[1]['content'])
        self.assertTrue(selected)
        self.assertIn('[1]', messages[-1]['content'])


if __name__ == '__main__':
    unittest.main()
