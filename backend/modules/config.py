"""
Configuration Module for NavAI Real-Time
Centralized settings from environment variables.
"""

import os
from dotenv import load_dotenv
from typing import Tuple, List

load_dotenv()


class Config:
    """Central configuration for the AI Interviewer."""
    
    # === API Keys ===
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # === Model Configuration ===
    # LLM for evaluation (Groq is fast + free)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    
    # Vision model (Groq Llama 4 Scout)
    VISION_MODEL: str = os.getenv("VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    
    # Deepgram model
    DEEPGRAM_MODEL: str = os.getenv("DEEPGRAM_MODEL", "nova-2")
    
    # TTS settings
    TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "edge")  # "edge", "openai", "elevenlabs"
    EDGE_TTS_VOICE: str = os.getenv("EDGE_TTS_VOICE", "en-US-GuyNeural")
    OPENAI_TTS_VOICE: str = os.getenv("OPENAI_TTS_VOICE", "alloy")
    
    # === Vision Processing ===
    # Minimum pixel difference (0-1) to trigger vision API
    VISION_CHANGE_THRESHOLD: float = float(os.getenv("VISION_CHANGE_THRESHOLD", "0.10"))
    
    # Minimum seconds between vision API calls
    VISION_MIN_INTERVAL: float = float(os.getenv("VISION_MIN_INTERVAL", "3.0"))
    
    # === Interview Settings ===
    MAX_SLIDES: int = int(os.getenv("MAX_SLIDES", "15"))
    REMEDIATION_THRESHOLD: int = int(os.getenv("REMEDIATION_THRESHOLD", "7"))
    
    # === Audio Settings ===
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    
    # === Server Settings ===
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    
    @classmethod
    def validate(cls) -> Tuple[bool, List[str]]:
        """Validate configuration."""
        errors = []
        
        if not cls.GROQ_API_KEY:
            errors.append("GROQ_API_KEY missing - Get FREE key at https://console.groq.com")
        
        if not cls.DEEPGRAM_API_KEY:
            errors.append("DEEPGRAM_API_KEY missing - Get FREE key at https://console.deepgram.com")
        
        if errors:
            print("⚠️  Configuration Errors:")
            for e in errors:
                print(f"   - {e}")
            return False, errors
        
        print("✅ Configuration valid")
        return True, []
    
    @classmethod
    def get_status(cls) -> dict:
        """Get configuration status for display."""
        return {
            "Groq LLM": "✅" if cls.GROQ_API_KEY else "❌",
            "Groq Vision": "✅" if cls.GROQ_API_KEY else "❌",
            "Deepgram STT": "✅" if cls.DEEPGRAM_API_KEY else "❌",
            "TTS": f"✅ {cls.TTS_PROVIDER}",
        }
