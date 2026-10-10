"""Per-turn evaluation: decide whether to speak, what to ask, and which rubric evidence was shown.

The model returns JSON that is validated with pydantic. Every observation must carry a quote that is
verified against the transcript/screen by code (app.evidence); unverifiable observations are dropped,
never "rounded up" to a default score.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .dossier import Dossier
from .evidence import quote_supported
from .pacing import sanitize_question
from .providers.common import Usage
from .providers.llm import LLMClient, extract_json
from .rubrics import Rubric
from .settings import Settings

LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari script)", "auto": "the language the presenter is using: English, or Hinglish "
              "(Hindi written in Latin script) if they mix Hindi and English"}


class Observation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dimension: str
    score: int = Field(ge=0, le=4)
    quote: str
    source: Literal["speech", "screen"] = "speech"
    segment_ids: list[int] = Field(default_factory=list)
    note: str = ""

    @field_validator("score", mode="before")
    @classmethod
    def _round(cls, v):  # models sometimes answer 2.5 or "3"
        return max(0, min(4, int(round(float(v)))))


class Flag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: Literal["speech_vs_screen", "speech_vs_repo", "screen_vs_repo", "vague", "contradiction"] = "vague"
    detail: str
    quote: str = ""


class TurnEval(BaseModel):
    model_config = ConfigDict(extra="ignore")
    observations: list[Observation] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    action: Literal["ask", "acknowledge", "wait"] = "wait"
    message: str = ""
    target: str = ""


class EvaluationError(Exception):
    """The model never produced a valid evaluation. The session shows a warning; nothing is invented."""


@dataclass
class Segment:
    id: int
    text: str
    t: float  # seconds from interview start


@dataclass
class TurnContext:
    rubric: Rubric
    segments: list[Segment]
    language: str = "en"
    dossier: Dossier | None = None
    screen: dict | None = None
    claim_check: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)       # dim id -> verified observation count
    asked: list[str] = field(default_factory=list)
    probe_topics: list[str] = field(default_factory=list)
    invited: bool = False
    force_ask: bool = False


@dataclass
class TurnResult:
    action: str
    message: str
    target: str
    observations: list[dict]
    flags: list[dict]
    dropped: int
    fixes: list[str]
    model: str
    latency_s: float


SYSTEM_PROMPT = """You are Nova, a calm, fair technical interviewer running a short oral defense of a student's own project.
You get repository facts, what is on screen, and the presenter's latest words as numbered segments like [s12].

Rules
1. Ask exactly ONE question: a single plain sentence under 25 words. No lists, no "and also", no scores.
2. Ground it in something the presenter said, showed on screen, or that the repository contains.
3. Prefer, in order: a listed mismatch or unverified claim; a rubric dimension with no evidence yet; one follow-up on a vague answer.
4. Do not coach the answer and do not reveal scores. Be neutral and encouraging.
5. Score only what the presenter demonstrated in THIS turn, 0-4 using the anchors. Every score needs a quote of at least
   4 words copied VERBATIM from the segments (source "speech") or from the screen text (source "screen"), plus segment ids.
   If nothing was demonstrated return no observations.
6. If the presenter is mid-thought or the text is too short to judge, set action "wait".
7. "acknowledge" is a short neutral reply (no question) when the presenter asked you something procedural.

Reply with JSON only:
{"observations":[{"dimension":"<rubric id>","score":0-4,"quote":"<verbatim>","source":"speech|screen","segment_ids":[12],"note":"<max 15 words>"}],
 "flags":[{"kind":"speech_vs_screen|speech_vs_repo|screen_vs_repo|vague|contradiction","detail":"<max 25 words>","quote":"<verbatim or empty>"}],
 "action":"ask|acknowledge|wait","message":"<your single question or acknowledgement>","target":"<dimension id or topic>"}"""


def build_user_prompt(ctx: TurnContext) -> str:
    parts = []
    parts.append("RUBRIC (score 0-4; anchors for 0 / 2 / 4)\n" + "\n".join(
        f"- {d.id}: {d.label}. 0={d.anchors[0]}; 2={d.anchors[1]}; 4={d.anchors[2]}" for d in ctx.rubric.dimensions))
    parts.append("REPOSITORY\n" + (ctx.dossier.prompt_block() if ctx.dossier else
                                   "No repository was provided. Do not make claims about the code."))
    if ctx.screen:
        s = ctx.screen
        parts.append("ON SCREEN NOW\n"
                     f"type={s.get('content_type')}; title={s.get('title')}\nsummary={s.get('summary')}\n"
                     f"visible_text={json.dumps(s.get('visible_text', []), ensure_ascii=False)}\n"
                     f"technologies={s.get('technologies', [])}; numbers={s.get('numbers', [])}")
    else:
        parts.append("ON SCREEN NOW\nNo screen analysis available (screen share off, or analysis failed). Do not guess.")
    cc = ctx.claim_check or {}
    checks = []
    if cc.get("not_found"):
        checks.append("Technologies the presenter named that were NOT found in repository evidence: " + ", ".join(cc["not_found"]))
    if cc.get("unverified_metrics"):
        checks.append("Numeric claims with no support in README or screen: " + ", ".join(cc["unverified_metrics"]))
    if checks:
        parts.append("AUTOMATED CHECKS (hints, not proof; the repository sample may be incomplete)\n" + "\n".join(checks))
    parts.append("COVERAGE (verified observations per dimension)\n" + ", ".join(
        f"{d}={ctx.coverage.get(d, 0)}" for d in ctx.rubric.dim_ids()))
    if ctx.probe_topics:
        parts.append("UNUSED PROBE TOPICS\n" + "\n".join(f"- {t}" for t in ctx.probe_topics[:3]))
    if ctx.asked:
        parts.append("ALREADY ASKED (do not repeat)\n" + "\n".join(f"- {q}" for q in ctx.asked[-5:]))
    parts.append("PRESENTER SEGMENTS SINCE YOUR LAST TURN\n" + "\n".join(f"[s{s.id}] {s.text}" for s in ctx.segments))
    lang = LANG_NAMES.get(ctx.language, LANG_NAMES["auto"])
    tail = f"Write \"message\" in {lang}. JSON keys stay in English."
    if ctx.invited:
        tail += " The presenter just invited questions, so action must not be \"wait\"."
    if ctx.force_ask:
        tail += " The presenter has spoken for a long time; action must be \"ask\"."
    parts.append(tail)
    return "\n\n".join(parts)


def verify_observations(obs: list[Observation], ctx: TurnContext) -> tuple[list[dict], int]:
    """Keep observations whose dimension exists and whose quote is found. Returns (kept, dropped_count)."""
    by_id = {s.id: s for s in ctx.segments}
    all_speech = [s.text for s in ctx.segments]
    screen_texts: list[str] = []
    if ctx.screen:
        screen_texts = [ctx.screen.get("summary", ""), ctx.screen.get("title", ""),
                        *ctx.screen.get("visible_text", []), *ctx.screen.get("key_points", [])]
    kept, dropped = [], 0
    for o in obs:
        if ctx.rubric.get(o.dimension) is None:
            dropped += 1
            continue
        if o.source == "screen":
            pool = screen_texts
        else:
            cited = [by_id[i].text for i in o.segment_ids if i in by_id]
            pool = cited or all_speech
        if not quote_supported(o.quote, pool):
            dropped += 1
            continue
        t = min((by_id[i].t for i in o.segment_ids if i in by_id), default=ctx.segments[-1].t if ctx.segments else 0.0)
        kept.append({"dimension": o.dimension, "score": o.score, "quote": o.quote.strip(), "source": o.source,
                     "segment_ids": [i for i in o.segment_ids if i in by_id], "note": o.note[:120], "t": round(t, 1)})
    return kept, dropped


async def evaluate_turn(llm: LLMClient, settings: Settings, ctx: TurnContext, usage: Usage | None = None) -> TurnResult:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": build_user_prompt(ctx)}]
    last_err = ""
    for attempt in range(2):
        msgs = messages if attempt == 0 else messages + [
            {"role": "user", "content": f"Your previous reply was invalid ({last_err}). Reply with the JSON object only."}]
        res = await llm.chat(settings.live_chain, msgs, purpose="turn evaluation", json_mode=True,
                             max_tokens=1400, temperature=0.2, timeout=40.0, usage=usage)
        try:
            ev = TurnEval.model_validate(extract_json(res.text))
        except (ValueError, ValidationError) as e:
            last_err = str(e)[:160]
            continue
        kept, dropped = verify_observations(ev.observations, ctx)
        message, fixes = ev.message, []
        action = ev.action
        if action == "ask":
            message, fixes = sanitize_question(message)
            if not message.endswith("?"):
                action = "wait" if not message else "acknowledge"
        if ctx.invited and action == "wait" and message:
            action = "acknowledge"
        return TurnResult(action=action, message=message, target=ev.target[:60],
                          observations=kept, flags=[f.model_dump() for f in ev.flags[:4]],
                          dropped=dropped, fixes=fixes, model=f"{res.provider}:{res.model}", latency_s=res.latency_s)
    raise EvaluationError(f"model did not return valid JSON twice: {last_err}")
