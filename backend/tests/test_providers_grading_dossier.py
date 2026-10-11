"""Provider fallback, grading honesty, and repository dossier tests (all against a fake network)."""
from __future__ import annotations

import json

import httpx
import pytest

from app.dossier import DossierError, build_dossier, parse_repo_url, strip_comments
from app.grading import band_for, finalize
from app.providers.common import AllProvidersFailed
from app.providers.llm import LLMClient
from app.providers.stt import STTClient, looks_like_hallucination
from app.rubrics import PROJECT_VIVA
from tests.conftest import make_settings, wav_bytes

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ------------------------------------------------------------------ LLM fallback
async def test_chain_falls_back_after_rate_limit_and_trips_breaker(tmp_path, net, http):
    cfg = make_settings(tmp_path)
    net.chat_fail_hosts = {"api.groq.com"}
    llm = LLMClient(cfg, http)
    chain = [("groq", "openai/gpt-oss-20b"), ("ollama", "gemma4:31b")]
    res = await llm.chat(chain, [{"role": "user", "content": "hi"}], purpose="t", json_mode=True)
    assert res.provider == "ollama"
    assert llm.breaker.is_open(("groq", "openai/gpt-oss-20b"))        # 429 opens the circuit
    before = len(net.calls)
    await llm.chat(chain, [{"role": "user", "content": "hi"}], purpose="t", json_mode=True)
    assert [h for h, _ in net.calls[before:]] == ["ollama.com"]        # groq is skipped, not retried


async def test_all_providers_failing_raises_instead_of_inventing_an_answer(tmp_path, net, http):
    cfg = make_settings(tmp_path, groq_api_key="", ollama_api_key="", openrouter_api_key="")
    llm = LLMClient(cfg, http)
    with pytest.raises(AllProvidersFailed) as e:
        await llm.chat(cfg.live_chain, [{"role": "user", "content": "x"}], purpose="turn evaluation")
    assert {x.kind for x in e.value.errors} == {"no_key"}
    assert "turn evaluation" in str(e.value)


async def test_json_mode_rejection_is_retried_without_it(tmp_path):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"ok\": true}"}}]})

    llm = LLMClient(make_settings(tmp_path), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    res = await llm.chat([("ollama", "m")], [{"role": "user", "content": "x"}], purpose="t", json_mode=True)
    assert res.text == '{"ok": true}' and seen == [True, False]
    await llm.chat([("ollama", "m")], [{"role": "user", "content": "x"}], purpose="t", json_mode=True)
    assert seen[-1] is False                                           # remembered: not retried with JSON mode


async def test_retired_model_is_reported_as_model_error(tmp_path):
    def handler(req):
        return httpx.Response(404, json={"error": "model not found"})

    llm = LLMClient(make_settings(tmp_path), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(AllProvidersFailed) as e:
        await llm.chat([("groq", "llama-3.1-8b-instant")], [{"role": "user", "content": "x"}], purpose="t")
    assert e.value.errors[0].kind == "model"


# -------------------------------------------------------------------------- STT
async def test_stt_groq_success_and_openrouter_fallback(tmp_path, net, http):
    chain = [("groq", "whisper-large-v3-turbo"), ("groq", "whisper-large-v3"),
             ("openrouter", "openai/whisper-large-v3-turbo")]
    cfg = make_settings(tmp_path, stt_chain=chain)
    stt = STTClient(cfg, http)
    r = await stt.transcribe(wav_bytes(2.0), language="en", prompt="Terms: FastAPI")
    assert r.provider == "groq" and r.model == "whisper-large-v3-turbo"
    assert "FastAPI" in r.text and round(r.seconds, 1) == 2.0

    cfg2 = make_settings(tmp_path, groq_api_key="", stt_chain=chain)
    r2 = await STTClient(cfg2, http).transcribe(wav_bytes(2.0))
    assert r2.provider == "openrouter"


async def test_default_stt_chain_has_a_second_free_groq_model(tmp_path):
    cfg = make_settings(tmp_path)
    assert [m for _, m in cfg.stt_chain] == ["whisper-large-v3-turbo", "whisper-large-v3"]
    assert all(p == "groq" for p, _ in cfg.stt_chain)    # no paid-only provider in the default path


async def test_default_live_chain_avoids_reasoning_by_default_models(tmp_path):
    cfg = make_settings(tmp_path)
    models = [m for _, m in cfg.live_chain]
    assert models[0] == "qwen/qwen3.8-27b" and not any("gpt-oss" in m for m in models)


def test_whisper_silence_hallucinations_are_dropped():
    assert looks_like_hallucination("Thank you.", 1.2, None, None)
    assert looks_like_hallucination("some words here", 4.0, 0.9, -1.5)
    assert not looks_like_hallucination("We use Redis for caching", 4.0, 0.02, -0.2)


# ----------------------------------------------------------------------- grading
OBS = [
    {"id": "o1", "dimension": "technical_depth", "score": 3, "quote": "we cache session tokens in redis", "t": 12.0, "source": "speech"},
    {"id": "o2", "dimension": "technical_depth", "score": 1, "quote": "it just works somehow", "t": 40.0, "source": "speech"},
]


def _grade(dim_scores: dict, strengths=None):
    from app.grading import CouncilGrade
    return CouncilGrade.model_validate({
        "dimensions": {d: {"score": s, "rationale": "r", "evidence": ["o1"]} for d, s in dim_scores.items()},
        "strengths": strengths or [{"text": "Concrete caching explanation", "evidence": ["o1"]}],
        "growth": [{"text": "Unsupported point", "evidence": ["o77"]}], "next_steps": ["Write a test"]})


def test_unobserved_dimensions_are_not_scored_and_never_defaulted():
    rep = finalize(PROJECT_VIVA, OBS, [], {}, [("m1", _grade({"technical_depth": 3, "communication": 4}))], [],
                   duration_s=300, utterances=4, questions=2, screens=1, dropped_unverified=1)
    dims = {d["id"]: d for d in rep["dimensions"]}
    assert dims["technical_depth"]["status"] == "observed"
    assert dims["communication"]["status"] == "not_observed" and dims["communication"]["final"] is None
    assert dims["communication"]["council_scores"] == []                  # grader tried to score it: ignored
    assert "Clarity of explanation" in rep["not_observed"]
    assert all(d["final"] is None for d in rep["dimensions"] if d["id"] != "technical_depth")


def test_low_coverage_blocks_a_band_and_requests_human_review():
    rep = finalize(PROJECT_VIVA, OBS, [], {}, [], ["no council"], duration_s=60, utterances=2, questions=1,
                   screens=0, dropped_unverified=0)
    assert rep["overall"]["band"] == "Not enough evidence"
    assert rep["review"]["needs_human_review"]
    assert rep["process"]["narrative_status"] == "unavailable" and rep["strengths"] == []


def test_points_without_checkable_evidence_are_dropped():
    rep = finalize(PROJECT_VIVA, OBS, [], {}, [("m1", _grade({"technical_depth": 3}))], [],
                   duration_s=1, utterances=1, questions=0, screens=0, dropped_unverified=0)
    assert [p["evidence"] for p in rep["strengths"]] == [["o1"]]
    assert rep["growth"] == []                                             # cited o77 which does not exist


def test_grader_disagreement_is_flagged():
    rep = finalize(PROJECT_VIVA, OBS, [], {}, [("a", _grade({"technical_depth": 4})), ("b", _grade({"technical_depth": 0}))],
                   [], duration_s=1, utterances=1, questions=0, screens=0, dropped_unverified=0)
    d = next(x for x in rep["dimensions"] if x["id"] == "technical_depth")
    assert d["spread"] >= 1.5
    assert any("disagree" in r for r in rep["review"]["reasons"])
    assert rep["process"]["council_agreement"] == 0.0


def test_bands():
    assert [band_for(x) for x in (0.2, 1.6, 2.6, 3.5)] == ["Emerging", "Developing", "Proficient", "Strong"]


# ------------------------------------------------------------------------ dossier
def test_repo_url_parsing_rejects_other_hosts():
    assert parse_repo_url("https://github.com/KUNALSHAWW/AI-Automated-Interviewer.git") == ("KUNALSHAWW", "AI-Automated-Interviewer")
    assert parse_repo_url("https://github.com/o/r/tree/main/src") == ("o", "r")
    for bad in ("https://evil.example/o/r", "http://169.254.169.254/latest", "https://github.com.evil.io/o/r", "file:///etc/passwd"):
        with pytest.raises(DossierError):
            parse_repo_url(bad)


def test_strip_comments_removes_narration_but_keeps_code():
    src = "# entrypoint\nimport os\n  # explain\nx = 1  # trailing stays\n"
    assert strip_comments(src, ".py") == "import os\nx = 1  # trailing stays"


async def test_dossier_detects_stack_tests_ci_and_skips_vendor_dirs(http):
    d = await build_dossier("https://github.com/o/shop", http, seed="s1")
    assert d.repo == "o/shop" and d.branch == "main"
    assert {"FastAPI", "Docker", "SQLAlchemy"} <= set(d.techs)
    assert d.has_tests and d.has_ci and d.has_docker
    assert not any("node_modules" in p for p in d.tree_sample)
    assert d.languages.get("Python") == 4
    assert "40%" in d.readme and "evidence_text" not in d.public()
    assert d.probe_topics and d.brief.startswith("o/shop")


async def test_private_repo_gives_a_clear_error(http):
    with pytest.raises(DossierError, match="private"):
        await build_dossier("https://github.com/o/private-repo", http)


# ------------------------------------------------- reasoning models that spend max_tokens thinking
async def test_empty_completion_from_exhausted_budget_is_retried_with_more_tokens(tmp_path):
    budgets = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        budgets.append(body["max_tokens"])
        if body["max_tokens"] < 200:   # all tokens went on hidden reasoning
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    llm = LLMClient(make_settings(tmp_path), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    res = await llm.chat([("ollama", "gpt-oss:120b")], [{"role": "user", "content": "x"}], purpose="t", max_tokens=64)
    assert res.text == "ok" and budgets == [64, 256]


async def test_tool_names_in_source_text_are_not_evidence_of_use(http):
    d = await build_dossier("https://github.com/o/shop", http, seed="s1")
    assert "Kafka" not in d.techs and "Redis" not in d.techs      # only listed as strings in app/lexicon.py
    assert "FastAPI" in d.techs                                    # backed by requirements.txt and an import
    assert "Celery" in d.documented_techs and "Celery" not in d.techs   # README says so, nothing backs it up
