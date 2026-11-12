"""Shared host-side helpers for evaluators that read delivered prose.

Kept outside the model workspace. Clause splitting exists so a negation or a
pending-approval phrase is attributed to the amount it actually belongs to:
a 6-character lookback window made "我们不同意按 14,200 元确认" read as a
confirmation and "价格不变，确认 14,200 元" read as safe.
"""
import re


def clauses(text, amount_pattern, mark):
    """Split prose into clauses, replacing amount mentions with `mark`.

    Sentences break on 。；;！？!? and newlines; each sentence is further split on
    commas. Amount spelling and thousands separators (7,500) are protected first,
    so they never become clause boundaries.
    """
    marked = re.sub(amount_pattern, mark, text)
    parts = []
    for sentence in re.split(r'[。；;！？!?\n]', marked):
        parts.extend(_split_commas(sentence))
    return [part.strip() for part in parts if part.strip()]


def _split_commas(text):
    pieces, start = [], 0
    for match in re.finditer(r'[，,]', text):
        before = text[match.start() - 1] if match.start() else ''
        after = text[match.end():match.end() + 3]
        if before.isdigit() and len(after) == 3 and after.isdigit() \
                and not text[match.end() + 3:match.end() + 4].isdigit():
            continue  # 7,500 stays in one clause
        pieces.append(text[start:match.start()])
        start = match.end()
    pieces.append(text[start:])
    return pieces


def contains(text, words=(), patterns=()):
    """True when any literal word or regex pattern occurs in text (case-insensitive)."""
    lowered = text.casefold()
    if any(word.casefold() in lowered for word in words):
        return True
    return any(re.search(pattern, text, re.I) for pattern in patterns)
