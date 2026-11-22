from __future__ import annotations

import re

_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "it", "be", "this", "that", "with",
    "as", "at", "by", "from", "we", "should", "not", "are", "when", "if", "can", "no", "has", "have", "java",
    "scala", "src", "main", "org", "apache", "kafka", "code", "none", "null", "http", "https", "www", "com",
}


def tokens(text: str) -> list[str]:
    """camelCase / snake_case / path aware tokens, lowercased, stopwords dropped."""
    out = []
    for word in re.findall(r"[A-Za-z0-9]+", text or ""):
        parts = _SPLIT.findall(word) or [word]
        out.extend(p.lower() for p in parts)
        if len(parts) > 1:
            out.append(word.lower())
    return [t for t in out if len(t) > 1 and t not in STOP]
