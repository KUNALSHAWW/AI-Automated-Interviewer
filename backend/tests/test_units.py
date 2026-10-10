"""Pure-logic tests: pacing, question validation, evidence verification, lexicon, change detection, rubrics."""
from __future__ import annotations

import pytest

from app.evidence import quote_supported
from app.pacing import TurnInputs, decide, is_invitation, sanitize_question
from app.rubrics import custom_rubric, resolve
from app.techlex import check_claims, find_techs
from app.vision import ChangeDetector
from tests.conftest import make_settings, slide_jpeg


# ----------------------------------------------------------------------------- pacing
@pytest.mark.parametrize("text,expected", [
    ("Any questions so far?", True),
    ("so that's all from my side, thank you", True),
    ("should I move on to the next module", True),
    ("we can integrate the payment gateway", False),   # old substring bug: matched "can i"
    ("it will scan input from the camera", False),
    ("the pipeline can improve throughput", False),
])
def test_invitation_uses_word_boundaries(text, expected):
    assert is_invitation(text) is expected


def _inp(**kw):
    base = dict(now=100.0, last_speech_at=90.0, last_ai_at=0.0, words_since_ai=60, invited=False,
                screen_changed_since_ai=False, ai_busy=False, ai_speaking=False, transcribing=0)
    base.update(kw)
    return TurnInputs(**base)


def test_decide_waits_while_presenter_is_still_talking(tmp_path):
    cfg = make_settings(tmp_path, pause_s=2.5)
    assert not decide(_inp(last_speech_at=99.0), cfg).ask          # 1 s of silence is thinking time
    assert decide(_inp(last_speech_at=96.0), cfg).ask              # 4 s of silence


def test_decide_never_interrupts_ai_or_pending_transcription(tmp_path):
    cfg = make_settings(tmp_path)
    assert decide(_inp(ai_speaking=True), cfg).reason == "ai_busy"
    assert decide(_inp(ai_busy=True), cfg).reason == "ai_busy"
    assert decide(_inp(transcribing=1), cfg).reason == "transcribing"


def test_decide_respects_min_gap_but_not_invitation(tmp_path):
    cfg = make_settings(tmp_path, min_ai_gap_s=20.0)
    assert decide(_inp(last_ai_at=95.0), cfg).reason == "min_gap"
    assert decide(_inp(last_ai_at=95.0, invited=True, last_speech_at=98.0), cfg).reason == "invited"


def test_decide_needs_enough_words(tmp_path):
    cfg = make_settings(tmp_path, min_words_to_ask=35)
    assert decide(_inp(words_since_ai=12), cfg).reason == "too_short"
    assert decide(_inp(words_since_ai=12, screen_changed_since_ai=True), cfg).reason == "new_slide"


# ---------------------------------------------------------------- question validator
def test_sanitize_keeps_a_single_question():
    q, fixes = sanitize_question("Nice work. Why did you choose Redis? And how would you test it?")
    assert q.count("?") == 1 and "stacked_questions_trimmed" in fixes
    assert q.endswith("Why did you choose Redis?") or q.endswith("Nice work. Why did you choose Redis?")


def test_sanitize_strips_markup_and_list_markers():
    q, _ = sanitize_question("1. **What happens** when the cache is empty?")
    assert q == "What happens when the cache is empty?"


def test_sanitize_passes_clean_question_unchanged():
    q, fixes = sanitize_question("How does the login endpoint handle expired tokens?")
    assert q == "How does the login endpoint handle expired tokens?" and fixes == []


# ------------------------------------------------------------------- evidence
def test_quote_must_appear_in_the_transcript():
    seg = "We cache session tokens in Redis so the login endpoint stays fast under load"
    assert quote_supported("cache session tokens in Redis", [seg])
    assert quote_supported("we cache session tokens in redis so", [seg])           # case/punctuation
    assert quote_supported("cache the session tokens in Redis", [seg])             # small STT-style edit
    assert not quote_supported("I wrote every kernel module myself", [seg])         # fabricated
    assert not quote_supported("Redis", [seg])                                      # too short to be evidence


# --------------------------------------------------------------------- lexicon
def test_lexicon_ignores_ordinary_english():
    assert find_techs("users react quickly and we express thanks, then render the page") == set()
    assert {"React", "FastAPI"} <= find_techs("Frontend in React, backend in FastAPI")


def test_claim_check_flags_unfound_tech_and_unsupported_metric():
    out = check_claims("We used Redis and Kafka and got 95% accuracy", "FastAPI Docker 90% accuracy", {"FastAPI", "Docker"})
    assert out["not_found"] == ["Kafka", "Redis"]
    assert out["unverified_metrics"] == ["95%"]
    assert out["supported"] == []


def test_slide_that_shows_a_tool_the_repo_lacks_is_still_not_found():
    out = check_claims("We use Redis", "FastAPI", {"FastAPI"}, screen_text="Diagram: API -> Redis cache -> Kafka")
    assert out["supported"] == [] and out["not_found"] == ["Kafka", "Redis"]


def test_metric_shown_on_screen_counts_as_supported():
    out = check_claims("it is 99.9% available", "no numbers here", set(), screen_text="Uptime 99.9%")
    assert out["unverified_metrics"] == []


# ------------------------------------------------------------ change detection
def test_detector_fires_on_ordinary_slide_change_that_the_old_threshold_missed():
    det = ChangeDetector()
    a = slide_jpeg(["Architecture Overview", "- FastAPI backend", "- React frontend", "- Groq LLM"])
    b = slide_jpeg(["Database Design", "- Postgres, 4 tables", "- Indexed on user_id", "- Nightly backups"])
    assert det.feed(a) is True                     # first frame: nothing analysed yet, nothing moving
    det.commit()
    assert det.feed(a) is False                    # identical frame: nothing new
    assert det.feed(b) is False                    # still "moving" relative to the previous frame
    assert det.feed(b) is True                     # settled and different: analyse


def test_detector_ignores_cursor_movement():
    det = ChangeDetector()
    base = ["def evaluate(x):", "    return model(x)", "class Brain: ..."]
    assert det.feed(slide_jpeg(base, dark=True, cursor=(100, 600)))
    det.commit()
    assert not det.feed(slide_jpeg(base, dark=True, cursor=(900, 300)))
    assert not det.feed(slide_jpeg(base, dark=True, cursor=(400, 650)))


def test_detector_keeps_change_pending_until_committed():
    det = ChangeDetector()
    a, b = slide_jpeg(["Slide one", "alpha"]), slide_jpeg(["Slide two", "beta", "gamma"])
    assert det.feed(a)
    det.commit()
    det.feed(b)
    assert det.feed(b)          # change is offered...
    assert det.feed(b)          # ...and offered again because it was never committed (rate-limited case)
    det.commit()
    assert not det.feed(b)


# --------------------------------------------------------------------- rubrics
def test_custom_rubric_is_validated_and_normalised():
    r = custom_rubric({"title": "Demo day", "dimensions": [{"id": "impact", "weight": 3}, {"id": "ux", "weight": 1}]})
    assert [round(d.weight, 2) for d in r.dimensions] == [0.75, 0.25]
    with pytest.raises(ValueError):
        custom_rubric({"dimensions": [{"id": "only_one"}]})
    with pytest.raises(ValueError):
        custom_rubric({"dimensions": [{"id": "Bad Id!"}, {"id": "ok"}]})


def test_unknown_rubric_id_falls_back_to_project_viva():
    assert resolve("nope", None).id == "project_viva"


def test_documented_only_is_separate_from_not_found():
    out = check_claims("We use Celery and Kafka", "README", {"FastAPI"}, documented={"Celery"})
    assert out["documented_only"] == ["Celery"] and out["not_found"] == ["Kafka"]
    assert out["supported"] == []


def test_transcript_normalisation_restores_product_names():
    from app.techlex import normalize_transcript
    raw = "The FAST API backend, hosted on GIT Hub, uses Post gres SQL and web sockets with Mongo DB."
    out = normalize_transcript(raw)
    assert "FastAPI" in out and "GitHub" in out and "PostgreSQL" in out and "MongoDB" in out
    assert normalize_transcript("fast and slow api calls") == "fast and slow api calls"   # no false merges
