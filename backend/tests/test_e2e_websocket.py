"""End-to-end: HTTP session creation -> WebSocket interview -> evidence -> report -> PDF -> delete.

Runs the real FastAPI app and the real session engine; only the provider network is faked."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings, slide_jpeg, wav_bytes


def _drain_until(ws, want: set[str], seen: list, limit: int = 60):
    for _ in range(limit):
        msg = ws.receive_json()
        seen.append(msg)
        if msg["type"] in want:
            return msg
    raise AssertionError(f"never saw {want}; got {[m['type'] for m in seen]}")


def _client(tmp_path, http, **kw):
    return TestClient(create_app(make_settings(tmp_path, **kw), http=http))


@pytest.mark.timeout(45)
def test_full_interview_flow(tmp_path, net, http):
    with _client(tmp_path, http) as c:
        # --- consent and access are enforced -------------------------------------------------
        assert c.post("/api/sessions", json={"consent": False}).status_code == 400
        r = c.post("/api/sessions", json={"consent": True, "repo_url": "https://github.com/o/shop", "language": "en"})
        assert r.status_code == 200, r.text
        s = r.json()
        sid, token = s["id"], s["token"]
        assert s["repo"]["repo"] == "o/shop" and "FastAPI" in s["repo"]["techs"]

        # --- unauthenticated reads are refused ----------------------------------------------
        assert c.get(f"/api/sessions/{sid}").status_code == 401
        assert c.get(f"/api/sessions/{sid}", headers={"Authorization": "Bearer nope"}).status_code == 401

        seen: list = []
        with c.websocket_connect(s["ws_path"]) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": token}))
            assert ws.receive_json()["type"] == "ready"
            ws.send_text(json.dumps({"type": "start"}))
            opening = _drain_until(ws, {"ai_say"}, seen)
            assert opening["kind"] == "opening" and "o/shop" in opening["text"]
            ws.send_text(json.dumps({"type": "playback", "state": "ended"}))

            # a real audio utterance goes through STT; a slide goes through change detection + vision
            ws.send_bytes(b"\x01" + wav_bytes(2.0))
            ws.send_bytes(b"\x02" + slide_jpeg(["Architecture", "API -> Redis -> Postgres"]))
            ws.send_bytes(b"\x02" + slide_jpeg(["Architecture", "API -> Redis -> Postgres"]))
            _drain_until(ws, {"transcript"}, seen)

            question = _drain_until(ws, {"ai_say"}, seen)          # pacing -> evaluator -> one question
            assert question["kind"] == "question"
            assert question["text"].count("?") == 1                 # "A? And B?" was trimmed to one question
            ws.send_text(json.dumps({"type": "playback", "state": "ended"}))

            kinds = [m["type"] for m in seen]
            assert "evidence" in kinds and "claims" in kinds and "screen" in kinds
            evidence = [m for m in seen if m["type"] == "evidence"]
            assert [e["dimension"] for e in evidence] == ["technical_depth"]   # fabricated 'ownership' quote dropped
            claims = next(m for m in seen if m["type"] == "claims")
            assert "Redis" in claims["not_found"]                    # said, but absent from the repo

            ws.send_text(json.dumps({"type": "stop"}))
            report_msg = _drain_until(ws, {"report", "report_error"}, seen)
            assert report_msg["type"] == "report", report_msg

        rep = report_msg["report"]
        assert rep["process"]["dropped_unverified"] == 1
        dims = {d["id"]: d for d in rep["dimensions"]}
        assert dims["technical_depth"]["status"] == "observed"
        assert dims["ownership"]["status"] == "not_observed" and dims["ownership"]["final"] is None
        assert rep["review"]["needs_human_review"]                   # coverage is thin, Redis not in repo
        assert any("Redis" in f["detail"] for f in rep["flags"])
        assert rep["process"]["council"] and rep["strengths"]

        # --- persisted + retrievable with the token, PDF renders, deletion works ------------
        auth = {"Authorization": f"Bearer {token}"}
        got = c.get(f"/api/sessions/{sid}", headers=auth).json()
        assert got["status"] == "done" and got["report"]["overall"]["band"] == "Not enough evidence"
        pdf = c.get(f"/api/sessions/{sid}/report.pdf", headers=auth)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
        assert c.get(f"/api/sessions/{sid}/thumb/1.jpg", headers=auth).status_code == 200
        assert c.delete(f"/api/sessions/{sid}", headers=auth).status_code == 200
        assert c.get(f"/api/sessions/{sid}", headers=auth).status_code == 401   # token no longer valid


@pytest.mark.timeout(30)
def test_session_is_saved_even_if_report_is_skipped_and_socket_just_closes(tmp_path, net, http):
    """Regression: the old server only saved interviews when a report was requested."""
    with _client(tmp_path, http) as c:
        s = c.post("/api/sessions", json={"consent": True}).json()
        with c.websocket_connect(s["ws_path"]) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": s["token"]}))
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start"}))
            ws.send_text(json.dumps({"type": "text", "text": "We built a small FastAPI service for orders."}))
            time.sleep(0.3)
        deadline = time.time() + 10
        status = None
        while time.time() < deadline:
            status = c.get(f"/api/sessions/{s['id']}", headers={"Authorization": f"Bearer {s['token']}"}).json()["status"]
            if status in {"done", "report_failed", "ended"}:
                break
            time.sleep(0.2)
        assert status in {"done", "ended"}


def test_websocket_rejects_bad_token_and_session_reuse(tmp_path, net, http):
    with _client(tmp_path, http) as c:
        s = c.post("/api/sessions", json={"consent": True}).json()
        with c.websocket_connect(s["ws_path"]) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "wrong"}))
            assert ws.receive_json()["code"] == "auth"


def test_health_reports_missing_keys_loudly(tmp_path, net, http):
    with _client(tmp_path, http, groq_api_key="", ollama_api_key="", openrouter_api_key="") as c:
        h = c.get("/api/health").json()
        assert h["ready"] is False and any("interviewer model" in p for p in h["problems"])
        r = c.post("/api/sessions", json={"consent": True})
        assert r.status_code == 503


def test_access_code_and_rate_limit(tmp_path, net, http):
    with _client(tmp_path, http, access_code="letmein", sessions_per_hour_per_ip=2) as c:
        assert c.post("/api/sessions", json={"consent": True}).status_code == 403
        ok = {"consent": True, "access_code": "letmein"}
        assert c.post("/api/sessions", json=ok).status_code == 200
        assert c.post("/api/sessions", json=ok).status_code == 200
        assert c.post("/api/sessions", json=ok).status_code == 429


def test_rubric_endpoint_and_custom_rubric(tmp_path, net, http):
    with _client(tmp_path, http) as c:
        ids = [r["id"] for r in c.get("/api/rubrics").json()["rubrics"]]
        assert {"project_viva", "hackathon_judging", "mock_interview"} <= set(ids)
        custom = {"title": "Demo day", "dimensions": [{"id": "impact", "weight": 2}, {"id": "ux", "weight": 1}]}
        s = c.post("/api/sessions", json={"consent": True, "rubric": custom}).json()
        assert [d["id"] for d in s["rubric"]["dimensions"]] == ["impact", "ux"]
        assert c.post("/api/sessions", json={"consent": True, "rubric": {"dimensions": []}}).status_code == 400


# ------------------------------------------------------- regressions for the old architecture bugs
@pytest.mark.timeout(40)
def test_stop_is_processed_while_the_llm_is_slow(tmp_path, net):
    """Old server: STT -> LLM -> TTS ran inside the receive loop, so 'End Interview' waited behind them."""
    import asyncio

    import httpx

    async def slow(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            if "Nova" in str(body["messages"][0]["content"]):
                await asyncio.sleep(6)           # a very slow interviewer model
        return net.handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    with _client(tmp_path, http) as c:
        s = c.post("/api/sessions", json={"consent": True}).json()
        seen: list = []
        with c.websocket_connect(s["ws_path"]) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": s["token"]}))
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start"}))
            _drain_until(ws, {"ai_say"}, seen)
            ws.send_text(json.dumps({"type": "playback", "state": "ended"}))
            ws.send_text(json.dumps({"type": "text", "text": "We built a FastAPI service with Redis caching and Docker."}))
            _drain_until(ws, {"status"}, seen)
            _drain_until(ws, {"transcript"}, seen)
            t0 = time.time()
            while not any(m.get("state") == "thinking" for m in seen if m["type"] == "status"):
                seen.append(ws.receive_json())      # wait until the (slow) evaluation is in flight
            ws.send_text(json.dumps({"type": "stop"}))
            _drain_until(ws, {"ended"}, seen)
            assert time.time() - t0 < 5, "stop waited behind the slow LLM call"


@pytest.mark.timeout(30)
def test_reshare_timer_is_cancelled_on_restore(tmp_path, net, http):
    """Old server: the 30 s timer was never cancelled, so lose -> restore -> lose ended the interview early."""
    with _client(tmp_path, http, reshare_timeout_s=3.0) as c:
        s = c.post("/api/sessions", json={"consent": True}).json()
        seen: list = []
        with c.websocket_connect(s["ws_path"]) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": s["token"]}))
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start"}))
            _drain_until(ws, {"ai_say"}, seen)
            ws.send_text(json.dumps({"type": "screen_state", "active": False}))
            _drain_until(ws, {"screen_lost"}, seen)
            time.sleep(1.0)
            ws.send_text(json.dumps({"type": "screen_state", "active": True}))
            _drain_until(ws, {"screen_restored"}, seen)
            time.sleep(0.5)
            ws.send_text(json.dumps({"type": "screen_state", "active": False}))
            _drain_until(ws, {"screen_lost"}, seen)
            time.sleep(1.8)                           # now past the FIRST timer's deadline (1.0+0.5+1.8 > 3.0 from t0)
            ws.send_text(json.dumps({"type": "ping"}))
            msgs = []
            while True:
                m = ws.receive_json()
                msgs.append(m["type"])
                if m["type"] == "pong":
                    break
            assert "ended" not in msgs                # still alive: the second window is its own full timeout
            ended = _drain_until(ws, {"ended"}, seen)  # and it does end once its own timeout elapses
            assert ended["auto"] is True
