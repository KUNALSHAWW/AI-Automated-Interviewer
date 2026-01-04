"""
TTS Engine Module
Text-to-Speech with streaming support for low latency.

Supports multiple providers:
- Edge TTS (Free, good quality)
- OpenAI TTS (Paid, excellent quality)
- ElevenLabs (Paid, best quality)
"""

import asyncio
import io
import os
import tempfile
from typing import AsyncGenerator
import edge_tts

from .config import Config


class TTSEngine:
    """
    Text-to-Speech engine with streaming support.
    
    Usage:
        engine = TTSEngine()
        async for chunk in engine.stream_speech("Hello world"):
            # Send chunk to client
            pass
    """
    
    def __init__(self):
        self.provider = Config.TTS_PROVIDER
        self.edge_voice = Config.EDGE_TTS_VOICE
        self.openai_voice = Config.OPENAI_TTS_VOICE
    
    async def stream_speech(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Generate speech audio and yield chunks for streaming.
        
        Args:
            text: Text to convert to speech
            
        Yields:
            Audio chunks (MP3 format)
        """
        if self.provider == "openai":
            async for chunk in self._stream_openai(text):
                yield chunk
        else:
            # Default to Edge TTS (free)
            async for chunk in self._stream_edge_tts(text):
                yield chunk
    
    async def _stream_edge_tts(self, text: str) -> AsyncGenerator[bytes, None]:
        """Stream using Edge TTS (Microsoft)."""
        try:
            communicate = edge_tts.Communicate(text, self.edge_voice)
            
            # Collect all chunks
            audio_data = io.BytesIO()
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])
                    
                    # Yield in larger chunks for efficiency
                    if audio_data.tell() >= 4096:
                        audio_data.seek(0)
                        yield audio_data.read()
                        audio_data = io.BytesIO()
            
            # Yield remaining data
            if audio_data.tell() > 0:
                audio_data.seek(0)
                yield audio_data.read()
                
        except Exception as e:
            print(f"[TTS] Edge TTS error: {e}")
    
    async def _stream_openai(self, text: str) -> AsyncGenerator[bytes, None]:
        """Stream using OpenAI TTS API."""
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
            
            response = await client.audio.speech.create(
                model="tts-1",
                voice=self.openai_voice,
                input=text,
                response_format="mp3"
            )
            
            # OpenAI returns full audio, yield in chunks
            audio_bytes = response.content
            chunk_size = 4096
            
            for i in range(0, len(audio_bytes), chunk_size):
                yield audio_bytes[i:i+chunk_size]
                
        except ImportError:
            print("[TTS] OpenAI package not installed, falling back to Edge TTS")
            async for chunk in self._stream_edge_tts(text):
                yield chunk
        except Exception as e:
            print(f"[TTS] OpenAI error: {e}")
    
    async def generate_full_audio(self, text: str) -> bytes:
        """
        Generate complete audio file (non-streaming).
        
        Args:
            text: Text to convert
            
        Returns:
            Complete audio data as bytes
        """
        chunks = []
        async for chunk in self.stream_speech(text):
            chunks.append(chunk)
        return b"".join(chunks)
