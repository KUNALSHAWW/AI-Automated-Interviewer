"""Speech-to-text over HTTP.

Neither Ollama Cloud nor its OpenAI-compatible endpoint exposes transcription (docs.ollama.com,
2026-10), so STT goes to Groq Whisper first (free tier, 25 MB / 10 s minimum billing) and to
OpenRouter's /audio/transcriptions (paid, ~$0.012/h for whisper-large-v3-turbo) as fallback.
"""
from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass

import httpx

from ..settings import Settings
from .common import AllProvidersFailed, Breaker, ProviderError, Usage
from .llm import _http_error

# Whisper invents these on near-silence. Dropped when the clip is short or the model itself says "no speech".
_HALLUCINATIONS = {
    "thank you", "thank you.", "thanks for watching", "thanks for watching!", "you", "bye", "bye.",
    "thank you for watching", "please subscribe", ".", "so", "okay.", "uh", "um",
}
_WORD_RE = re.compile(r"\w+", re.U)


@dataclass
class STTResult:
    text: str
    provider: str
    model: str
    seconds: float
    language: str | None
    dropped: bool = False
    reason: str = ""


def wav_duration_s(wav: bytes) -> float:
    """Duration of a canonical 16-bit PCM WAV (44-byte header)."""
    if len(wav) < 44 or wav[:4] != b"RIFF":
        return 0.0
    byte_rate = int.from_bytes(wav[28:32], "little") or 32000
    return max(0.0, (len(wav) - 44) / byte_rate)


def looks_like_hallucination(text: str, seconds: float, no_speech_prob: float | None, avg_logprob: float | None) -> str:
    t = text.strip().lower()
    if not _WORD_RE.search(t):
        return "no words"
    if no_speech_prob is not None and no_speech_prob > 0.6 and (avg_logprob is None or avg_logprob < -0.8):
        return f"no_speech_prob={no_speech_prob:.2f}"
    if t in _HALLUCINATIONS and seconds < 3.0:
        return "stock phrase on a very short clip"
    return ""


class STTClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self.cfg = settings
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=8.0))
        self._owns_http = http is None
        self.breaker = Breaker()
        self.usage = Usage()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def transcribe(self, wav: bytes, *, language: str | None = None, prompt: str | None = None,
                         usage: Usage | None = None) -> STTResult:
        seconds = wav_duration_s(wav)
        errors: list[ProviderError] = []
        for provider, model in self.cfg.stt_chain:
            key = (provider, model)
            if not self.cfg.provider_ready(provider):
                errors.append(ProviderError(provider, model, "no_key", f"{provider.upper()}_API_KEY is not set"))
                continue
            if self.breaker.is_open(key):
                errors.append(ProviderError(provider, model, "circuit_open", "skipped after recent failures"))
                continue
            try:
                if provider == "groq":
                    res = await self._groq(model, wav, seconds, language, prompt)
                elif provider == "openrouter":
                    res = await self._openrouter(model, wav, seconds, language)
                else:
                    raise ProviderError(provider, model, "model", f"{provider} has no speech-to-text endpoint")
            except ProviderError as err:
                self.breaker.fail(key, err)
                errors.append(err)
                continue
            self.breaker.ok(key)
            self.usage.add_audio(provider, model, seconds)
            if usage is not None:
                usage.add_audio(provider, model, seconds)
            return res
        raise AllProvidersFailed("speech-to-text", errors)

    async def _groq(self, model, wav, seconds, language, prompt) -> STTResult:
        data = {"model": model, "response_format": "verbose_json", "temperature": "0"}
        if language and language != "auto":
            data["language"] = language
        if prompt:
            data["prompt"] = prompt[:800]  # API limit is 224 tokens; this stays safely below
        try:
            r = await self._http.post(
                f"{self.cfg.base_url('groq')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.cfg.groq_api_key}"},
                data=data, files={"file": ("utterance.wav", wav, "audio/wav")}, timeout=40.0)
        except httpx.TimeoutException:
            raise ProviderError("groq", model, "timeout", "no reply within 40s") from None
        except httpx.HTTPError as e:
            raise ProviderError("groq", model, "network", str(e) or e.__class__.__name__) from None
        if r.status_code >= 400:
            raise _http_error("groq", model, r, r.text[:300])
        try:
            body = r.json()
            text = (body.get("text") or "").strip()
        except ValueError:
            raise ProviderError("groq", model, "bad_response", r.text[:200]) from None
        segs = body.get("segments") or []
        nsp = max((s.get("no_speech_prob", 0.0) for s in segs), default=None) if segs else None
        alp = min((s.get("avg_logprob", 0.0) for s in segs), default=None) if segs else None
        reason = looks_like_hallucination(text, seconds, nsp, alp)
        return STTResult(text="" if reason else text, provider="groq", model=model, seconds=seconds,
                         language=body.get("language"), dropped=bool(reason), reason=reason)

    async def _openrouter(self, model, wav, seconds, language) -> STTResult:
        payload = {"model": model, "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"},
                   "temperature": 0}
        if language and language != "auto":
            payload["language"] = language
        try:
            r = await self._http.post(
                f"{self.cfg.base_url('openrouter')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.cfg.openrouter_api_key}", "X-Title": "NavAI Viva"},
                json=payload, timeout=45.0)
        except httpx.TimeoutException:
            raise ProviderError("openrouter", model, "timeout", "no reply within 45s") from None
        except httpx.HTTPError as e:
            raise ProviderError("openrouter", model, "network", str(e) or e.__class__.__name__) from None
        if r.status_code >= 400:
            raise _http_error("openrouter", model, r, r.text[:300])
        try:
            text = (r.json().get("text") or "").strip()
        except ValueError:
            raise ProviderError("openrouter", model, "bad_response", r.text[:200]) from None
        reason = looks_like_hallucination(text, seconds, None, None)
        return STTResult(text="" if reason else text, provider="openrouter", model=model, seconds=seconds,
                         language=language, dropped=bool(reason), reason=reason)

    async def ping(self, provider: str, model: str) -> dict:
        """Transcribe one second of silence just to prove auth + model id work."""
        import struct
        n = 16000
        wav = (b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
               + b"data" + struct.pack("<I", n * 2) + b"\x00\x00" * n)
        t0 = time.perf_counter()
        try:
            if provider == "groq":
                await self._groq(model, wav, 1.0, "en", None)
            elif provider == "openrouter":
                await self._openrouter(model, wav, 1.0, "en")
            else:
                return {"ok": False, "provider": provider, "model": model, "kind": "model",
                        "message": "provider has no speech-to-text endpoint"}
            return {"ok": True, "latency_s": round(time.perf_counter() - t0, 2)}
        except ProviderError as e:
            return {"ok": False, "latency_s": round(time.perf_counter() - t0, 2), **e.public()}
