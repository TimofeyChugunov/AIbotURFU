"""Small local lexical retriever. No model, API, or external index required."""
import math
import re
from collections import Counter

STOPWORDS = set('а без бы был была были быть в вам вас ваш ваши во вот все всего где да для до его ее если есть еще же за здесь и из или им их к как какой какие ко когда который кто ли либо мне можно мой мы на над надо наш не него нее нет но ну о об один он она они оно от по под пожалуйста при про с сам себе со так также такой там те тем то того тоже только том ты у уже что чтобы это этой этот я напиши расскажи объясни помоги составить сделать дай пару совет советов проще просто нужно'.split())


def terms(text):
    result = []
    for word in re.findall(r'[a-zа-яё]+|\d+(?:[.\-]\d+)*', text.lower().replace('ё', 'е')):
        if word in STOPWORDS or (len(word) < 3 and not word.isdigit()):
            continue
        # Domain terms have stable stems despite common Russian inflections.
        canonical = next((stem for stem in ('введен', 'заключен', 'оформлен', 'требован', 'презентац', 'актуальн', 'источник', 'гост') if word.startswith(stem)), None)
        if canonical:
            result.append(canonical)
        elif re.fullmatch('[а-я]+', word) and len(word) > 5:
            result.append(re.sub(r'(иями|ами|ями|ого|его|ому|ему|ыми|ими|ах|ях|ов|ев|ая|яя|ое|ее|ые|ие|ый|ий|ой|ую|юю|ам|ям|ом|ем|а|я|ы|и|у|ю|е|о)$', '', word))
        else:
            result.append(word)
    return result


def dialogue_query(message, history):
    previous = next((item['content'] for item in reversed(history) if item['role'] == 'user'), '')
    references_previous = re.search(r'\b(это|этого|этому|этим|его|ее|её|он|она|они|об этом|поподробнее)\b', message.lower())
    short_followup = len(terms(message)) <= 1 or re.match(r'^\s*(?:а\s+)?(?:объясни проще|приведи пример|покажи пример|продолжи|уточни)', message.lower())
    return previous + ' ' + message if previous and (references_previous or short_followup) else message


def chunks(text):
    start = 0
    while start < len(text):
        end = min(start + 1400, len(text))
        if end < len(text):
            boundary = max(text.rfind('\n', start + 700, end), text.rfind('. ', start + 700, end))
            if boundary >= 0:
                end = boundary + 1
            else:
                space = text.rfind(' ', start + 700, end)
                if space >= 0:
                    end = space
        yield start, text[start:end].strip()
        if end == len(text):
            break
        next_start = max(start + 1, end - 200)
        space = text.find(' ', next_start, end)
        start = space + 1 if space >= 0 else end


def retrieve(query, documents, limit=5):
    query_terms = set(terms(query))
    if not query_terms:
        return []
    candidates = []
    frequencies = Counter()
    for doc in documents:
        for offset, text in chunks(doc['text']):
            counts = Counter(terms(text))
            frequencies.update(counts.keys())
            candidates.append((doc, offset, text, counts))
    # A document mentioning only GOST does not answer a question about introduction.
    focus = query_terms - {'гост', 'документ', 'требован', 'оформлен'}
    ranked = []
    total = len(candidates)
    for doc, offset, text, counts in candidates:
        common = query_terms & counts.keys()
        if not common or (focus and not focus.intersection(counts)):
            continue
        score = sum((1 + math.log((total + 1) / (frequencies[word] + 1))) * min(counts[word], 3) for word in common)
        score *= 1 + 2 * len(common) / len(query_terms)
        score /= 1 + len(text) / 2800
        score += .5 * len(query_terms.intersection(terms(doc['name'])))
        ranked.append((score, {'id': doc['id'], 'name': doc['name'], 'text': text, 'offset': offset}))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for _, item in ranked:
        if any(previous['id'] == item['id'] and abs(previous['offset'] - item['offset']) < 700 for previous in selected):
            continue
        selected.append(item)
        if len(selected) == limit:
            break
    return selected


def excerpt(text, query, max_length=550):
    """Return a verbatim excerpt near a matching term, rather than the file's start."""
    if len(text) <= max_length:
        return text
    query_terms = set(terms(query))
    focus = query_terms - {'гост', 'документ', 'требован', 'оформлен'} or query_terms
    positions = [match.start() for match in re.finditer(r'\w+', text) if focus.intersection(terms(match.group()))]
    position = positions[0] if positions else 0
    start = max(0, position - 100)
    if start:
        boundary = text.find(' ', start, position)
        start = boundary + 1 if boundary >= 0 else start
    end = min(len(text), start + max_length)
    if end < len(text):
        boundary = text.rfind(' ', start, end)
        if boundary > start:
            end = boundary
    return ('…' if start else '') + text[start:end] + ('…' if end < len(text) else '')
