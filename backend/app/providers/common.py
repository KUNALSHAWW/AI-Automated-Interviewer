"""Shared provider plumbing: typed errors, circuit breaker, usage accounting."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


class ProviderError(Exception):
    """One provider/model failed. `kind` is one of: no_key, circuit_open, auth, rate, model,
    timeout, network, server, bad_response, bad_request."""

    def __init__(self, provider: str, model: str, kind: str, message: str, status: int | None = None,
                 retry_after: float | None = None):
        super().__init__(f"{provider}:{model} {kind}: {message}")
        self.provider, self.model, self.kind, self.message = provider, model, kind, message
        self.status, self.retry_after = status, retry_after

    def public(self) -> dict:
        return {"provider": self.provider, "model": self.model, "kind": self.kind, "message": self.message[:200]}


class AllProvidersFailed(Exception):
    """Every entry of a chain failed. Callers must surface this; never invent a result."""

    def __init__(self, purpose: str, errors: list[ProviderError]):
        self.purpose, self.errors = purpose, errors
        detail = "; ".join(f"{e.provider}:{e.model} {e.kind}" for e in errors) or "no provider configured"
        super().__init__(f"{purpose}: all providers failed ({detail})")


@dataclass
class _Circuit:
    fails: int = 0
    open_until: float = 0.0
    last_error: str = ""
    last_ok: float = 0.0


class Breaker:
    """Trips a (provider, model) pair after repeated failures so a dead model costs one call, not one per turn."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._state: dict[tuple[str, str], _Circuit] = defaultdict(_Circuit)

    def is_open(self, key: tuple[str, str]) -> bool:
        return self._state[key].open_until > self._clock()

    def ok(self, key: tuple[str, str]) -> None:
        c = self._state[key]
        c.fails, c.open_until, c.last_error, c.last_ok = 0, 0.0, "", time.time()

    def fail(self, key: tuple[str, str], err: ProviderError) -> None:
        c = self._state[key]
        c.fails += 1
        c.last_error = f"{err.kind}: {err.message[:120]}"
        if err.kind == "auth":
            c.open_until = self._clock() + 600  # a wrong key stays wrong
        elif err.kind == "model":
            c.open_until = self._clock() + 900  # retired / misspelt model id
        elif err.kind == "rate":
            c.open_until = self._clock() + min(max(err.retry_after or 20.0, 5.0), 60.0)
        elif c.fails >= 3:
            c.open_until = self._clock() + 60

    def snapshot(self) -> dict:
        now = self._clock()
        return {
            f"{p}:{m}": {
                "fails": c.fails,
                "open": c.open_until > now,
                "last_error": c.last_error,
                "last_ok": c.last_ok or None,
            }
            for (p, m), c in self._state.items()
        }


@dataclass
class Usage:
    """Per-process counters. Sessions keep their own copy for the report."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    audio_seconds: float = 0.0
    by_model: dict = field(default_factory=lambda: defaultdict(lambda: {"calls": 0, "tokens": 0}))

    def add_chat(self, provider: str, model: str, usage: dict | None) -> None:
        usage = usage or {}
        p, c = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        self.prompt_tokens += p
        self.completion_tokens += c
        self.calls += 1
        slot = self.by_model[f"{provider}:{model}"]
        slot["calls"] += 1
        slot["tokens"] += p + c

    def add_audio(self, provider: str, model: str, seconds: float) -> None:
        self.audio_seconds += seconds
        slot = self.by_model[f"{provider}:{model}"]
        slot["calls"] += 1

    def as_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "llm_calls": self.calls,
            "audio_seconds": round(self.audio_seconds, 1),
            "by_model": {k: dict(v) for k, v in self.by_model.items()},
        }
