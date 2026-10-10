"""Shared fixtures: a fake provider network (httpx.MockTransport) so no test touches the internet."""
from __future__ import annotations

import io
import json
import re
import struct
import sys
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import Settings  # noqa: E402


def pytest_runtest_logreport(report):
    """On GitHub Actions, surface failures as annotations (visible without downloading logs)."""
    import os
    if report.failed and os.getenv("GITHUB_ACTIONS"):
        text = (report.longreprtext or "")[-1200:]
        for raw, enc in (("%", "%25"), (chr(13), ""), (chr(10), "%0A")):
            text = text.replace(raw, enc)
        print(f"
::error title={report.nodeid}::{text}", flush=True)  # leading newline: pytest dots share the line


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(groq_api_key="gk", ollama_api_key="ok", openrouter_api_key="rk", github_token="",
                data_dir=tmp_path / "data", frontend_dist=tmp_path / "nodist", pause_s=0.3, min_ai_gap_s=0.0,
                min_words_to_ask=5, max_words_without_ai=60, vision_min_interval_s=0.0, council_size=2,
                retention_days=30)
    base.update(kw)
    return Settings(**base)


def wav_bytes(seconds: float = 1.5, rate: int = 16000) -> bytes:
    n = int(seconds * rate)
    return (b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", n * 2) + b"\x00\x00" * n)


def slide_jpeg(lines: list[str], dark: bool = False, size=(1280, 720), cursor: tuple[int, int] | None = None) -> bytes:
    bg, fg = ((30, 30, 30), (220, 220, 220)) if dark else ((255, 255, 255), (0, 0, 0))
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=44)
    y = 80
    for line in lines:
        d.text((80, y), line, fill=fg, font=font)
        y += 74
    if cursor:
        d.polygon([cursor, (cursor[0] + 14, cursor[1] + 20), (cursor[0] + 4, cursor[1] + 18)], fill=(0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


REPO_TREE = {
    "tree": [
        {"path": "README.md", "type": "blob"}, {"path": "requirements.txt", "type": "blob"},
        {"path": "Dockerfile", "type": "blob"}, {"path": "app/main.py", "type": "blob"},
        {"path": "app/routes.py", "type": "blob"}, {"path": "tests/test_api.py", "type": "blob"},
        {"path": ".github/workflows/ci.yml", "type": "blob"}, {"path": "node_modules/x/index.js", "type": "blob"},
    ],
    "truncated": False,
}
RAW = {
    "README.md": "# Shop API\nA FastAPI service for orders. Latency improved by 40% after batching.\n",
    "requirements.txt": "fastapi\nuvicorn\nsqlalchemy\n",
    "Dockerfile": "FROM python:3.12\nCMD uvicorn app.main:app\n",
    "app/main.py": "# entrypoint\nfrom fastapi import FastAPI\napp = FastAPI()\n",
    "app/routes.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
}


class FakeNetwork:
    """Routes requests to canned provider behaviour. `calls` records (host, path) for assertions."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.chat_fail_hosts: set[str] = set()
        self.stt_text = "We built a FastAPI service with Redis caching and Docker for deployment."
        self.turn_reply: dict | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        self.calls.append((host, path))
        if host == "api.github.com":
            if path.endswith("/git/trees/main"):
                return httpx.Response(200, json=REPO_TREE)
            if re.match(r"^/repos/[^/]+/private-repo$", path):
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"default_branch": "main", "description": "Order service"})
        if host == "raw.githubusercontent.com":
            rel = path.split("/main/", 1)[-1]
            return httpx.Response(200, text=RAW[rel]) if rel in RAW else httpx.Response(404)
        if path.endswith("/audio/transcriptions"):
            if host == "api.groq.com":
                return httpx.Response(200, json={"text": self.stt_text, "language": "en",
                                                 "segments": [{"no_speech_prob": 0.01, "avg_logprob": -0.2}]})
            return httpx.Response(200, json={"text": self.stt_text, "usage": {"seconds": 1.5}})
        if path.endswith("/chat/completions"):
            if host in self.chat_fail_hosts:
                return httpx.Response(429, headers={"retry-after": "3"}, json={"error": "rate limited"})
            body = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(self._chat(body))}}],
                                             "usage": {"prompt_tokens": 100, "completion_tokens": 40}})
        return httpx.Response(404)

    # --------------------------------------------------------------- chat behaviours
    def _chat(self, body: dict) -> dict:
        msgs = body["messages"]
        sys_txt = msgs[0]["content"] if isinstance(msgs[0]["content"], str) else ""
        user = msgs[-1]["content"]
        if isinstance(user, list):  # vision request
            return {"content_type": "slide", "title": "Architecture", "summary": "Diagram of API, Redis cache and Postgres",
                    "key_points": ["API", "cache"], "visible_text": ["Redis cache", "Postgres"],
                    "technologies": ["Redis", "PostgreSQL"], "numbers": ["99.9%"]}
        if "independent grader" in sys_txt:
            ids = re.findall(r"- (o\d+) \[([a-z_]+)\]", user)
            dims = {}
            for oid, dim in ids:
                dims.setdefault(dim, {"score": 3, "rationale": "Clear and specific.", "evidence": []})["evidence"].append(oid)
            first = ids[0][0] if ids else "o1"
            return {"dimensions": dims, "strengths": [{"text": "Explained the caching idea concretely.", "evidence": [first]}],
                    "growth": [{"text": "Show how failures are tested.", "evidence": [first, "o999"]},
                               {"text": "Invented point with a fake id.", "evidence": ["o404"]}],
                    "next_steps": ["Write one failure-case test.", "Draw the data flow."]}
        if self.turn_reply is not None:
            return self.turn_reply
        segs = re.findall(r"\[s(\d+)\] (.+)", user)
        sid, text = (int(segs[0][0]), segs[0][1]) if segs else (1, "")
        words = text.split()
        quote = " ".join(words[:6])
        return {
            "observations": [
                {"dimension": "technical_depth", "score": 3, "quote": quote, "source": "speech", "segment_ids": [sid]},
                {"dimension": "ownership", "score": 4, "quote": "I personally wrote every single kernel module",
                 "source": "speech", "segment_ids": [sid]},  # fabricated: must be dropped
            ],
            "flags": [],
            "action": "ask",
            "message": "Why did you choose Redis for caching? And how would you test it?",
            "target": "design_tradeoffs",
        }


@pytest.fixture
def net() -> FakeNetwork:
    return FakeNetwork()


@pytest.fixture
def http(net) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(net.handler))
