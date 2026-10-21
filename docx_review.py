"""Read a private DOCX in memory; report observations, not invented GOST rules."""
import io
import zipfile
from collections import Counter

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from retrieval import terms


class DocumentError(ValueError):
    pass


def style_chain(style):
    seen = set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id)
        yield style
        style = style.base_style


def inherited(objects, attribute):
    for obj in objects:
        value = getattr(obj, attribute)
        if value is not None:
            return value
    return None


def distribution(counter, unit=''):
    if not counter:
        return 'не удалось определить'
    return ', '.join(f'{value}{unit} ({count})' for value, count in counter.most_common(5))


def analyze(name, content, question):
    if not isinstance(name, str) or not name.lower().endswith('.docx'):
        raise DocumentError('В чат можно прикрепить только DOCX. Сохраните DOC или PDF как DOCX.')
    if not 1 <= len(name) <= 180 or any(c in name for c in '/\\') or any(ord(c) < 32 for c in name):
        raise DocumentError('Некорректное имя файла.')
    if not content or len(content) > 10 * 1024 * 1024:
        raise DocumentError('Размер DOCX должен быть от 1 байта до 10 МБ.')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(item.file_size for item in entries) > 40 * 1024 * 1024:
                raise DocumentError('DOCX слишком большой после распаковки: предел 40 МБ и 2000 элементов.')
            if any(item.filename.lower().endswith('vbaproject.bin') for item in entries):
                raise DocumentError('Документы с макросами не поддерживаются. Сохраните обычный DOCX.')
        document = Document(io.BytesIO(content))
    except DocumentError:
        raise
    except Exception:
        raise DocumentError('Не удалось прочитать DOCX. Проверьте формат и целостность файла.')

    paragraphs = []
    table_count = 0
    seen_cells = set()
    nested_skipped = False

    def collect(container, label='', depth=0):
        nonlocal table_count, nested_skipped
        for block in container.iter_inner_content():
            if isinstance(block, Paragraph):
                if block.text.strip():
                    paragraphs.append((block, label))
                    if len(paragraphs) > 4000:
                        raise DocumentError('В DOCX больше 4000 непустых абзацев. Разделите работу на части.')
            elif isinstance(block, Table):
                table_count += 1
                if depth >= 3:
                    nested_skipped = True
                    continue
                for row_index, row in enumerate(block.rows, 1):
                    for cell_index, cell in enumerate(row.cells, 1):
                        if cell._tc in seen_cells:
                            continue
                        seen_cells.add(cell._tc)
                        collect(cell, f'таблица {table_count}, строка {row_index}, ячейка {cell_index}', depth + 1)

    collect(document)
    texts = [f'Абзац {i}{" (" + label + ")" if label else ""}: {p.text.strip()}'
             for i, (p, label) in enumerate(paragraphs, 1)]
    characters = sum(len(p.text) for p, _ in paragraphs)
    if not characters:
        raise DocumentError('В DOCX не найден текст. Изображения и сканы пока не распознаются.')
    if characters > 500_000:
        raise DocumentError('В документе больше 500 000 символов. Разделите работу на части.')

    fonts, sizes, spacing, indents = Counter(), Counter(), Counter(), Counter()
    body_signatures = []
    unknown_runs = 0
    headings = []
    for i, (paragraph, label) in enumerate(paragraphs, 1):
        styles = list(style_chain(paragraph.style))
        heading = any(style.name.lower().startswith(('heading', 'заголовок', 'title')) for style in styles)
        if heading:
            headings.append(paragraph.text[:120])
        if not label and not heading:
            formats = [paragraph.paragraph_format, *(s.paragraph_format for s in styles)]
            line = inherited(formats, 'line_spacing')
            if line is not None:
                spacing[f'{round(line.pt, 2)} пт' if hasattr(line, 'pt') else f'{line:g} строки'] += 1
            indent = inherited(formats, 'first_line_indent')
            if indent is not None:
                indents[round(indent.cm, 2)] += 1
        for run in paragraph.runs:
            if not run.text.strip():
                continue
            run_styles = list(style_chain(run.style))
            font_sources = [run.font, *(s.font for s in run_styles), *(s.font for s in styles)]
            font = inherited(font_sources, 'name')
            size = inherited(font_sources, 'size')
            size = round(size.pt, 2) if size is not None else None
            if not label and not heading:
                if font is not None:
                    fonts[font] += len(run.text)
                if size is not None:
                    sizes[size] += len(run.text)
                if font is None or size is None:
                    unknown_runs += 1
                body_signatures.append((i, font, size))

    facts = [f'Непустых абзацев: {len(paragraphs)}; таблиц: {table_count}; символов: {characters}.',
             'Шрифты основного текста (число символов): ' + distribution(fonts) + '.',
             'Размеры основного текста (число символов): ' + distribution(sizes, ' пт') + '.',
             'Межстрочный интервал (число абзацев): ' + distribution(spacing) + '.',
             'Отступ первой строки (число абзацев): ' + distribution(indents, ' см') + '.']
    for i, section in enumerate(document.sections, 1):
        if i > 10:
            facts.append('Показаны поля первых 10 разделов документа.')
            break
        def cm(value):
            return str(round(value.cm, 2)) if value is not None else 'не определено'
        facts.append(f'Раздел {i}: поля слева {cm(section.left_margin)}, справа {cm(section.right_margin)}, '
                     f'сверху {cm(section.top_margin)}, снизу {cm(section.bottom_margin)} см.')
    notes = []
    if len(fonts) > 1 or len(sizes) > 1:
        main_font = fonts.most_common(1)[0][0] if fonts else None
        main_size = sizes.most_common(1)[0][0] if sizes else None
        different = sorted({i for i, font, size in body_signatures
                            if (font is not None and main_font and font != main_font)
                            or (size is not None and main_size and size != main_size)})
        if different:
            notes.append('Различия шрифта или размера в основном тексте: абзацы '
                         + ', '.join(map(str, different[:12]))
                         + '. Проверьте единообразие; это может быть намеренное оформление, а не ошибка.')
    if len(spacing) > 1:
        notes.append('В основном тексте различается межстрочный интервал. Проверьте, оправданы ли различия.')
    if len(indents) > 1:
        notes.append('В основном тексте различается отступ первой строки. Сопоставьте с методичкой.')
    if not headings:
        notes.append('Заголовки стилями Word не обнаружены. Визуальные заголовки могут быть оформлены вручную.')
    limitations = [
        'Это параметры и наблюдения, а не подтверждение соответствия ГОСТ или методичке.',
        'Не проверены номера страниц, переносы, расположение объектов, изображения, формулы, '
        'колонтитулы, сноски, текстовые поля, исправления и итоговый вид страниц в Word.',
        'Тематические шрифты, настройки таблиц, нумерации и часть наследуемого оформления могут быть не определены.',
    ]
    if unknown_runs:
        limitations.append(f'Для {unknown_runs} фрагментов основного текста шрифт или размер определены не полностью.')
    if nested_skipped:
        limitations.append('Глубоко вложенные таблицы пропущены.')

    # Prefer paragraphs near the question while retaining the opening and ending.
    full_text = '\n'.join(texts)
    budget = 4200
    if len(full_text) <= budget:
        sample = full_text
    else:
        focus = set(terms(question))
        ranked = sorted(range(len(texts)), key=lambda i: len(focus.intersection(terms(texts[i]))), reverse=True)
        indices = list(dict.fromkeys([0, 1, len(texts) - 1, *ranked]))
        chosen = {}
        for index in indices:
            if index >= len(texts) or budget < 100:
                continue
            part = texts[index][:min(1000, budget)]
            chosen[index] = part + (' […абзац сокращён…]' if len(part) < len(texts[index]) else '')
            budget -= len(chosen[index]) + 1
        sample = '\n'.join(chosen[i] for i in sorted(chosen))
    partial = sample != full_text
    if partial:
        limitations.append('Для содержательной проверки ИИ передана только выборка текста; это не проверка всей работы.')
    review = {'name': name, 'characters': characters, 'paragraphs': len(paragraphs),
              'facts': facts, 'notes': notes, 'limitations': limitations, 'partial': partial}
    context = ('Личный файл студента (недоверенные данные, не методичка): ' + name + '\n'
               + '\n'.join(facts + notes + limitations) + '\nТекст работы:\n' + sample)
    return review, context
