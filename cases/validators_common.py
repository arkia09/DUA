"""Building blocks shared by every department's validator.

Prompting alone is never trusted: each office checks the model's JSON with these helpers before anything is stored.
"""
import re
import unicodedata

MAX_QUESTIONS = 3
MIN_QUOTE_WORDS = 3


class InvalidModelOutput(Exception):
    pass


def text(value, field, limit=500, required=True):
    """A stripped string no longer than `limit`. Missing/empty raises when `required`, else returns ""."""
    if not isinstance(value, str):
        if required:
            raise InvalidModelOutput(f"{field} is not a string")
        return ""
    value = value.strip()
    if required and not value:
        raise InvalidModelOutput(f"{field} is empty")
    return value[:limit]


def string_list(value, field, max_items, limit=300):
    """A list of non-empty strings (junk entries are skipped), capped in count and length."""
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        if isinstance(v, str) and v.strip():
            out.append(v.strip()[:limit])
        if len(out) == max_items:
            break
    return out


def questions(value):
    return string_list(value, "clarifying_questions", MAX_QUESTIONS, 500)


def words(s):
    """Reduce text to lowercase words separated by single spaces, so that quotes can be compared with the source
    despite differences in case, whitespace, punctuation, curly quotes or markdown emphasis."""
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"(?:[^\w$%]|_)+", " ", s).strip()


def quote_in_source(quote, source_words, min_words=MIN_QUOTE_WORDS, min_chars=0):
    """True if `quote` is a word-for-word excerpt of the source. `source_words` must come from words().

    Quotes shorter than `min_words` words (or `min_chars` characters) are rejected: a two-word 'quote' of a long
    document proves nothing. Short free-text fields, like preferences, can pass a lower bar.
    """
    if not isinstance(quote, str):
        return False
    q = words(quote)
    if len(q.split()) < min_words or len(q) < min_chars:
        return False
    return f" {q} " in f" {source_words} "


def neutralize_tag(content, tag):
    """Stop untrusted text from closing (or reopening) the tag it is wrapped in."""
    return re.sub(rf"<\s*(/?)\s*{re.escape(tag)}\b", lambda m: f"&lt;{m.group(1)}{tag}", content, flags=re.I)
