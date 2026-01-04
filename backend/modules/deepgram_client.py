"""
Deepgram Real-Time Streaming Client
Handles live audio transcription with VAD (Voice Activity Detection)

Key features:
- WebSocket streaming to Deepgram
- Interim and final transcript callbacks
- Speech start/end detection for interruption handling
- Automatic reconnection
"""

import asyncio
import json
from typing import Callable, Optional
import websockets
from .config import Config


class DeepgramStreamClient:
    """
    Real-time audio transcription using Deepgram WebSocket API.
    
    Usage:
        client = DeepgramStreamClient()
        client.on_interim = lambda text: print(f"Interim: {text}")
        client.on_final = lambda text: print(f"Final: {text}")
        await client.connect()
        await client.send_audio(audio_bytes)
        await client.disconnect()
    """
    
    DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
    
    def __init__(self):
        self.api_key = Config.DEEPGRAM_API_KEY
        self.model = Config.DEEPGRAM_MODEL
        self.sample_rate = Config.AUDIO_SAMPLE_RATE
        
        # WebSocket connection
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._is_connected = False
        
        # Callbacks
        self.on_interim: Optional[Callable[[str], asyncio.coroutine]] = None
        self.on_final: Optional[Callable[[str], asyncio.coroutine]] = None
        self.on_speech_started: Optional[Callable[[], asyncio.coroutine]] = None
        self.on_speech_ended: Optional[Callable[[], asyncio.coroutine]] = None
        
        # State
        self._is_speaking = False
    
    def _build_url(self) -> str:
        """Build Deepgram WebSocket URL with parameters."""
        params = [
            f"model={self.model}",
            f"sample_rate={self.sample_rate}",
            "encoding=linear16",
            "channels=1",
            "punctuate=true",
            "interim_results=true",
            "utterance_end_ms=1000",  # Detect end of speech
            "vad_events=true",  # Voice Activity Detection
            "smart_format=true",
        ]
        return f"{self.DEEPGRAM_WS_URL}?{'&'.join(params)}"
    
    async def connect(self):
        """Establish WebSocket connection to Deepgram."""
        if self._is_connected:
            return
        
        try:
            url = self._build_url()
            headers = {"Authorization": f"Token {self.api_key}"}
            
            self._ws = await websockets.connect(
                url,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10
            )
            
            self._is_connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            print("[Deepgram] Connected to streaming API")
            
        except Exception as e:
            print(f"[Deepgram] Connection error: {e}")
            raise
    
    async def disconnect(self):
        """Close WebSocket connection."""
        self._is_connected = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            # Send close message
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except:
                pass
        
        self._ws = None
        print("[Deepgram] Disconnected")
    
    async def send_audio(self, audio_bytes: bytes):
        """Send audio chunk to Deepgram."""
        if not self._is_connected or not self._ws:
            return
        
        try:
            await self._ws.send(audio_bytes)
        except Exception as e:
            print(f"[Deepgram] Send error: {e}")
            # Attempt reconnection
            await self._handle_disconnect()
    
    async def _receive_loop(self):
        """Process incoming messages from Deepgram."""
        try:
            async for message in self._ws:
                await self._handle_message(message)
        except websockets.ConnectionClosed:
            print("[Deepgram] Connection closed")
            await self._handle_disconnect()
        except Exception as e:
            print(f"[Deepgram] Receive error: {e}")
    
    async def _handle_message(self, message: str):
        """Parse and handle Deepgram response."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            
            if msg_type == "Results":
                await self._handle_transcript(data)
            
            elif msg_type == "SpeechStarted":
                if not self._is_speaking:
                    self._is_speaking = True
                    if self.on_speech_started:
                        await self.on_speech_started()
            
            elif msg_type == "UtteranceEnd":
                self._is_speaking = False
                if self.on_speech_ended:
                    await self.on_speech_ended()
            
            elif msg_type == "Metadata":
                print(f"[Deepgram] Session: {data.get('request_id', 'unknown')}")
            
            elif msg_type == "Error":
                print(f"[Deepgram] Error: {data.get('message', 'Unknown error')}")
        
        except json.JSONDecodeError:
            print(f"[Deepgram] Invalid JSON: {message[:100]}")
    
    async def _handle_transcript(self, data: dict):
        """Process transcript result."""
        channel = data.get("channel", {})
        alternatives = channel.get("alternatives", [])
        
        if not alternatives:
            return
        
        transcript = alternatives[0].get("transcript", "").strip()
        if not transcript:
            return
        
        is_final = data.get("is_final", False)
        speech_final = data.get("speech_final", False)
        
        if is_final or speech_final:
            # Final transcript - trigger response
            if self.on_final:
                await self.on_final(transcript)
        else:
            # Interim - update display
            if self.on_interim:
                await self.on_interim(transcript)
    
    async def _handle_disconnect(self):
        """Handle unexpected disconnection."""
        self._is_connected = False
        
        # Attempt reconnection after brief delay
        await asyncio.sleep(1)
        
        try:
            await self.connect()
            print("[Deepgram] Reconnected")
        except Exception as e:
            print(f"[Deepgram] Reconnection failed: {e}")
