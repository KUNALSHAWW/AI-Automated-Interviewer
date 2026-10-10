"""HTTP + WebSocket API.

Security model (the old server had none): sessions are created with POST /api/sessions (optional organizer
ACCESS_CODE, per-IP rate limit, explicit consent), return a secret token, and every later request must
present it. CORS is an allow-list, not "*". Data is deletable and expires after RETENTION_DAYS.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .dossier import DossierError, build_dossier
from .providers.llm import LLMClient
from .providers.stt import STTClient
from .rubrics import PRESETS, Rubric, resolve
from .session import InterviewSession, _write_pdf, make_report
from .settings import Settings
from .store import Store

log = logging.getLogger("navai")
THUMB_RE = re.compile(r"^\d{1,3}\.jpg$")


class CreateSession(BaseModel):
    repo_url: str | None = Field(default=None, max_length=300)
    rubric_id: str | None = None
    rubric: dict | None = None
    language: Literal["en", "hi", "auto"] = "en"
    title: str = Field(default="", max_length=80)
    access_code: str = Field(default="", max_length=100)
    consent: bool = False


class RateLimiter:
    def __init__(self, limit: int, window_s: float = 3600.0):
        self.limit, self.window, self._hits = limit, window_s, defaultdict(deque)

    def allow(self, key: str) -> bool:
        now, q = time.monotonic(), self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def create_app(settings: Settings | None = None, *, llm: LLMClient | None = None, stt: STTClient | None = None,
               store: Store | None = None, http: httpx.AsyncClient | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = http or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=8.0))
        app.state.http = client
        app.state.llm = llm or LLMClient(cfg, client)
        app.state.stt = stt or STTClient(cfg, client)
        app.state.store = store or Store(cfg.data_dir)
        app.state.active = {}
        purged = app.state.store.purge_older_than(cfg.retention_days)
        log.info("NavAI Viva %s started; purged %d expired sessions; live chain=%s", __version__, purged,
                 [f"{p}:{m}" for p, m in cfg.chain_available(cfg.live_chain)])
        try:
            yield
        finally:
            for s in list(app.state.active.values()):
                await s.end(auto=True)
            if http is None:
                await client.aclose()
            if store is None:
                app.state.store.close()

    app = FastAPI(title="NavAI Viva", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origins), allow_credentials=False,
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type"])
    limiter = RateLimiter(cfg.sessions_per_hour_per_ip)
    deep_lock = {"last": 0.0}

    # ------------------------------------------------------------------ helpers
    def client_ip(request: Request) -> str:
        if cfg.trust_proxy:
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def chain_status() -> dict:
        def rows(chain):
            return [{"provider": p, "model": m, "configured": cfg.provider_ready(p)} for p, m in chain]
        return {"live": rows(cfg.live_chain), "vision": rows(cfg.vision_chain), "council": rows(cfg.council_chain),
                "stt": rows([(p, m) for p, m in cfg.stt_chain if p in ("groq", "openrouter")])}

    def readiness() -> dict:
        ch = chain_status()
        ok = {k: any(r["configured"] for r in v) for k, v in ch.items()}
        problems = []
        if not ok["live"]:
            problems.append("No interviewer model is configured. Set OLLAMA_API_KEY, GROQ_API_KEY or OPENROUTER_API_KEY.")
        if not ok["stt"]:
            problems.append("No speech-to-text provider is configured (set GROQ_API_KEY or OPENROUTER_API_KEY). "
                            "Typed answers still work.")
        if not ok["vision"]:
            problems.append("No vision model is configured; screens will be saved but not described.")
        if not ok["council"]:
            problems.append("No grading model is configured; reports will contain scores but no narrative.")
        return {"ready": ok["live"], "capabilities": ok, "problems": problems}

    def authorize(request: Request, sid: str) -> dict:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
        st: Store = app.state.store
        if not token or not st.check_token(sid, token):
            raise HTTPException(401, "Missing or invalid session token")
        rec = st.get(sid)
        if rec is None:
            raise HTTPException(404, "Session not found")
        return rec

    # --------------------------------------------------------------------- meta
    @app.get("/api/health")
    async def health():
        return {"version": __version__, **readiness(), "chains": chain_status(),
                "breaker": app.state.llm.breaker.snapshot(), "stt_breaker": app.state.stt.breaker.snapshot(),
                "access_code_required": bool(cfg.access_code), "max_session_minutes": cfg.max_session_minutes,
                "retention_days": cfg.retention_days,
                "active_sessions": len(app.state.active), "max_concurrent_sessions": cfg.max_concurrent_sessions}

    @app.get("/api/health/deep")
    async def health_deep(request: Request):
        """Live check: one tiny call per configured provider. Spends quota, so it needs the access code when one
        is configured (header X-Access-Code or ?access_code=) and is throttled."""
        if cfg.access_code:
            given = request.headers.get("x-access-code") or request.query_params.get("access_code", "")
            if not hmac.compare_digest(given, cfg.access_code):
                raise HTTPException(403, "Access code required")
        now = time.monotonic()
        if now - deep_lock["last"] < 15:
            raise HTTPException(429, "Deep health check ran moments ago; wait a few seconds.")
        deep_lock["last"] = now
        seen, out = set(), []
        llm_: LLMClient = app.state.llm
        for chain in (cfg.live_chain, cfg.vision_chain, cfg.council_chain):
            for p, m in cfg.chain_available(chain):
                if (p, m) in seen:
                    continue
                seen.add((p, m))
                out.append({"kind": "chat", "provider": p, "model": m, **(await llm_.ping(p, m))})
        for p, m in cfg.chain_available(cfg.stt_chain):
            out.append({"kind": "stt", "provider": p, "model": m, **(await app.state.stt.ping(p, m))})
        return {"checked": out}

    @app.get("/api/rubrics")
    async def rubrics():
        return {"rubrics": [r.as_dict() for r in PRESETS.values()]}

    # ----------------------------------------------------------------- sessions
    @app.post("/api/sessions")
    async def create_session(body: CreateSession, request: Request):
        if cfg.access_code and not hmac.compare_digest(body.access_code, cfg.access_code):
            raise HTTPException(403, "Invalid access code")
        if not body.consent:
            raise HTTPException(400, "Consent is required: audio, screen frames and transcript are processed by the "
                                     "configured AI providers and stored until you delete them.")
        if not limiter.allow(client_ip(request)):
            raise HTTPException(429, "Too many interviews started from this address; try again later.")
        r = readiness()
        if not r["ready"]:
            raise HTTPException(503, " ".join(r["problems"]))
        if len(app.state.active) >= cfg.max_concurrent_sessions:
            raise HTTPException(503, "The interviewer is busy. Please try again in a few minutes.")
        try:
            rubric = resolve(body.rubric_id, body.rubric)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

        st: Store = app.state.store
        meta = {"language": body.language, "title": body.title.strip(), "repo_url": None, "rubric_id": rubric.id}
        sid, token = st.create(meta)
        meta["id"], warnings, dossier = sid, [], None
        if body.repo_url:
            try:
                dossier = await build_dossier(body.repo_url, app.state.http, token=cfg.github_token, seed=sid)
                meta["repo_url"] = dossier.url
            except DossierError as e:
                warnings.append(str(e))
        st.update(sid, meta={**meta, "created": time.time(), "rubric": rubric.as_dict()},
                  state={"dossier": asdict(dossier)} if dossier else None)
        return {"id": sid, "token": token, "ws_path": f"/ws/interview/{sid}", "rubric": rubric.as_dict(),
                "repo": dossier.public() if dossier else None, "warnings": warnings, **{"readiness": r}}

    @app.get("/api/sessions/{sid}")
    async def get_session(sid: str, request: Request):
        rec = authorize(request, sid)
        state = rec.get("state") or {}
        return {"id": sid, "status": rec["status"], "created": rec["created"], "meta": rec["meta"],
                "report": rec["report"], "questions": len(state.get("asked", []))}

    @app.get("/api/sessions/{sid}/report.pdf")
    async def get_pdf(sid: str, request: Request):
        rec = authorize(request, sid)
        pdf = app.state.store.session_dir(sid) / "report.pdf"
        if not pdf.exists():
            if rec["report"]:
                await _write_pdf(app.state.store, sid, rec["report"], {**rec["meta"], "created": rec["created"]})
            else:
                raise HTTPException(404, "No report yet")
        return FileResponse(pdf, media_type="application/pdf", filename=f"navai_report_{sid}.pdf")

    @app.get("/api/sessions/{sid}/thumb/{name}")
    async def get_thumb(sid: str, name: str, request: Request):
        authorize(request, sid)
        if not THUMB_RE.match(name):
            raise HTTPException(404, "Not found")
        p = app.state.store.session_dir(sid) / "thumbs" / name
        if not p.exists():
            raise HTTPException(404, "Not found")
        return FileResponse(p, media_type="image/jpeg")

    @app.post("/api/sessions/{sid}/report")
    async def regenerate(sid: str, request: Request):
        rec = authorize(request, sid)
        if sid in app.state.active:
            raise HTTPException(409, "Interview still running")
        state = rec.get("state")
        if not state or "segments" not in state:
            raise HTTPException(409, "Interview has no recorded content yet")
        rub = Rubric.from_dict(rec["meta"]["rubric"])
        meta = {**rec["meta"], "id": sid, "created": rec["created"]}
        report = await make_report(app.state.llm, cfg, rub, state, meta)
        app.state.store.update(sid, status="done", report=report)
        await _write_pdf(app.state.store, sid, report, meta)
        return report

    @app.delete("/api/sessions/{sid}")
    async def delete_session(sid: str, request: Request):
        authorize(request, sid)
        s = app.state.active.get(sid)
        if s:
            await s.end(auto=True)
        app.state.store.delete(sid)
        return {"deleted": sid}

    # ---------------------------------------------------------------- websocket
    @app.websocket("/ws/interview/{sid}")
    async def ws_interview(ws: WebSocket, sid: str):
        await ws.accept()
        st: Store = app.state.store
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), 8.0))
        except (asyncio.TimeoutError, ValueError, WebSocketDisconnect, RuntimeError):
            await _close(ws, 4400)
            return
        if first.get("type") != "auth" or not st.check_token(sid, str(first.get("token", ""))):
            await ws.send_json({"type": "error", "code": "auth", "message": "Invalid session token"})
            await _close(ws, 4401)
            return
        rec = st.get(sid)
        if not rec or rec["status"] != "created" or sid in app.state.active:
            await ws.send_json({"type": "error", "code": "state", "message": "This session cannot be started again"})
            await _close(ws, 4409)
            return
        if len(app.state.active) >= cfg.max_concurrent_sessions:
            await ws.send_json({"type": "error", "code": "busy", "message": "The interviewer is busy"})
            await _close(ws, 4429)
            return

        meta = {**rec["meta"], "id": sid, "created": rec["created"]}
        rub = Rubric.from_dict(meta["rubric"])
        dossier = _dossier_from_state(rec.get("state"))
        session = InterviewSession(sid=sid, meta=meta, rubric=rub, dossier=dossier, llm=app.state.llm,
                                   stt=app.state.stt, settings=cfg, store=st, send=ws.send_json)
        app.state.active[sid] = session
        started = False
        st.update(sid, status="live")
        await ws.send_json({"type": "ready", "providers": readiness()})
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    await session.handle_binary(msg["bytes"])
                elif msg.get("text") is not None:
                    try:
                        data = json.loads(msg["text"])
                    except ValueError:
                        continue
                    if data.get("type") == "start" and not started:
                        started = True
                        await session.start()
                    elif data.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                    elif started:
                        await session.handle_json(data)
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("websocket error")
        finally:
            try:
                if started:
                    await session.end(auto=True)
                else:
                    st.update(sid, status="created")
            finally:
                app.state.active.pop(sid, None)

    # ------------------------------------------------------------- static SPA
    dist = cfg.frontend_dist
    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")
    else:
        @app.get("/")
        async def root():
            return JSONResponse({"service": "NavAI Viva", "version": __version__,
                                 "note": "Frontend not built. Run `npm run build` in frontend/ or use the Vite dev server."})
    return app


async def _close(ws: WebSocket, code: int) -> None:
    try:
        await ws.close(code=code)
    except Exception:
        pass


def _dossier_from_state(state: dict | None):
    from .dossier import Dossier
    raw = (state or {}).get("dossier")
    if not raw:
        return None
    return Dossier(**{k: v for k, v in raw.items() if k in Dossier.__dataclass_fields__})


app = create_app()
