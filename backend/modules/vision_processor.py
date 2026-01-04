"""
Vision Processor Module
Handles screen frame analysis with intelligent change detection.

Key features:
- SSIM-based frame difference detection (no API call unless scene changes)
- Groq Vision API integration for content extraction
- Rate limiting and error handling
"""

import asyncio
import base64
import io
import time
from typing import Tuple, Optional
from PIL import Image
import numpy as np
from groq import Groq

from .config import Config


class VisionProcessor:
    """
    Intelligent vision processing with change detection.
    
    Only sends frames to the Vision API when:
    1. The frame has changed significantly from the last analyzed frame
    2. Enough time has passed since the last API call
    
    This dramatically reduces API costs and latency.
    """
    
    VISION_PROMPT = """Analyze this screenshot from a technical presentation.

Extract and return concisely:
1. **Content Type**: Code, Diagram, Slide, Terminal, IDE, etc.
2. **Technical Details**: 
   - If code: language, key functions, logic flow, complexity
   - If diagram: components, relationships, data flow
   - If slide: bullet points, key claims, numbers
3. **Key Data Points**: Any metrics, percentages, or quantitative claims
4. **Main Topic**: Primary subject being shown

Be precise and factual. Output will verify the presenter's explanation.

Format:
TYPE: <type>
DETAILS: <technical details>
DATA: <numbers/metrics if any>
TOPIC: <main topic>"""

    def __init__(self):
        self.groq_client = Groq(api_key=Config.GROQ_API_KEY)
        
        # Frame comparison state
        self._last_frame: Optional[np.ndarray] = None
        self._last_analysis: str = ""
        self._last_api_call: float = 0
        
        # Configuration
        self.change_threshold = Config.VISION_CHANGE_THRESHOLD
        self.min_interval = Config.VISION_MIN_INTERVAL
    
    async def process_frame(self, frame_base64: str) -> Tuple[bool, Optional[str]]:
        """
        Process a video frame, only calling API if scene changed.
        
        Args:
            frame_base64: Base64-encoded frame image
            
        Returns:
            Tuple of (has_significant_change, analysis_text or None)
        """
        try:
            # Decode frame
            frame_bytes = base64.b64decode(frame_base64)
            image = Image.open(io.BytesIO(frame_bytes))
            
            # Convert to numpy for comparison
            frame_array = np.array(image.convert('RGB'))
            
            # Check if frame has changed significantly
            has_change = self._detect_change(frame_array)
            
            if not has_change:
                return False, None
            
            # Check rate limiting
            now = time.time()
            if now - self._last_api_call < self.min_interval:
                return False, None
            
            # Call Vision API
            analysis = await self._analyze_frame(image)
            
            # Update state
            self._last_frame = frame_array
            self._last_analysis = analysis
            self._last_api_call = now
            
            return True, analysis
            
        except Exception as e:
            print(f"[Vision] Processing error: {e}")
            return False, None
    
    def _detect_change(self, current_frame: np.ndarray) -> bool:
        """
        Detect if the current frame is significantly different from the last.
        Uses simple pixel difference ratio (fast and effective for slides).
        
        Args:
            current_frame: Current frame as numpy array
            
        Returns:
            True if frame has changed significantly
        """
        if self._last_frame is None:
            return True
        
        try:
            # Resize both frames to same size for comparison
            h, w = 180, 320  # Small size for fast comparison
            
            # Resize current frame
            current_small = np.array(
                Image.fromarray(current_frame).resize((w, h), Image.LANCZOS)
            )
            
            # Resize last frame
            last_small = np.array(
                Image.fromarray(self._last_frame).resize((w, h), Image.LANCZOS)
            )
            
            # Calculate pixel-wise difference
            diff = np.abs(current_small.astype(float) - last_small.astype(float))
            
            # Normalize to 0-1 range
            diff_ratio = np.mean(diff) / 255.0
            
            # Check if difference exceeds threshold
            return diff_ratio > self.change_threshold
            
        except Exception as e:
            print(f"[Vision] Change detection error: {e}")
            return True  # Assume change on error
    
    async def _analyze_frame(self, image: Image.Image) -> str:
        """
        Send frame to Groq Vision API for analysis.
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            Analysis text
        """
        try:
            # Convert to base64
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=80)
            image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Call Groq Vision API (runs in thread pool to not block)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.groq_client.chat.completions.create(
                    model=Config.VISION_MODEL,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                            }
                        ]
                    }],
                    temperature=0.1,
                    max_tokens=500
                )
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            error_str = str(e).lower()
            
            if '429' in str(e) or 'rate' in error_str:
                print("[Vision] Rate limited - will retry later")
                return self._last_analysis  # Return cached analysis
            
            print(f"[Vision] API error: {e}")
            return "Screen content analysis temporarily unavailable"
    
    def get_current_context(self) -> str:
        """Get the most recent screen analysis."""
        return self._last_analysis or "No screen content analyzed yet"
    
    def reset(self):
        """Reset the processor state."""
        self._last_frame = None
        self._last_analysis = ""
        self._last_api_call = 0
