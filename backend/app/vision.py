"""Screen understanding: cheap change detection first, a vision model only when the slide really changed.

The old detector averaged the whole frame, so an ordinary slide-to-slide change scored 0.015-0.023
against a 0.10 threshold and almost never fired. This one compares a 16x9 grid of tiles, ignores the
mouse cursor and clocks (sub-tile changes), and waits for the picture to stop moving.
"""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageChops

from .providers.common import AllProvidersFailed, Usage
from .providers.llm import LLMClient, extract_json
from .settings import Settings
from .techlex import find_techs

GRID_W, GRID_H = 16, 9
SMALL = (160, 90)  # 10x10 px per tile


def _prepare(jpeg: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(jpeg))
    img.draft("L", (320, 180))  # fast JPEG decode at reduced size
    return img.convert("L").resize(SMALL, Image.BOX)


def changed_tiles(a: Image.Image, b: Image.Image, tile_threshold: float) -> int:
    diff = ImageChops.difference(a, b).resize((GRID_W, GRID_H), Image.BOX)
    limit = tile_threshold * 255
    return sum(1 for v in diff.getdata() if v > limit)


class ChangeDetector:
    """feed() returns True when the screen differs from the last analysed frame AND has settled."""

    def __init__(self, tile_threshold: float = 0.03, min_changed_tiles: int = 3):
        self.tile_threshold = tile_threshold
        self.min_changed_tiles = min_changed_tiles
        self._analyzed: Image.Image | None = None
        self._prev: Image.Image | None = None
        self._last: Image.Image | None = None

    def feed(self, jpeg: bytes) -> bool:
        cur = _prepare(jpeg)
        moving = self._prev is not None and changed_tiles(self._prev, cur, self.tile_threshold) > 1
        differs = self._analyzed is None or changed_tiles(self._analyzed, cur, self.tile_threshold) >= self.min_changed_tiles
        self._prev = self._last = cur
        return differs and not moving

    def commit(self) -> None:
        """Call when the last fed frame was actually sent for analysis. Not calling it (e.g. rate limited)
        keeps the frame pending, so a slide change is never silently forgotten."""
        self._analyzed = self._last

    def reset(self) -> None:
        self._analyzed = self._prev = self._last = None


def thumbnail(jpeg: bytes, width: int = 480) -> bytes:
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    h = max(1, round(img.height * width / img.width))
    buf = io.BytesIO()
    img.resize((width, h), Image.LANCZOS).save(buf, "JPEG", quality=70)
    return buf.getvalue()


VISION_PROMPT = """You see a screenshot of a student's screen during a live project defense.
Return ONLY a JSON object:
{"content_type": "slide|code|diagram|terminal|browser|ide|document|other",
 "title": "<short title of what is shown>",
 "summary": "<max 40 words: what is on screen>",
 "key_points": ["<max 5 short points actually visible>"],
 "visible_text": ["<max 6 short verbatim snippets, e.g. headings, function names, numbers>"],
 "technologies": ["<tools/frameworks/libraries visibly named>"],
 "numbers": ["<metrics or numeric claims visible, verbatim>"]}
Describe only what is visible. If the screen is unreadable, say so in "summary"."""


async def describe(llm: LLMClient, settings: Settings, jpeg: bytes, usage: Usage | None = None) -> dict:
    """Ask the vision chain what is on screen. Raises AllProvidersFailed; callers must not substitute text."""
    b64 = base64.b64encode(jpeg).decode()
    messages = [{"role": "user", "content": [
        {"type": "text", "text": VISION_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ]}]
    res = await llm.chat(settings.vision_chain, messages, purpose="screen analysis", json_mode=True,
                         max_tokens=500, temperature=0.1, timeout=45.0, usage=usage)
    try:
        data = extract_json(res.text)
    except ValueError:
        data = {"summary": res.text[:300]}
    text = " ".join([str(data.get("title", "")), str(data.get("summary", "")), *map(str, data.get("visible_text", []) or []),
                     *map(str, data.get("technologies", []) or [])])
    return {
        "content_type": str(data.get("content_type", "other"))[:20],
        "title": str(data.get("title", ""))[:120],
        "summary": str(data.get("summary", ""))[:400],
        "key_points": [str(x)[:140] for x in (data.get("key_points") or [])[:5]],
        "visible_text": [str(x)[:140] for x in (data.get("visible_text") or [])[:6]],
        "numbers": [str(x)[:60] for x in (data.get("numbers") or [])[:6]],
        "technologies": sorted(find_techs(text) | {str(t) for t in (data.get("technologies") or [])[:8]}),
        "model": f"{res.provider}:{res.model}",
    }


__all__ = ["ChangeDetector", "thumbnail", "describe", "AllProvidersFailed"]
