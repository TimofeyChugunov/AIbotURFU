import io
import unittest
import zipfile

from docx import Document
from docx.shared import Cm, Pt

import docx_review


def document_bytes(text='Тестовая работа. Цель — проверить анализ DOCX.'):
    doc = Document()
    normal = doc.styles['Normal']
    normal.font.name = 'Times New Roman'
    normal.font.size = Pt(14)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.first_line_indent = Cm(1.25)
    doc.sections[0].left_margin = Cm(3)
    doc.add_heading('Введение', level=1)
    doc.add_paragraph(text)
    doc.add_paragraph('Фрагмент с другим оформлением.').runs[0].font.size = Pt(16)
    doc.add_table(rows=1, cols=1).cell(0, 0).text = 'Табличный факт: ABC-729'
    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()


class DocxReviewTests(unittest.TestCase):
    def test_inherited_formatting_tables_and_observations(self):
        review, context = docx_review.analyze('report.docx', document_bytes(), 'Проверь введение')
        facts = '\n'.join(review['facts'])
        for value in ['Times New Roman', '14.0 пт', '16.0 пт', '1.5 строки', '1.25 см', 'слева 3.0']:
            self.assertIn(value, facts)
        self.assertIn('ABC-729', context)
        self.assertIn('Абзац 2', context)
        self.assertTrue(any('может быть намеренное' in note for note in review['notes']))
        self.assertFalse(review['partial'])

    def test_unknown_font_is_not_assumed(self):
        doc = Document(); doc.add_paragraph('Текст с тематическим шрифтом Word.')
        stream = io.BytesIO(); doc.save(stream)
        review, _ = docx_review.analyze('theme.docx', stream.getvalue(), 'Проверь')
        self.assertIn('не удалось определить', review['facts'][1])
        self.assertTrue(any('не полностью' in line for line in review['limitations']))

    def test_long_document_has_explicit_partial_scope(self):
        doc = Document()
        for i in range(50):
            doc.add_paragraph(f'Раздел {i}. ' + 'Учебный материал и описание работы. ' * 20)
        doc.add_paragraph('Уникальное заключение ZEBRA729: достигнута цель работы.')
        stream = io.BytesIO(); doc.save(stream)
        review, context = docx_review.analyze('long.docx', stream.getvalue(), 'Проверь заключение ZEBRA729')
        self.assertTrue(review['partial'])
        self.assertIn('ZEBRA729', context)
        self.assertLess(len(context), 8000)

    def test_invalid_files_are_rejected(self):
        for name, content in [('report.doc', b'test'), ('../report.docx', b'test'),
                              ('report.docx', b'not zip'), ('report.docx', b'')]:
            with self.subTest(name=name):
                with self.assertRaises(docx_review.DocumentError):
                    docx_review.analyze(name, content, 'Проверь')

    def test_empty_and_oversized_archives_are_rejected(self):
        stream = io.BytesIO(); Document().save(stream)
        with self.assertRaisesRegex(docx_review.DocumentError, 'не найден текст'):
            docx_review.analyze('empty.docx', stream.getvalue(), 'Проверь')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('word/document.xml', b'0' * (41 * 1024 * 1024))
        with self.assertRaisesRegex(docx_review.DocumentError, 'распаковки'):
            docx_review.analyze('large.docx', stream.getvalue(), 'Проверь')
