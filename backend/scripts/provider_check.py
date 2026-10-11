"""Verify your keys and model ids against the live providers, and print latency.

    cd backend && python scripts/provider_check.py

It makes one tiny call per configured model (chat, vision with a generated slide, JSON mode, speech-to-text on
one second of silence) and tells you which chain entries work, which model ids are retired, and what to put in
your .env. Cost: a few hundred tokens and one second of audio per entry.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.providers.llm import LLMClient  # noqa: E402
from app.providers.stt import STTClient  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.vision import describe, sample_slide_jpeg  # noqa: E402


async def main() -> int:
    cfg = Settings.from_env()
    keys = {p: cfg.provider_ready(p) for p in ("ollama", "groq", "openrouter")}
    print("Keys configured:", ", ".join(f"{p}={'yes' if ok else 'NO'}" for p, ok in keys.items()))
    if not any(keys.values()):
        print("No API key found. Copy backend/.env.example to backend/.env and fill it in.")
        return 2
    failures = 0
    async with httpx.AsyncClient(timeout=60) as http:
        llm, stt = LLMClient(cfg, http), STTClient(cfg, http)

        async def row(kind, provider, model, coro):
            nonlocal failures
            t0 = time.perf_counter()
            r = await coro
            ok = r.get("ok")
            failures += 0 if ok else 1
            detail = f"{r.get('latency_s', round(time.perf_counter() - t0, 2))}s" if ok else f"{r.get('kind')}: {r.get('message')}"
            print(f"  [{'OK ' if ok else 'FAIL'}] {kind:<8} {provider}:{model:<40} {detail}")

        print("\nInterviewer chain (LIVE_CHAIN)")
        for p, m in cfg.chain_available(cfg.live_chain):
            await row("chat", p, m, llm.ping(p, m))
        print("\nGrading council (COUNCIL_CHAIN)")
        for p, m in cfg.chain_available(cfg.council_chain):
            await row("chat", p, m, llm.ping(p, m))
        print("\nVision (VISION_CHAIN): describes a generated slide")
        for p, m in cfg.chain_available(cfg.vision_chain):
            one = Settings(**{**cfg.__dict__, "vision_chain": [(p, m)]})
            t0 = time.perf_counter()
            try:
                out = await describe(LLMClient(one, http), one, sample_slide_jpeg())
                techs = out.get("technologies")
                print(f"  [OK ] vision   {p}:{m:<40} {time.perf_counter() - t0:.2f}s  saw: {techs}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  [FAIL] vision   {p}:{m:<40} {str(e)[:100]}")
        print("\nSpeech-to-text (STT_CHAIN)")
        for p, m in cfg.chain_available(cfg.stt_chain):
            await row("stt", p, m, stt.ping(p, m))
    print("\nResult:", "all configured entries work" if not failures else f"{failures} entr{'y' if failures == 1 else 'ies'} failed; "
          "edit the *_CHAIN variables in .env to drop or replace them.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
