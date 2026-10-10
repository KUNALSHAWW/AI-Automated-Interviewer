"""Evidence verification: a score only counts if its quote really appears in the transcript or on screen."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_NON_WORD = re.compile(r"[^\w]+", re.U)


def norm(text: str) -> list[str]:
    return [t for t in _NON_WORD.sub(" ", (text or "").lower()).split() if t]


def quote_supported(quote: str, texts: list[str], min_ratio: float = 0.85, min_words: int = 3) -> bool:
    """True if `quote` is (almost) verbatim inside any of `texts`.

    Exact token-sequence containment passes; otherwise a sliding window with difflib tolerates the small
    edits speech-to-text and models introduce (a dropped filler word, a changed article).
    """
    q = norm(quote)
    if len(q) < min_words:
        return False
    for text in texts:
        t = norm(text)
        if len(t) < min_words:
            continue
        k = len(q)
        if k <= len(t):
            for i in range(len(t) - k + 1):
                if t[i:i + k] == q:
                    return True
        # fuzzy: windows of k-1..k+1 tokens
        for w in (k - 1, k, k + 1):
            if w < min_words or w > len(t):
                continue
            for i in range(len(t) - w + 1):
                if SequenceMatcher(None, q, t[i:i + w], autojunk=False).ratio() >= min_ratio:
                    return True
    return False
