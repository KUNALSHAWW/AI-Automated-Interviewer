"""Turn-taking rules. Pure functions, no I/O, fully unit-tested.

Lessons applied from the NYU Stern oral-exam field report (arXiv 2603.18221): short pauses are
thinking time, not an end of turn; and stacked questions must be caught by a programmatic validator,
not by the prompt alone (their validator cut multi-question turns from 31% to ~11%).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .settings import Settings

# Word-boundary anchored so "we can integrate" or "scan input" can never look like "can I".
INVITE_RE = re.compile(
    r"\b(any questions?|questions\?|that(?:'s| is) (?:it|all)|that concludes|that's my|thank you(?: all)?|"
    r"should i (?:move|continue|go|proceed)|shall i (?:move|continue|go|proceed)|may i (?:move|continue|proceed)|"
    r"next slide|moving on|over to you|what do you think|does that make sense|is that clear|"
    r"let me know if|happy to take)\b", re.I)


def is_invitation(text: str) -> bool:
    return bool(INVITE_RE.search(text))


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, re.U))


@dataclass
class TurnInputs:
    now: float
    last_speech_at: float          # end time of the last presenter utterance
    last_ai_at: float              # when the AI last finished speaking (0 = never)
    words_since_ai: int
    invited: bool
    screen_changed_since_ai: bool
    ai_busy: bool                  # evaluating or synthesising
    ai_speaking: bool
    transcribing: int = 0          # utterances still in the STT queue


@dataclass
class Decision:
    ask: bool
    reason: str


def decide(i: TurnInputs, cfg: Settings) -> Decision:
    if i.ai_busy or i.ai_speaking:
        return Decision(False, "ai_busy")
    if i.transcribing:
        return Decision(False, "transcribing")
    if i.words_since_ai == 0 and not i.screen_changed_since_ai:
        return Decision(False, "nothing_new")
    silence = i.now - i.last_speech_at
    if i.invited and silence >= 0.8:
        return Decision(True, "invited")
    if silence < cfg.pause_s:
        return Decision(False, "still_talking")
    if i.last_ai_at and i.now - i.last_ai_at < cfg.min_ai_gap_s:
        return Decision(False, "min_gap")
    if i.words_since_ai >= cfg.max_words_without_ai:
        return Decision(True, "long_monologue")
    if i.screen_changed_since_ai and i.words_since_ai >= 10:
        return Decision(True, "new_slide")
    if i.words_since_ai >= cfg.min_words_to_ask:
        return Decision(True, "natural_pause")
    return Decision(False, "too_short")


# ------------------------------------------------------------------ question validator
_LEAD_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_SENT_RE = re.compile(r"[^.?!]+[.?!]?")


def sanitize_question(text: str, max_words: int = 30) -> tuple[str, list[str]]:
    """Return (clean_question, fixes). One question, plain text, no list markers, bounded length."""
    fixes: list[str] = []
    t = re.sub(r"[*_`#>]+", "", text or "").strip()
    t = _LEAD_RE.sub("", t)
    if "\n" in t:
        t = " ".join(line.strip() for line in t.splitlines() if line.strip())
    sents = [s.strip() for s in _SENT_RE.findall(t) if s.strip()]
    qs = [s for s in sents if s.endswith("?")]
    if len(qs) > 1:
        # keep the first question; an optional short acknowledgement before it survives
        first = qs[0]
        lead = [s for s in sents[:sents.index(first)] if not s.endswith("?")]
        t = (lead[-1] + " " if lead and word_count(lead[-1]) <= 14 else "") + first
        fixes.append("stacked_questions_trimmed")
    elif qs:
        first = qs[0]
        lead = [s for s in sents[:sents.index(first)]]
        if len(lead) >= 2:
            t = " ".join(lead[-1:] + [first])
            fixes.append("lead_in_trimmed")
    words = t.split()
    if len(words) > max_words and qs:
        t = qs[0]
        fixes.append("long_question_reduced")
    if len(t.split()) > max_words * 2:
        t = " ".join(t.split()[:max_words * 2])
        fixes.append("hard_truncated")
    return t.strip(), fixes
