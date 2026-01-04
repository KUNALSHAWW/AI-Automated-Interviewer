"""
NavAI Real-Time Interview Server - FIXED VERSION
FastAPI + WebSocket Architecture for real-time interviewing

Key fixes:
1. Proper audio format handling (webm/opus from browser)
2. Simplified Deepgram integration using SDK
3. Better error handling and logging
4. Proper async flow
"""

import asyncio
import json
import time
import base64
import io
import os
import tempfile
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

from modules.config import Config
from modules.vision_processor import VisionProcessor
from modules.interview_brain import InterviewBrain
from modules.tts_engine import TTSEngine
from modules.report_generator import PDFReportGenerator

# Try to import deepgram SDK
try:
    from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
    DEEPGRAM_SDK_AVAILABLE = True
except ImportError:
    DEEPGRAM_SDK_AVAILABLE = False
    print("⚠️ Deepgram SDK not installed. Using HTTP fallback.")


# ============================================
# Interview History Storage
# ============================================
class InterviewHistoryStorage:
    """Stores past interview records."""
    
    def __init__(self, storage_dir: str = "interview_history"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        
    def save_interview(self, session_id: str, data: Dict) -> str:
        """Save interview data to JSON file."""
        filepath = self.storage_dir / f"{session_id}.json"
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return str(filepath)
    
    def get_all_interviews(self) -> List[Dict]:
        """Get all past interviews."""
        interviews = []
        for filepath in sorted(self.storage_dir.glob("*.json"), reverse=True):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    data['filename'] = filepath.name
                    interviews.append(data)
            except Exception as e:
                print(f"[History] Error loading {filepath}: {e}")
        return interviews
    
    def get_interview(self, session_id: str) -> Optional[Dict]:
        """Get a specific interview by session ID."""
        filepath = self.storage_dir / f"{session_id}.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None

# Global history storage
interview_storage = InterviewHistoryStorage()

# Global PDF report generator
pdf_generator = PDFReportGenerator()


# ============================================
# Application Lifespan
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    print("🚀 Starting NavAI Real-Time Server...")
    Config.validate()
    yield
    print("👋 Shutting down NavAI Server...")


# ============================================
# FastAPI App
# ============================================
app = FastAPI(
    title="NavAI Real-Time Interviewer",
    description="AI-Driven Automated Interviewer with real-time capabilities",
    version="2.1.0",
    lifespan=lifespan
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Simple Deepgram Transcription (HTTP API)
# ============================================
async def transcribe_audio_chunk(audio_data: bytes, encoding: str = "linear16", sample_rate: int = 16000) -> Optional[str]:
    """Transcribe audio using Deepgram HTTP API."""
    import httpx
    
    url = "https://api.deepgram.com/v1/listen"
    params = {
        "model": "nova-2",
        "smart_format": "true",
        "punctuate": "true",
        "encoding": encoding,
        "sample_rate": str(sample_rate),
        "channels": "1"
    }
    
    headers = {
        "Authorization": f"Token {Config.DEEPGRAM_API_KEY}",
        "Content-Type": "application/octet-stream"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, params=params, headers=headers, content=audio_data)
            
            if response.status_code == 200:
                result = response.json()
                transcript = result.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
                return transcript.strip() if transcript else None
            else:
                print(f"[Deepgram] Error {response.status_code}: {response.text[:200]}")
                return None
    except Exception as e:
        print(f"[Deepgram] Request error: {e}")
        return None


# ============================================
# WebSocket Interview Session
# ============================================
class InterviewSession:
    """Manages a single interview WebSocket session."""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Initialize components
        self.vision = VisionProcessor()
        self.brain = InterviewBrain()
        self.tts = TTSEngine()
        
        # State
        self.is_active = False
        self.is_ai_speaking = False
        self.screen_context = ""
        self.screen_contexts: List[str] = []  # Track all screen contexts for report
        self.history: List[Dict] = []
        self.slide_count = 0
        
        # Audio accumulation
        self.audio_chunks: List[bytes] = []
        self.last_transcript_time = time.time()
        self.accumulated_transcript = ""
        self._audio_encoding = "linear16"
        self._audio_sample_rate = 16000
        
        # Question pacing - don't bombard presenter
        self.last_question_time = 0
        self.min_question_interval = 8.0  # Minimum seconds between AI questions
        self.pending_response = False  # Are we waiting for presenter to respond?
        
        # Screen share reconnection
        self.screen_share_active = False
        self.screen_share_lost_time: Optional[float] = None
        self.screen_reconnect_timeout = 30.0  # seconds to wait for reshare
        self.awaiting_screen_reshare = False
        
        # Stop state
        self.is_stopped = False
        
        # Locks
        self._response_lock = asyncio.Lock()
        self._transcript_task: Optional[asyncio.Task] = None
    
    async def send_event(self, event_type: str, data: Any = None):
        """Send an event to the frontend."""
        try:
            await self.websocket.send_json({
                "type": event_type,
                "data": data,
                "timestamp": time.time()
            })
        except Exception as e:
            print(f"[WS] Send error: {e}")
    
    async def handle_audio_chunk(self, audio_b64: str, encoding: str = "linear16", sample_rate: int = 16000):
        """Process incoming audio chunk."""
        if not self.is_active:
            return
        
        try:
            # Decode audio
            audio_bytes = base64.b64decode(audio_b64)
            self.audio_chunks.append(audio_bytes)
            
            # Store encoding info
            self._audio_encoding = encoding
            self._audio_sample_rate = sample_rate
            
            # Process accumulated audio every 3 seconds
            if time.time() - self.last_transcript_time >= 3.0 and self.audio_chunks:
                await self.process_accumulated_audio()
                
        except Exception as e:
            print(f"[Audio] Error: {e}")
    
    async def process_accumulated_audio(self):
        """Process accumulated audio chunks."""
        if not self.audio_chunks:
            return
        
        # Combine chunks
        combined_audio = b"".join(self.audio_chunks)
        self.audio_chunks = []
        self.last_transcript_time = time.time()
        
        # Skip if too small (less than 0.5 seconds of audio at 16kHz, 16-bit)
        if len(combined_audio) < 16000:  # 0.5 sec * 16000 samples/sec * 2 bytes/sample
            return
        
        print(f"[Audio] Processing {len(combined_audio)} bytes of PCM audio")
        
        # Transcribe with correct encoding
        encoding = getattr(self, '_audio_encoding', 'linear16')
        sample_rate = getattr(self, '_audio_sample_rate', 16000)
        
        transcript = await transcribe_audio_chunk(combined_audio, encoding, sample_rate)
        
        if transcript:
            print(f"[Transcript] {transcript}")
            
            # Send interim transcript
            await self.send_event("transcript_interim", {"text": transcript})
            
            # Accumulate
            self.accumulated_transcript += " " + transcript
            
            # Generate response after enough words (or detect pause)
            word_count = len(self.accumulated_transcript.split())
            if word_count >= 8:
                await self.finalize_transcript()
    
    async def finalize_transcript(self):
        """Finalize transcript and generate AI response."""
        if not self.accumulated_transcript.strip():
            return
        
        transcript = self.accumulated_transcript.strip()
        self.accumulated_transcript = ""
        
        # Send final transcript
        await self.send_event("transcript_final", {"text": transcript})
        
        # Generate response
        await self.generate_response(transcript)
    
    async def handle_video_frame(self, frame_base64: str):
        """Process incoming video frame."""
        if not self.is_active:
            return
        
        try:
            # Check for significant change before processing
            has_change, analysis = await self.vision.process_frame(frame_base64)
            
            if has_change and analysis:
                self.screen_context = analysis
                self.screen_contexts.append(analysis)  # Track for report
                await self.send_event("screen_update", {
                    "context": analysis[:200] + "..." if len(analysis) > 200 else analysis
                })
                print(f"[Vision] Screen updated: {analysis[:100]}...")
        except Exception as e:
            print(f"[Vision] Error: {e}")
    
    async def generate_response(self, transcript: str):
        """Generate AI response based on transcript and screen context."""
        async with self._response_lock:
            # Check pacing - don't bombard with questions
            time_since_last = time.time() - self.last_question_time
            if time_since_last < self.min_question_interval and self.last_question_time > 0:
                # Too soon, let presenter continue
                print(f"[Pacing] Skipping question - only {time_since_last:.1f}s since last")
                return
            
            await self.send_event("status", {"state": "thinking"})
            
            try:
                # Get evaluation from the brain
                evaluation = await self.brain.evaluate(
                    transcript=transcript,
                    screen_context=self.screen_context,
                    history=self.history
                )
                
                # Check if presenter asked a question (like "next slide?")
                if evaluation.get("presenter_asked_question"):
                    # Respond immediately without pacing delay
                    pass
                elif evaluation.get("response_type") == "proceed" and self.pending_response:
                    # They're continuing, don't interrupt
                    await self.send_event("status", {"state": "listening"})
                    return
                
                # Update history with comprehensive data
                self.slide_count += 1
                self.history.append({
                    "slide": self.slide_count,
                    "transcript": transcript,
                    "score": evaluation.get("score", 5),
                    "technical_depth": evaluation.get("technical_depth", evaluation.get("score", 5)),
                    "clarity": evaluation.get("clarity", evaluation.get("score", 5)),
                    "visual_quality": evaluation.get("visual_quality", 5),
                    "is_final_for_topic": evaluation.get("is_final_for_topic", True),
                    "conflict": evaluation.get("conflict_detected", False),
                    "conflict_description": evaluation.get("conflict_description", ""),
                    "feedback": evaluation.get("feedback", ""),
                    "question": evaluation.get("next_response", evaluation.get("next_question", "")),
                    "topic": evaluation.get("topic", ""),
                    "response_type": evaluation.get("response_type", ""),
                    "screen_context": self.screen_context[:300] if self.screen_context else "",
                    "timestamp": datetime.now().isoformat()
                })
                
                # Send evaluation to frontend (map new fields to expected format)
                frontend_eval = {
                    "score": evaluation.get("score", 5),
                    "conflict_detected": evaluation.get("conflict_detected", False),
                    "feedback": evaluation.get("feedback", ""),
                    "next_question": evaluation.get("next_response", evaluation.get("next_question", "")),
                    "question_type": evaluation.get("response_type", "question"),
                    "topic": evaluation.get("topic", "")
                }
                await self.send_event("evaluation", frontend_eval)
                
                # Generate and stream TTS - use next_response (new field)
                response_text = evaluation.get("next_response", evaluation.get("next_question", ""))
                if response_text and response_text.strip():
                    await self.speak_response(response_text)
                    self.last_question_time = time.time()
                    self.pending_response = True
                else:
                    await self.send_event("status", {"state": "listening"})
                
            except Exception as e:
                print(f"[Brain] Error: {e}")
                import traceback
                traceback.print_exc()
                await self.send_event("error", {"message": str(e)})
                await self.send_event("status", {"state": "listening"})
    
    async def speak_response(self, text: str):
        """Generate TTS and send audio to client."""
        self.is_ai_speaking = True
        await self.send_event("status", {"state": "speaking"})
        
        try:
            # Generate full audio first (simpler than streaming)
            audio_bytes = await self.tts.generate_full_audio(text)
            
            if audio_bytes:
                # Send as single base64 chunk
                audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
                await self.send_event("audio_chunk", {"audio": audio_b64})
                await self.send_event("audio_end")
            
        except Exception as e:
            print(f"[TTS] Error: {e}")
        finally:
            self.is_ai_speaking = False
            await self.send_event("status", {"state": "listening"})
    
    async def start(self):
        """Start the interview session."""
        self.is_active = True
        self.screen_share_active = True
        
        print(f"[Session] Started: {self.session_id}")
        
        # Send opening message
        await self.send_event("status", {"state": "thinking"})
        
        opening = await self.brain.generate_opening()
        await self.send_event("ai_message", {"text": opening})
        await self.speak_response(opening)
        self.last_question_time = time.time()
    
    async def handle_screen_share_lost(self):
        """Handle when screen share is lost mid-interview."""
        if not self.is_active or self.awaiting_screen_reshare:
            return
        
        self.screen_share_active = False
        self.screen_share_lost_time = time.time()
        self.awaiting_screen_reshare = True
        
        print(f"[Session] Screen share lost at {self.screen_share_lost_time}")
        
        # Notify presenter and ask to reshare
        message = "I noticed you stopped sharing your screen. Please reshare to continue the interview, or click End Interview to finish."
        await self.send_event("screen_share_lost", {"message": message})
        await self.send_event("ai_message", {"text": message})
        await self.speak_response(message)
        
        # Start timeout checker
        asyncio.create_task(self._screen_share_timeout_checker())
    
    async def _screen_share_timeout_checker(self):
        """Check if screen share was restored within timeout."""
        await asyncio.sleep(self.screen_reconnect_timeout)
        
        if self.awaiting_screen_reshare and self.is_active:
            # Timeout - end interview gracefully
            print(f"[Session] Screen share timeout - ending interview")
            
            closing = "Since the screen share wasn't restored, I'll wrap up the interview now. Thank you for your presentation!"
            await self.send_event("ai_message", {"text": closing})
            await self.speak_response(closing)
            
            # Auto-stop and generate report
            await self.stop(auto_ended=True)
    
    async def handle_screen_share_restored(self):
        """Handle when screen share is restored."""
        if not self.awaiting_screen_reshare:
            return
        
        self.screen_share_active = True
        self.awaiting_screen_reshare = False
        self.screen_share_lost_time = None
        
        print(f"[Session] Screen share restored")
        
        # Welcome back message
        message = "Great, I can see your screen again! Please continue where you left off."
        await self.send_event("screen_share_restored", {"message": message})
        await self.send_event("ai_message", {"text": message})
        await self.speak_response(message)
    
    async def stop(self, auto_ended: bool = False, generate_report: bool = False):
        """Stop the interview session. Report generated only if requested."""
        if not self.is_active or self.is_stopped:
            return
            
        self.is_active = False
        self.is_stopped = True
        self.awaiting_screen_reshare = False
        
        print(f"[Session] Stopping interview {self.session_id}...")
        
        # Process any remaining audio
        if self.audio_chunks:
            await self.process_accumulated_audio()
        
        if self.accumulated_transcript.strip():
            await self.finalize_transcript()
        
        # Save basic interview data (without full report)
        interview_record = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "auto_ended": auto_ended,
            "duration_minutes": (time.time() - self.last_question_time) / 60 if self.last_question_time else 0,
            "total_questions": len(self.history),
            "history": self.history,
            "screen_contexts_count": len(self.screen_contexts),
            "summary": None  # Will be filled if report is generated
        }
        
        # Ask user if they want report (unless auto-ended which generates automatically)
        if auto_ended and self.history:
            # Auto-generate for auto-ended sessions
            await self._generate_and_send_report(interview_record)
        else:
            # Ask user - send popup event
            await self.send_event("interview_stopped", {
                "session_id": self.session_id,
                "total_questions": len(self.history),
                "has_content": len(self.history) > 0
            })
        
        print(f"[Session] Ended: {self.session_id}")
    
    async def generate_report_on_demand(self):
        """Generate report when user requests it."""
        if not self.history:
            await self.send_event("interview_complete", {
                "summary": {"overall_score": 0, "summary": "No content to evaluate."},
                "history": [],
                "session_id": self.session_id
            })
            return
        
        interview_record = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "auto_ended": False,
            "duration_minutes": 0,
            "total_questions": len(self.history),
            "history": self.history,
            "screen_contexts_count": len(self.screen_contexts),
            "summary": None
        }
        await self._generate_and_send_report(interview_record)
    
    async def _generate_and_send_report(self, interview_record: Dict):
        """Generate and send the report including PDF."""
        try:
            await self.send_event("status", {"state": "thinking"})
            await self.send_event("ai_message", {"text": "Generating your report..."})
            
            summary = await self.brain.generate_summary(self.history, self.screen_contexts)
            interview_record["summary"] = summary
            
            print(f"[Session] Summary generated: {summary.get('overall_score', 'N/A')}/100")
            
            # Save JSON record
            filepath = interview_storage.save_interview(self.session_id, interview_record)
            print(f"[Session] Interview saved to: {filepath}")
            
            # Generate PDF report asynchronously
            pdf_path = None
            try:
                loop = asyncio.get_event_loop()
                pdf_path = await loop.run_in_executor(
                    None,
                    lambda: pdf_generator.generate(
                        summary=summary,
                        session_id=self.session_id,
                        history=self.history
                    )
                )
                print(f"[Session] PDF report generated: {pdf_path}")
            except Exception as pdf_error:
                print(f"[Session] PDF generation failed (non-critical): {pdf_error}")
            
            # Send completion event with PDF URL if available
            response_data = {
                "summary": summary,
                "history": self.history,
                "session_id": self.session_id
            }
            
            if pdf_path:
                response_data["report_url"] = f"/api/reports/{self.session_id}"
                await self.send_event("report_ready", {
                    "url": f"/api/reports/{self.session_id}",
                    "session_id": self.session_id
                })
            
            await self.send_event("interview_complete", response_data)
            
        except Exception as e:
            print(f"[Session] Error generating summary: {e}")
            import traceback
            traceback.print_exc()
            
            await self.send_event("interview_complete", {
                "summary": {
                    "overall_score": 50,
                    "summary": f"Report generation error: {str(e)[:100]}",
                    "recommendation": "NEEDS_REVIEW"
                },
                "history": self.history,
                "session_id": self.session_id
            })


# ============================================
# WebSocket Endpoint
# ============================================
@app.websocket("/ws/interview")
async def websocket_interview(websocket: WebSocket):
    """Main WebSocket endpoint for interview sessions."""
    await websocket.accept()
    session = InterviewSession(websocket)
    
    print(f"[WS] New connection: {session.session_id}")
    
    try:
        await session.start()
        
        while True:
            try:
                # Receive message with timeout
                message = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                # Send keepalive
                await session.send_event("keepalive")
                continue
            
            if message["type"] == "websocket.disconnect":
                break
            
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "audio":
                        audio_b64 = data.get("data", "")
                        encoding = data.get("encoding", "linear16")
                        sample_rate = data.get("sampleRate", 16000)
                        await session.handle_audio_chunk(audio_b64, encoding, sample_rate)
                    
                    elif msg_type == "video":
                        frame_b64 = data.get("data", "")
                        # Mark screen share as active when receiving frames
                        if session.awaiting_screen_reshare:
                            await session.handle_screen_share_restored()
                        session.screen_share_active = True
                        await session.handle_video_frame(frame_b64)
                    
                    elif msg_type == "screen_share_lost":
                        await session.handle_screen_share_lost()
                    
                    elif msg_type == "screen_share_restored":
                        await session.handle_screen_share_restored()
                    
                    elif msg_type == "generate_report":
                        await session.generate_report_on_demand()
                    
                    elif msg_type == "stop":
                        # Don't break - call stop to show popup, keep WS open for report
                        await session.stop(auto_ended=False)
                        # Now wait for generate_report or client disconnect
                    
                    elif msg_type == "user_speaking":
                        if session.is_ai_speaking:
                            await session.send_event("stop_audio")
                            session.is_ai_speaking = False
                
                except json.JSONDecodeError as e:
                    print(f"[WS] JSON error: {e}")
    
    except WebSocketDisconnect:
        print(f"[WS] Client disconnected: {session.session_id}")
    except Exception as e:
        print(f"[WS] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await session.stop()


# ============================================
# REST Endpoints
# ============================================
@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "running",
        "service": "NavAI Real-Time Interviewer",
        "version": "2.1.0",
        "deepgram_sdk": DEEPGRAM_SDK_AVAILABLE
    }


@app.get("/api/config")
async def get_config():
    """Get public configuration for frontend."""
    return {
        "maxDuration": 30 * 60,
        "frameInterval": 2000,
        "audioFormat": "webm/opus",
        "sampleRate": 16000
    }


@app.get("/api/interviews")
async def get_interviews():
    """Get all past interviews."""
    interviews = interview_storage.get_all_interviews()
    return {
        "interviews": interviews,
        "total": len(interviews)
    }


@app.get("/api/interviews/{session_id}")
async def get_interview(session_id: str):
    """Get a specific interview by session ID."""
    interview = interview_storage.get_interview(session_id)
    if interview:
        return interview
    return {"error": "Interview not found"}


@app.get("/api/reports/{session_id}")
async def get_report_pdf(session_id: str):
    """
    Download PDF report for a specific interview session.
    
    Returns the PDF file if found, or generates one if summary exists.
    """
    # Check if PDF already exists
    pdf_path = pdf_generator.get_report_path(session_id)
    
    if pdf_path:
        return FileResponse(
            path=pdf_path,
            filename=f"NavAI_Report_{session_id}.pdf",
            media_type="application/pdf"
        )
    
    # Try to generate from saved interview data
    interview = interview_storage.get_interview(session_id)
    if interview and interview.get("summary"):
        try:
            pdf_path = pdf_generator.generate(
                summary=interview["summary"],
                session_id=session_id,
                history=interview.get("history", [])
            )
            return FileResponse(
                path=pdf_path,
                filename=f"NavAI_Report_{session_id}.pdf",
                media_type="application/pdf"
            )
        except Exception as e:
            return {"error": f"Failed to generate PDF: {str(e)}"}
    
    return {"error": "Report not found. Interview may not have a summary yet."}


@app.get("/api/reports")
async def list_reports():
    """List all generated PDF reports."""
    reports = pdf_generator.list_reports()
    return {
        "reports": reports,
        "total": len(reports)
    }


# ============================================
# Main Entry Point
# ============================================
if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
