"""Resolve declared DOCX fonts per script instead of using Font.name (ASCII only)."""
from lxml import etree
from docx.oxml.ns import qn


class FontResolver:
    def __init__(self, document):
        self.defaults = document.styles.element.find(
            qn('w:docDefaults') + '/' + qn('w:rPrDefault') + '/' + qn('w:rPr'))
        self.theme = None
        self.theme_cache = {}
        for relation in document.part.rels.values():
            if relation.reltype.endswith('/theme') and not relation.is_external:
                try:
                    self.theme = etree.fromstring(relation.target_part.blob,
                        etree.XMLParser(resolve_entities=False, no_network=True))
                except etree.XMLSyntaxError:
                    pass
                break

    def theme_font(self, value, script):
        key = (value, script)
        if key in self.theme_cache:
            return self.theme_cache[key]
        a = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
        family = 'majorFont' if value.startswith('major') else 'minorFont' if value.startswith('minor') else None
        result = None
        if family and self.theme is not None:
            group = self.theme.find('.//' + a + 'fontScheme/' + a + family)
            if group is not None:
                if script == 'Cyrl':
                    for font in group.findall(a + 'font'):
                        if font.get('script') == 'Cyrl' and font.get('typeface'):
                            result = font.get('typeface')
                            break
                if result is None:
                    tag = 'ea' if value.endswith('EastAsia') else 'cs' if value.endswith('Bidi') else 'latin'
                    font = group.find(a + tag)
                    if font is not None:
                        result = font.get('typeface') or None
        self.theme_cache[key] = result
        return result

    @staticmethod
    def attribute(sources, tag, attribute='val'):
        for source in sources:
            if source is None:
                continue
            element = source.find(qn('w:' + tag))
            if element is not None:
                value = element.get(qn('w:' + attribute))
                if value is not None:
                    return value
        return None

    def slot_font(self, sources, slot, script):
        theme_attribute = 'cstheme' if slot == 'cs' else slot + 'Theme'
        for source in sources:
            if source is None:
                continue
            fonts = source.find(qn('w:rFonts'))
            if fonts is None:
                continue
            theme = fonts.get(qn('w:' + theme_attribute))
            if theme is None and slot == 'cs':
                theme = fonts.get(qn('w:csTheme'))
            if theme is not None:
                # Word uses a theme reference when supplied at this level.
                # An unresolved theme must not be replaced by an unrelated ASCII font.
                return self.theme_font(theme, script)
            name = fonts.get(qn('w:' + slot))
            if name is not None:
                return name or None
        return None

    def spans(self, run, styles):
        sources = [run._r.rPr, *(style.element.rPr for style in styles), self.defaults]
        def flag_value(tag):
            for source in sources:
                flag = source.find(qn('w:' + tag)) if source is not None else None
                if flag is not None:
                    return flag.get(qn('w:val'), '1') not in ('0', 'false', 'off')
            return False
        complex_script = flag_value('cs') or flag_value('rtl')
        hint = self.attribute(sources, 'rFonts', 'hint')
        size_raw = self.attribute(sources, 'szCs' if complex_script else 'sz')
        try:
            size = float(size_raw) / 2 if size_raw is not None else None
            if size is not None and not 0 < size <= 1638:
                size = None
        except ValueError:
            size = None
        cache = {}
        result = []
        for offset, character in enumerate(run.text):
            codepoint = ord(character)
            cyrillic = 0x400 <= codepoint <= 0x52f or 0x2de0 <= codepoint <= 0x2dff or 0xa640 <= codepoint <= 0xa69f
            slot = ('cs' if complex_script else 'ascii' if codepoint < 128 else
                    'eastAsia' if cyrillic and hint == 'eastAsia' else
                    'hAnsi' if cyrillic or 0xa0 <= codepoint <= 0x3ff or 0x1e00 <= codepoint <= 0x1eff else None)
            key = (slot, 'Cyrl' if cyrillic else 'Latn')
            if key not in cache:
                font = self.slot_font(sources, slot, key[1]) if slot else None
                if slot == 'eastAsia' and font == 'Times New Roman':
                    ascii_font = self.slot_font(sources, 'ascii', 'Latn')
                    ansi_font = self.slot_font(sources, 'hAnsi', 'Cyrl')
                    if ascii_font and ascii_font == ansi_font:
                        font = ascii_font
                cache[key] = font
            font = cache[key]
            if result and result[-1][1:3] == (font, size):
                result[-1][0].append(character)
            else:
                result.append(([character], font, size, offset))
        return [(''.join(text), font, size, offset) for text, font, size, offset in result]
