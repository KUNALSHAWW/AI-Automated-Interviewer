"""One live interview.

Architecture (fixes the old single-await loop, where STT -> LLM -> TTS all ran inside the WebSocket
receive loop and everything else, including "End Interview", waited):

    receive loop  --(non-blocking put)-->  utterance queue  -->  stt worker   -> segments
                  --(latest frame wins)->  vision worker (tile change detector -> vision model)
    director (0.5 s tick): pacing.decide() -> evaluator -> ai_say event (browser speaks it)

The socket handler only enqueues. Speaking state comes from the browser's playback events, not a guess.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import Counter
from dataclasses import asdict
from typing import Awaitable, Callable

from .dossier import Dossier
from .evaluator import EvaluationError, Segment, TurnContext, evaluate_turn
from .evidence import norm
from .grading import aggregate, build_packet, council_grade, finalize
from .pacing import TurnInputs, decide, is_invitation, word_count
from .providers.common import AllProvidersFailed, Usage
from .providers.llm import LLMClient
from .providers.stt import STTClient
from .rubrics import Rubric
from .settings import Settings
from .store import Store
from .techlex import check_claims, normalize_transcript
from .vision import ChangeDetector, describe, thumbnail

log = logging.getLogger("navai.session")

KIND_AUDIO, KIND_FRAME = 1, 2
MAX_WAV = 60 * 32000 + 44 + 1024
MAX_FRAME = 2_000_000
Send = Callable[[dict], Awaitable[None]]

OPENING = {
    "en": "Hi, I'm Nova. {repo}Please start with a one-minute overview of what you built and why, and share your "
          "screen when you're ready.",
    "auto": "Hi, I'm Nova. {repo}Please start with a one-minute overview of what you built and why, and share your "
            "screen when you're ready. English, Hindi or a mix is fine.",
    "hi": "नमस्ते, मैं नोवा हूँ। {repo}कृपया एक मिनट में बताइए कि आपने क्या बनाया और क्यों, और तैयार होने पर अपनी स्क्रीन साझा कीजिए।",
}
OPENING_REPO = {
    "en": "I've looked at {repo} on GitHub{stack}. ",
    "hi": "मैंने GitHub पर {repo} देखा है{stack}। ",
}
CLOSING = {"en": "Thank you. I'll prepare your feedback now.", "hi": "धन्यवाद। मैं अब आपका फ़ीडबैक तैयार करता हूँ।"}
RESHARE = {
    "en": "I can't see your screen any more. Please share it again, or end the interview.",
    "hi": "आपकी स्क्रीन दिखाई नहीं दे रही। कृपया फिर से साझा करें, या इंटरव्यू समाप्त करें।",
}
WELCOME_BACK = {"en": "Great, I can see your screen again. Please continue.", "hi": "ठीक है, स्क्रीन फिर से दिख रही है। कृपया जारी रखें।"}


class InterviewSession:
    def __init__(self, *, sid: str, meta: dict, rubric: Rubric, dossier: Dossier | None, llm: LLMClient,
                 stt: STTClient, settings: Settings, store: Store, send: Send, clock=time.monotonic):
        self.sid, self.meta, self.rubric, self.dossier = sid, meta, rubric, dossier
        self.llm, self.stt, self.cfg, self.store = llm, stt, settings, store
        self._send, self._clock = send, clock
        self.language = meta.get("language", "en")
        self.usage = Usage()

        # lifecycle
        self.active = False
        self._ended = False
        self._t0 = 0.0
        self._tasks: list[asyncio.Task] = []
        self._reshare_task: asyncio.Task | None = None
        self._end_task: asyncio.Task | None = None
        self._awaiting_reshare = False

        # transcript + evidence
        self.segments: list[Segment] = []
        self.observations: list[dict] = []
        self.flags: list[dict] = []
        self.asked: list[dict] = []
        self.screens: list[dict] = []
        self.screen: dict | None = None
        self._dropped = 0
        self._utterances = 0
        self._seen_obs: set[tuple] = set()
        self._claims_seen = {"supported": set(), "documented_only": set(), "not_found": set(),
                             "unverified_metrics": set()}

        # turn taking
        self._consumed_upto = 0
        self._words_since_ai = 0
        self._last_speech_at = 0.0
        self._last_ai_at = 0.0
        self._invited = False
        self._screen_changed = False
        self._ai_busy = False
        self._ai_speaking = False
        self._speaking_deadline = 0.0
        self._eval_not_before = 0.0
        self._transcribing = 0
        self._probe_used: set[str] = set()

        # io
        self._utt_q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._frame: bytes | None = None
        self._frame_evt = asyncio.Event()
        self.detector = ChangeDetector(settings.tile_threshold, settings.min_changed_tiles)
        self._warned: dict[str, float] = {}
        self._stt_prompt = self._make_stt_prompt()

    # ------------------------------------------------------------------ helpers
    def _now(self) -> float:
        return max(0.0, self._clock() - self._t0) if self._t0 else 0.0

    async def _emit(self, type_: str, **data) -> None:
        try:
            await self._send({"type": type_, "t": round(self._now(), 1), **data})
        except Exception as e:  # socket already closed
            log.debug("send failed: %s", e)

    async def _warn(self, code: str, text: str, errors: list | None = None) -> None:
        now = self._clock()
        if now - self._warned.get(code, -1e9) < 30:
            return
        self._warned[code] = now
        await self._emit("warning", code=code, message=text, details=errors or [])

    def _make_stt_prompt(self) -> str | None:
        if not self.dossier:
            return None
        terms = ", ".join(self.dossier.techs[:25])
        return f"A student presents a software project called {self.dossier.repo.split('/')[-1]}. Terms: {terms}."[:600]

    def _lang(self) -> str:
        """Key into the opening/closing phrase tables."""
        return "hi" if self.language == "hi" else "en"

    def _tts_lang(self) -> str:
        return {"hi": "hi-IN", "auto": "en-IN"}.get(self.language, "en-US")

    # --------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        self.active = True
        self._t0 = self._clock()
        self._last_speech_at = self._clock()
        self._tasks = [asyncio.create_task(self._stt_loop(), name="stt"),
                       asyncio.create_task(self._vision_loop(), name="vision"),
                       asyncio.create_task(self._director(), name="director")]
        repo_txt = ""
        if self.dossier:
            stack = ", ".join(self.dossier.techs[:4])
            tail = (f", which uses {stack}" if self._lang() == "en" else f", जिसमें {stack} है") if stack else ""
            repo_txt = OPENING_REPO[self._lang()].format(repo=self.dossier.repo, stack=tail)
        opening = OPENING["auto"] if self.language == "auto" else OPENING[self._lang()]
        await self._say(opening.format(repo=repo_txt), kind="opening")

    async def end(self, *, auto: bool = False) -> None:
        if self._ended:
            return
        self._ended, self.active = True, False
        me = asyncio.current_task()
        for t in (self._reshare_task, *[t for t in self._tasks if t.get_name() != "stt"]):
            if t and t is not me:
                t.cancel()
        with contextlib.suppress(asyncio.TimeoutError, Exception):
            await asyncio.wait_for(self._utt_q.join(), 10.0)  # let queued speech finish transcribing
        for t in self._tasks:
            if t is not me:
                t.cancel()
        await asyncio.gather(*[t for t in self._tasks if t is not me], return_exceptions=True)
        await self._emit("ended", auto=auto)
        state = self.export_state(auto=auto)
        self.store.update(self.sid, status="ended", state=state)
        await self.finalize_report(state)

    async def finalize_report(self, state: dict) -> None:
        await self._emit("report_status", state="working")
        try:
            report = await make_report(self.llm, self.cfg, self.rubric, state, self.meta)
            self.store.update(self.sid, status="done", report=report)
            await _write_pdf(self.store, self.sid, report, self.meta)
            await self._emit("report", report=report)
        except Exception as e:  # never leave the user waiting silently
            log.exception("report failed")
            self.store.update(self.sid, status="report_failed")
            await self._emit("report_error", message=f"Report generation failed: {type(e).__name__}")

    # ----------------------------------------------------------- inbound events
    async def handle_binary(self, data: bytes) -> None:
        if not self.active or len(data) < 2:
            return
        kind, payload = data[0], data[1:]
        if kind == KIND_AUDIO:
            if len(payload) < 3200 or len(payload) > MAX_WAV:
                return
            if self._utt_q.full():  # shed oldest rather than stall the socket
                with contextlib.suppress(asyncio.QueueEmpty):
                    self._utt_q.get_nowait()
                    self._utt_q.task_done()
                await self._warn("stt_backlog", "Speech is arriving faster than it can be transcribed; "
                                                "the oldest clip was skipped.")
            self._utt_q.put_nowait((payload, self._now()))
        elif kind == KIND_FRAME and len(payload) <= MAX_FRAME:
            self._frame = payload
            self._frame_evt.set()

    async def handle_json(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "playback":
            if msg.get("state") == "ended":
                self._ai_speaking = False
                self._last_ai_at = self._clock()
                if not self._ai_busy:
                    await self._emit("status", state="listening")
            elif msg.get("state") == "started":
                self._ai_speaking = True
                self._speaking_deadline = max(self._speaking_deadline, self._clock() + 120)
        elif t == "interrupt":
            self._ai_speaking = False
            self._last_ai_at = self._clock()
            await self._emit("status", state="listening")
        elif t == "text":
            txt = str(msg.get("text", "")).strip()[:1200]
            if txt and self.active:
                await self._add_segment(txt, self._now(), "typed")
        elif t == "screen_state":
            await (self._on_screen_restored() if msg.get("active") else self._on_screen_lost())
        elif t == "stop" and not self._ended:
            self._end_task = asyncio.create_task(self.end())  # never block the socket on report generation

    # --------------------------------------------------------------- stt worker
    async def _stt_loop(self) -> None:
        while True:
            wav, arrived = await self._utt_q.get()
            self._transcribing += 1
            try:
                lang = None if self.language == "auto" else self.language
                try:
                    res = await self.stt.transcribe(wav, language=lang, prompt=self._stt_prompt, usage=self.usage)
                except AllProvidersFailed as e:
                    await self._warn("stt", "Speech-to-text is unavailable: " + _why(e), [x.public() for x in e.errors])
                    continue
                self._utterances += 1
                if res.text:
                    await self._add_segment(res.text, max(0.0, arrived - res.seconds), "speech",
                                            stt_s=round(res.latency_s, 2))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("stt worker error")
            finally:
                self._transcribing -= 1
                self._utt_q.task_done()

    async def _add_segment(self, text: str, t: float, source: str, stt_s: float | None = None) -> None:
        seg = Segment(id=len(self.segments) + 1, text=normalize_transcript(text.strip()), t=round(t, 1))
        self.segments.append(seg)
        self._words_since_ai += word_count(seg.text)
        self._last_speech_at = self._clock()
        self._invited = self._invited or is_invitation(seg.text)
        await self._emit("transcript", id=seg.id, text=seg.text, source=source, at=seg.t, stt_s=stt_s)

    # ------------------------------------------------------------ vision worker
    async def _vision_loop(self) -> None:
        last = -1e9
        while True:
            await self._frame_evt.wait()
            self._frame_evt.clear()
            frame = self._frame
            if frame is None:
                continue
            try:
                changed = await asyncio.to_thread(self.detector.feed, frame)
            except Exception:
                log.debug("bad frame", exc_info=True)
                continue
            if not changed or self._clock() - last < self.cfg.vision_min_interval_s:
                continue  # a rate-limited change stays pending: feed() keeps returning True until commit()
            self.detector.commit()
            last = self._clock()
            await self._analyse_screen(frame)

    async def _analyse_screen(self, frame: bytes) -> None:
        idx = len(self.screens) + 1
        rec: dict = {"id": idx, "t": round(self._now(), 1), "analysis": "pending"}
        try:
            thumb = await asyncio.to_thread(thumbnail, frame)
            d = self.store.session_dir(self.sid) / "thumbs"
            d.mkdir(exist_ok=True)
            (d / f"{idx}.jpg").write_bytes(thumb)
            rec["thumb"] = f"{idx}.jpg"
        except Exception:
            log.debug("thumbnail failed", exc_info=True)
        if not self.cfg.chain_available(self.cfg.vision_chain):
            rec["analysis"] = "unavailable"
            await self._warn("vision_key", "No vision model has an API key; slides are saved as images but not described.")
        else:
            try:
                rec.update(await describe(self.llm, self.cfg, frame, usage=self.usage))
                rec["analysis"] = "ok"
                self.screen = rec
            except AllProvidersFailed as e:
                rec["analysis"] = "failed"
                await self._warn("vision", "Screen analysis failed: " + _why(e), [x.public() for x in e.errors])
        self.screens.append(rec)
        self._screen_changed = True
        await self._emit("screen", **{k: rec.get(k) for k in
                                      ("id", "title", "summary", "content_type", "technologies", "analysis", "thumb")})

    # ----------------------------------------------------------------- director
    async def _director(self) -> None:
        while self.active:
            await asyncio.sleep(0.5)
            now = self._clock()
            if now - self._t0 > self.cfg.max_session_minutes * 60:
                asyncio.create_task(self._time_up())
                return
            if self._ai_speaking and now > self._speaking_deadline:  # client never reported playback end
                self._ai_speaking, self._last_ai_at = False, now
            if self._awaiting_reshare or now < self._eval_not_before:
                continue
            d = decide(TurnInputs(now=now, last_speech_at=self._last_speech_at, last_ai_at=self._last_ai_at,
                                  words_since_ai=self._words_since_ai, invited=self._invited,
                                  screen_changed_since_ai=self._screen_changed, ai_busy=self._ai_busy,
                                  ai_speaking=self._ai_speaking, transcribing=self._transcribing + self._utt_q.qsize()),
                       self.cfg)
            if d.ask:
                await self._take_turn(d.reason)

    async def _time_up(self) -> None:
        await self._say(CLOSING[self._lang()], kind="closing")
        await asyncio.sleep(2)
        await self.end(auto=True)

    async def _take_turn(self, reason: str) -> None:
        self._ai_busy = True
        try:
            await self._emit("status", state="thinking")
            segs = [s for s in self.segments if s.id > self._consumed_upto]
            if not segs and not self._screen_changed:
                return
            spoken = " ".join(s.text for s in segs)
            screen_text = self._screen_text()
            claim = (check_claims(spoken, self.dossier.evidence_text, set(self.dossier.techs), screen_text,
                                  set(self.dossier.documented_techs)) if self.dossier else {})
            cov = Counter(o["dimension"] for o in self.observations)
            left = [p for p in (self.dossier.probe_topics if self.dossier else []) if p not in self._probe_used]
            ctx = TurnContext(rubric=self.rubric, segments=segs or self.segments[-3:], language=self.language,
                              dossier=self.dossier, screen=self.screen, claim_check=claim, coverage=dict(cov),
                              asked=[a["question"] for a in self.asked], probe_topics=left,
                              invited=self._invited, force_ask=reason == "long_monologue")
            try:
                res = await evaluate_turn(self.llm, self.cfg, ctx, usage=self.usage)
            except (AllProvidersFailed, EvaluationError) as e:
                self._eval_not_before = self._clock() + 15
                errs = [x.public() for x in e.errors] if isinstance(e, AllProvidersFailed) else []
                await self._warn("llm", "The interviewer model is unavailable: " + _why(e), errs)
                return
            self._dropped += res.dropped
            await self._record(res.observations, res.flags, claim)
            if res.action in ("ask", "acknowledge") and res.message:
                if res.action == "ask":
                    self.asked.append({"question": res.message, "t": round(self._now(), 1), "target": res.target,
                                       "reason": reason, "model": res.model, "fixes": res.fixes,
                                       "eval_s": round(res.latency_s, 2)})
                    self._probe_used |= {p for p in left if res.target and res.target.lower() in p.lower()}
                await self._say(res.message, kind="question" if res.action == "ask" else "ack")
                self._consumed_upto = segs[-1].id if segs else self._consumed_upto
                self._words_since_ai, self._invited, self._screen_changed = 0, False, False
            else:
                self._eval_not_before = self._clock() + 6  # model said "wait": do not re-ask every tick
                self._invited = False
        finally:
            self._ai_busy = False
            if not self._ai_speaking and self.active:
                await self._emit("status", state="listening")

    def _screen_text(self) -> str:
        if not self.screen:
            return ""
        s = self.screen
        return " ".join([s.get("title", ""), s.get("summary", ""), *s.get("visible_text", []),
                         *s.get("key_points", []), *s.get("technologies", [])])

    async def _record(self, observations: list[dict], flags: list[dict], claim: dict) -> None:
        for o in observations:
            key = (o["dimension"], tuple(norm(o["quote"])))
            if key in self._seen_obs:
                continue
            self._seen_obs.add(key)
            o["id"] = f"o{len(self.observations) + 1}"
            self.observations.append(o)
            dim = self.rubric.get(o["dimension"])
            await self._emit("evidence", id=o["id"], dimension=o["dimension"], label=dim.label if dim else o["dimension"],
                             score=o["score"], quote=o["quote"], at=o["t"], source=o["source"])
        for f in flags:
            if any(f["detail"] == x["detail"] for x in self.flags):
                continue
            f["t"] = round(self._now(), 1)
            self.flags.append(f)
            await self._emit("flag", **f)
        if claim:
            for k in self._claims_seen:
                self._claims_seen[k] |= set(claim.get(k, []))
            await self._emit("claims", **{k: sorted(v) for k, v in self._claims_seen.items()})

    async def _say(self, text: str, kind: str) -> None:
        self._ai_speaking = True
        self._speaking_deadline = self._clock() + word_count(text) / 2.2 + 5
        await self._emit("ai_say", text=text, kind=kind, lang=self._tts_lang())
        await self._emit("status", state="speaking")

    # -------------------------------------------------------- screen share loss
    async def _on_screen_lost(self) -> None:
        if not self.active or self._awaiting_reshare:
            return
        self._awaiting_reshare = True
        await self._emit("screen_lost", timeout_s=self.cfg.reshare_timeout_s)
        await self._say(RESHARE[self._lang()], kind="system")
        self._reshare_task = asyncio.create_task(self._reshare_timeout())

    async def _reshare_timeout(self) -> None:
        await asyncio.sleep(self.cfg.reshare_timeout_s)
        if self._awaiting_reshare and self.active:
            await self._say(CLOSING[self._lang()], kind="closing")
            await self.end(auto=True)

    async def _on_screen_restored(self) -> None:
        if not self._awaiting_reshare:
            return
        self._awaiting_reshare = False
        if self._reshare_task:
            self._reshare_task.cancel()  # fixes: the old timer kept running and ended later share losses early
            self._reshare_task = None
        self.detector.reset()
        await self._emit("screen_restored")
        await self._say(WELCOME_BACK[self._lang()], kind="system")

    # --------------------------------------------------------------- persistence
    def export_state(self, auto: bool = False) -> dict:
        return {
            "segments": [asdict(s) for s in self.segments],
            "observations": self.observations, "flags": self.flags, "asked": self.asked,
            "screens": self.screens, "dropped_unverified": self._dropped, "utterances": self._utterances,
            "duration_s": round(self._now()), "usage": self.usage.as_dict(), "ended_auto": auto,
            "dossier": asdict(self.dossier) if self.dossier else None,
        }


def _why(e: Exception) -> str:
    if isinstance(e, AllProvidersFailed) and e.errors:
        kinds = "; ".join(f"{x.provider} {x.kind}" for x in e.errors[:4])
        return kinds
    return str(e)[:160]


# ---------------------------------------------------------------- report builder
async def make_report(llm: LLMClient, cfg: Settings, rubric: Rubric, state: dict, meta: dict) -> dict:
    """Pure function of the stored state, so a report can be regenerated later from the database."""
    usage = Usage()
    dossier = state.get("dossier") or None
    spoken = " ".join(s["text"] for s in state["segments"])
    screen_text = " ".join(" ".join([s.get("title", ""), s.get("summary", ""), *s.get("visible_text", []),
                                     *s.get("technologies", [])]) for s in state["screens"] if s.get("analysis") == "ok")
    claims = (check_claims(spoken, dossier.get("evidence_text", ""), set(dossier.get("techs", [])), screen_text,
                           set(dossier.get("documented_techs", []))) if dossier else {})
    flags = list(state["flags"])

    def _already_flagged(tech: str) -> bool:  # the interviewer model often raised the same point in its own words
        return any(tech.lower() in f["detail"].lower() for f in flags)

    for tech in claims.get("not_found", []):
        if not _already_flagged(tech):
            flags.append({"kind": "speech_vs_repo", "t": 0.0, "quote": "",
                          "detail": f"'{tech}' was mentioned but no trace of it was found in the repository sample."})
    for tech in claims.get("documented_only", []):
        if not _already_flagged(tech):
            flags.append({"kind": "speech_vs_repo", "t": 0.0, "quote": "",
                          "detail": f"'{tech}' is named in the README but no dependency, file or import backs it up."})
    brief = dossier.get("brief", "") if dossier else ""
    dims_preview = aggregate(rubric, state["observations"])
    packet = build_packet(rubric, dims_preview, flags, claims, [s for s in state["screens"] if s.get("analysis") == "ok"],
                          state["asked"], brief)
    grades, errors = ([], ["no observations to grade"]) if not state["observations"] else \
        await council_grade(llm, cfg, packet, usage=usage)
    report = finalize(rubric, state["observations"], flags, claims, grades, errors,
                      duration_s=state.get("duration_s", 0), utterances=state.get("utterances", 0),
                      questions=len(state["asked"]), screens=len(state["screens"]),
                      dropped_unverified=state.get("dropped_unverified", 0))
    u = state.get("usage", {})
    secs = u.get("audio_seconds", 0.0)
    report["usage"] = {**u, "report_tokens": usage.prompt_tokens + usage.completion_tokens,
                       "stt_cost_estimate_usd": round(secs / 3600 * cfg.stt_price_per_hour, 4),
                       "note": "STT estimate uses the configured per-hour price; LLM usage is token counts only."}
    report["rubric"] = rubric.as_dict()
    report["session_id"] = meta.get("id")
    report["repo"] = ({k: dossier[k] for k in ("repo", "url", "branch", "description", "languages", "techs",
                                               "has_tests", "has_ci", "has_docker", "warnings", "brief")}
                      if dossier else None)
    report["questions"] = state["asked"]
    report["screens"] = [{k: s.get(k) for k in ("id", "t", "title", "summary", "analysis", "thumb")} for s in state["screens"]]
    return report


async def _write_pdf(store: Store, sid: str, report: dict, meta: dict) -> None:
    from .report import build_pdf
    d = store.session_dir(sid)
    thumbs = [(d / "thumbs" / s["thumb"], f"{s.get('title') or 'Screen'} (t={int(s['t'])}s)")
              for s in report["screens"] if s.get("thumb")]
    pdf = await asyncio.to_thread(build_pdf, report, meta, sid, thumbs)
    (d / "report.pdf").write_bytes(pdf)
