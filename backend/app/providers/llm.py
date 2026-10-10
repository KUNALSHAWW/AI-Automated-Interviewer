"""OpenAI-compatible chat client with provider fallback chains.

Ollama Cloud (https://ollama.com/v1), Groq (https://api.groq.com/openai/v1) and OpenRouter
(https://openrouter.ai/api/v1) all speak the same /chat/completions dialect, so one httpx client
covers all three. Failures are typed and surfaced; there is never a canned answer.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx

from ..settings import Settings
from .common import AllProvidersFailed, Breaker, ProviderError, Usage

_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    latency_s: float
    usage: dict


class LLMClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self.cfg = settings
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=8.0))
        self._owns_http = http is None
        self.breaker = Breaker()
        self.usage = Usage()
        self._no_json_mode: set[tuple[str, str]] = set()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # ------------------------------------------------------------------ public
    async def chat(
        self,
        chain: list[tuple[str, str]],
        messages: list[dict],
        *,
        purpose: str,
        json_mode: bool = False,
        max_tokens: int = 700,
        temperature: float = 0.2,
        timeout: float = 30.0,
        usage: Usage | None = None,
    ) -> ChatResult:
        errors: list[ProviderError] = []
        for provider, model in chain:
            key = (provider, model)
            if not self.cfg.provider_ready(provider):
                errors.append(ProviderError(provider, model, "no_key", f"{provider.upper()}_API_KEY is not set"))
                continue
            if self.breaker.is_open(key):
                errors.append(ProviderError(provider, model, "circuit_open", "skipped after recent failures"))
                continue
            try:
                res = await self._call(provider, model, messages, json_mode, max_tokens, temperature, timeout)
            except ProviderError as err:
                self.breaker.fail(key, err)
                errors.append(err)
                continue
            self.breaker.ok(key)
            self.usage.add_chat(provider, model, res.usage)
            if usage is not None:
                usage.add_chat(provider, model, res.usage)
            return res
        raise AllProvidersFailed(purpose, errors)

    async def ping(self, provider: str, model: str) -> dict:
        """One tiny completion; used by /api/health/deep and scripts/provider_check.py."""
        t0 = time.perf_counter()
        try:
            res = await self._call(provider, model, [{"role": "user", "content": "Reply with the single word: ok"}],
                                   False, 16, 0.0, 20.0)
            return {"ok": True, "latency_s": round(res.latency_s, 2), "reply": res.text[:40]}
        except ProviderError as e:
            return {"ok": False, "latency_s": round(time.perf_counter() - t0, 2), **e.public()}

    # ----------------------------------------------------------------- private
    async def _call(self, provider, model, messages, json_mode, max_tokens, temperature, timeout) -> ChatResult:
        key = (provider, model)
        use_json = json_mode and key not in self._no_json_mode
        payload: dict = {"model": model, "messages": messages, "temperature": temperature,
                         "max_tokens": max_tokens, "stream": False}
        if use_json:
            payload["response_format"] = {"type": "json_object"}
        if provider == "groq" and model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"  # keep live turns fast; gpt-oss otherwise burns tokens thinking
        headers = {"Content-Type": "application/json"}
        api_key = self.cfg.api_key(provider)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if provider == "openrouter":
            headers["X-Title"] = "NavAI Viva"

        t0 = time.perf_counter()
        try:
            r = await self._http.post(f"{self.cfg.base_url(provider)}/chat/completions", json=payload,
                                      headers=headers, timeout=timeout)
        except httpx.TimeoutException:
            raise ProviderError(provider, model, "timeout", f"no reply within {timeout:.0f}s") from None
        except httpx.HTTPError as e:
            raise ProviderError(provider, model, "network", str(e) or e.__class__.__name__) from None

        if r.status_code >= 400:
            body = r.text[:400]
            if r.status_code == 400 and use_json and ("response_format" in body or "json" in body.lower()):
                self._no_json_mode.add(key)  # this model rejects JSON mode; fall back to prompt-only JSON
                return await self._call(provider, model, messages, json_mode, max_tokens, temperature, timeout)
            raise _http_error(provider, model, r, body)

        try:
            data = r.json()
            text = data["choices"][0]["message"].get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError(provider, model, "bad_response", f"unexpected body: {r.text[:200]}") from None
        text = _THINK_RE.sub("", text).strip()
        if not text:
            raise ProviderError(provider, model, "bad_response",
                                "empty completion (model may have spent max_tokens on reasoning)")
        return ChatResult(text=text, provider=provider, model=model, latency_s=time.perf_counter() - t0,
                          usage=data.get("usage") or {})


def _http_error(provider: str, model: str, r: httpx.Response, body: str) -> ProviderError:
    s = r.status_code
    if s in (401, 403):
        return ProviderError(provider, model, "auth", f"HTTP {s}: key rejected or not allowed", s)
    if s == 404:
        return ProviderError(provider, model, "model", f"HTTP 404: model not found or retired ({body[:120]})", s)
    if s == 429:
        try:
            ra = float(r.headers.get("retry-after", ""))
        except ValueError:
            ra = None
        return ProviderError(provider, model, "rate", "HTTP 429: rate limited", s, retry_after=ra)
    if s >= 500:
        return ProviderError(provider, model, "server", f"HTTP {s}: {body[:120]}", s)
    return ProviderError(provider, model, "bad_request", f"HTTP {s}: {body[:160]}", s)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (handles ```json fences and chatter)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model reply")
    return json.loads(text[start:end + 1])
