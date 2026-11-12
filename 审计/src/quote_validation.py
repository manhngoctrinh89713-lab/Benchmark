"""Default source-grounded citation matching; no model calls or score changes."""
import json
import re
import unicodedata

POLICY = 'source-grounded-format-v3'
_PUNCT = str.maketrans({'“':'"', '”':'"', '‘':"'", '’':"'", '。':'.', '、':',', '；':';', '：':':'})


def strings(value, serialized=True):
    if isinstance(value, str):
        yield value
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError, RecursionError):
            return
        if parsed != value:
            yield from strings(parsed, serialized)
    elif isinstance(value, (dict, list)):
        if serialized:
            yield json.dumps(value, ensure_ascii=False)
        for item in (value.values() if isinstance(value, dict) else value):
            yield from strings(item, serialized)


def normalized(value):
    value = re.sub(r'\*\*(.+?)\*\*', r'\1', value, flags=re.S)
    value = re.sub(r'`([^`]+)`', r'\1', value)
    return ''.join(unicodedata.normalize('NFKC', value).translate(_PUNCT).split())


def bounded(source, start, end, quote):
    # Do not accept a changed number merely because it is a substring.
    if quote[0].isdigit() and start and (source[start-1].isdigit() or source[start-1] == '.'):
        return False
    if quote[-1].isdigit() and end < len(source) and (source[end].isdigit() or source[end] == '.'):
        return False
    if start and source[start-1] in '不未无非' and quote.startswith(('允许','可以','需要','应该','得','有')):
        return False
    return True


def match_quote(quote, value):
    """Return match metadata or None. Keep the caller's original quote intact.

    Compatibility covers whitespace, typographic punctuation, JSON escaping and
    explicit ellipses within ONE source string. Words/numbers are never fuzzy.
    """
    if not isinstance(quote, str) or not quote.strip():
        return None
    candidates = list(strings(value))
    for mode in ('exact', 'normalized'):
        q = quote if mode == 'exact' else normalized(quote)
        for original in candidates:
            source = original if mode == 'exact' else normalized(original)
            start = source.find(q)
            while start >= 0:
                if bounded(source, start, start+len(q), q):
                    return dict(mode=mode, policy=POLICY)
                start = source.find(q, start+1)
    parts = [normalized(p) for p in re.split(r'\.{3,}|…+', quote) if p.strip()]
    if len(parts) < 2 or any(len(p) < 8 for p in parts):
        return None
    for original in strings(value, serialized=False):
        source = normalized(original)
        pattern = '[\\s\\S]*?'.join(re.escape(p) for p in parts)
        for found in re.finditer(pattern, source):
            if bounded(source, found.start(), found.end(), parts[0]) and bounded(source, found.start(), found.end(), parts[-1]):
                return dict(mode='ellipsis', policy=POLICY)
    return None


def match_evidence_quote(quote, primary, eligible_values):
    """Permit joins across the caller's eligible message pool, in order."""
    found = match_quote(quote, primary)
    if found:
        return found
    joined = '\n'.join(text for value in eligible_values for text in strings(value, serialized=False))
    found = match_quote(quote, joined)
    if found:
        return dict(found, mode='cross_message_' + found['mode'])
    return None
