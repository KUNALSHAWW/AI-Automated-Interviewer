"""
Interview Brain Module
The core AI logic for evaluating responses and generating questions.

Implements the "Conflict & Context" evaluation engine:
1. Compare verbal explanation vs screen content
2. Score responses on multiple dimensions
3. Generate adaptive follow-up questions
"""

import asyncio
import json
import time
from typing import Dict, List, Optional
from groq import Groq

from .config import Config


class InterviewBrain:
    """
    The evaluation engine for the AI Interviewer.
    
    Responsibilities:
    - Analyze student responses against screen content
    - Detect conflicts between verbal and visual
    - Score responses (0-10)
    - Generate context-aware questions
    """
    
    EVALUATION_SYSTEM_PROMPT = """You are a Senior Staff Engineer evaluating a technical project presentation.
Be critical of scalability, security, and implementation details.

BEHAVIOR:
- Ask ONE focused question per slide about what's shown
- If answer is vague/confusing/wrong, ask ONE follow-up to clarify
- If content is clear and well-explained, let them proceed
- Keep questions SHORT (under 20 words)
- Sound natural and encouraging

WHEN TO ASK A QUESTION:
- New slide/content appears → Ask about it
- They explain something → Probe deeper with "How does X work?" or "Why did you choose Y?"
- Unclear answer → "Can you clarify what you mean by...?"

WHEN TO LET THEM PROCEED (respond_type: proceed):
- They answered your question satisfactorily
- Content is self-explanatory and they explained it well
- They ask "Should I move on?" → Let them proceed

SPEED OPTIMIZATION:
If the presenter is speaking clearly and content matches the screen, output MINIMAL JSON:
{"response_type":"proceed"}
This saves tokens and reduces latency.

FULL OUTPUT FORMAT (when question needed):
{"score":<0-10>,"conflict_detected":<true/false>,"feedback":"<brief>","next_response":"<your SHORT question or acknowledgment>","response_type":"<question|acknowledgment|proceed>","topic":"<current topic>","needs_followup":<true if their answer was weak>}"""

    OPENING_PROMPT = """Generate a brief, warm opening (under 30 words). Ask their name and what project they're presenting. Sound friendly and natural. Output only the greeting."""

    SUMMARY_PROMPT = """You are generating a COMPREHENSIVE interview evaluation report.

Generate a detailed JSON evaluation with these EXACT fields:
{
    "overall_score": <0-100>,
    "category_scores": {
        "technical_depth": <0-100>,
        "clarity_of_explanation": <0-100>,
        "originality": <0-100>,
        "implementation_understanding": <0-100>,
        "presentation_formatting": <0-100>,
        "visual_aids_quality": <0-100>,
        "diagrams_and_charts": <0-100>,
        "code_quality": <0-100>,
        "problem_solving": <0-100>,
        "communication_skills": <0-100>
    },
    "strengths": [
        "<specific strength 1 with example>",
        "<specific strength 2 with example>",
        "<specific strength 3 with example>"
    ],
    "weaknesses": [
        "<specific weakness 1 with suggestion>",
        "<specific weakness 2 with suggestion>"
    ],
    "visual_feedback": {
        "slide_design": "<feedback on slide design, colors, layout>",
        "diagrams": "<feedback on diagrams, flowcharts if any>",
        "code_presentation": "<feedback on how code was shown>",
        "suggestions": "<specific visual improvement suggestions>"
    },
    "content_feedback": {
        "structure": "<feedback on presentation structure>",
        "depth": "<was content deep enough?>",
        "missing_topics": "<any topics that should have been covered>"
    },
    "summary": "<3-4 sentence personalized overall assessment>",
    "recommendation": "<PASS/NEEDS_IMPROVEMENT/FAIL with brief reason>"
}

Be SPECIFIC - reference actual content from the presentation."""

    def __init__(self):
        self.groq_client = Groq(api_key=Config.GROQ_API_KEY)
        self.conversation_history: List[Dict] = []
        self.remediation_threshold = Config.REMEDIATION_THRESHOLD
        
        # Follow-up tracking - don't bombard with questions
        self.pending_followup_topic: Optional[str] = None
        self.followup_attempts: Dict[str, int] = {}  # topic -> attempt count
        self.last_question_time: float = 0
        self.min_question_interval: float = 5.0  # seconds between questions
    
    async def evaluate(
        self,
        transcript: str,
        screen_context: str,
        history: List[Dict],
        is_followup_response: bool = False
    ) -> Dict:
        """
        Evaluate student response against screen content.
        
        Args:
            transcript: What the student said
            screen_context: Analysis of what's on screen
            history: Previous evaluation history
            is_followup_response: Whether this is responding to a follow-up question
            
        Returns:
            Evaluation dict with score, conflict info, next question
        """
        import time
        
        try:
            # Check if we should ask a question (pacing)
            current_time = time.time()
            time_since_last = current_time - self.last_question_time
            
            # Determine if this is a follow-up to a previous low-score topic
            followup_context = ""
            if self.pending_followup_topic:
                attempts = self.followup_attempts.get(self.pending_followup_topic, 0)
                followup_context = f"""\n## FOLLOW-UP CONTEXT:
This is the student's {attempts + 1}{'st' if attempts == 0 else 'nd' if attempts == 1 else 'rd' if attempts == 2 else 'th'} attempt explaining: {self.pending_followup_topic}
Previously they scored low. Be encouraging and see if they've improved.
If this is attempt 2+, give a final score."""
            
            # Build context
            context = f"""## SCREEN CONTENT:
{screen_context if screen_context else "No screen content captured yet"}

## STUDENT'S EXPLANATION:
"{transcript}"

## PREVIOUS CONTEXT:
{self._format_recent_history(history)}{followup_context}

Remember: Ask only ONE question. Be encouraging. Evaluate and respond with JSON only."""

            # Track in conversation
            self.conversation_history.append({
                "role": "user", 
                "content": context
            })
            
            # Call LLM (in thread pool) - using FAST model for speed
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.groq_client.chat.completions.create(
                    model=Config.FAST_LLM_MODEL,  # Fast 8B model for real-time
                    messages=[
                        {"role": "system", "content": self.EVALUATION_SYSTEM_PROMPT},
                        *self.conversation_history[-4:]  # Reduced context for speed
                    ],
                    temperature=0.2,  # Lower for faster, more deterministic
                    max_tokens=200  # Reduced for speed
                )
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON - handle minimal "proceed" response
            result = self._parse_json_response(content)
            
            # Fast path: if model says proceed, return minimal response
            if result.get("response_type") == "proceed" and len(result) <= 2:
                result = {
                    "score": 7,
                    "conflict_detected": False,
                    "feedback": "Good explanation",
                    "next_response": "",  # No response needed
                    "response_type": "proceed",
                    "topic": result.get("topic", "continuing"),
                    "needs_followup": False
                }
                return result
            
            # Track follow-up logic
            topic = result.get("topic", "general")
            needs_followup = result.get("needs_followup", False)
            is_final = result.get("is_final_score", True)
            
            if needs_followup and not is_final:
                # Student needs another chance - track this topic
                self.pending_followup_topic = topic
                self.followup_attempts[topic] = self.followup_attempts.get(topic, 0) + 1
            else:
                # Topic is resolved or scored
                if self.pending_followup_topic == topic:
                    self.pending_followup_topic = None
            
            # Update question timing
            self.last_question_time = time.time()
            
            # Track AI response
            self.conversation_history.append({
                "role": "assistant",
                "content": result.get("next_question", "")
            })
            
            return result
            
        except Exception as e:
            print(f"[Brain] Evaluation error: {e}")
            return {
                "score": 5,
                "conflict_detected": False,
                "conflict_description": "None",
                "feedback": f"Evaluation error: {str(e)[:50]}",
                "next_question": "Could you elaborate on that point?",
                "question_type": "remediation",
                "topic": "Unknown"
            }
    
    async def generate_opening(self) -> str:
        """Generate opening statement for the interview."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.groq_client.chat.completions.create(
                    model=Config.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a friendly, professional technical interviewer starting a presentation session."},
                        {"role": "user", "content": self.OPENING_PROMPT}
                    ],
                    temperature=0.7,
                    max_tokens=80
                )
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"[Brain] Opening error: {e}")
            return "Hi there! Welcome to your presentation session. Before we begin, could you tell me a bit about yourself and what project you'll be presenting today?"
    
    async def generate_summary(self, history: List[Dict], screen_contexts: List[str] = None) -> Dict:
        """Generate comprehensive final interview summary with visual feedback."""
        try:
            # Calculate detailed stats
            scores = [h.get("score", 0) for h in history]
            tech_scores = [h.get("technical_depth", h.get("score", 5)) for h in history]
            clarity_scores = [h.get("clarity", h.get("score", 5)) for h in history]
            visual_scores = [h.get("visual_quality", 5) for h in history]
            conflicts = [h for h in history if h.get("conflict", False)]
            
            avg_score = sum(scores) / len(scores) if scores else 0
            avg_tech = sum(tech_scores) / len(tech_scores) if tech_scores else 5
            avg_clarity = sum(clarity_scores) / len(clarity_scores) if clarity_scores else 5
            avg_visual = sum(visual_scores) / len(visual_scores) if visual_scores else 5
            
            # Build detailed history
            history_items = []
            for i, h in enumerate(history):
                conflict_text = "Yes - " + h.get("conflict_description", "") if h.get("conflict") else "No"
                item = f"""Topic {i+1}: {h.get('topic', 'Unknown')}
  - Score: {h.get('score', 'N/A')}/10
  - Technical Depth: {h.get('technical_depth', 'N/A')}/10
  - Clarity: {h.get('clarity', 'N/A')}/10
  - Visual Quality: {h.get('visual_quality', 'N/A')}/10
  - Conflict: {conflict_text}
  - Presenter said: {h.get('transcript', '')[:150]}...
  - AI feedback: {h.get('feedback', '')}"""
                history_items.append(item)
            
            history_text = "\n".join(history_items)
            
            # Include screen context summary if available
            visual_context = ""
            if screen_contexts and len(screen_contexts) > 0:
                context_items = ["- " + ctx[:200] for ctx in screen_contexts[-5:] if ctx]
                visual_context = f"""
## VISUAL CONTENT OBSERVED:
The presentation included the following visual elements:
{chr(10).join(context_items)}
"""
            
            prompt = f"""Analyze this complete interview and generate a DETAILED evaluation report.

## INTERVIEW STATISTICS:
- Total Topics Discussed: {len(history)}
- Average Score: {avg_score:.1f}/10
- Average Technical Depth: {avg_tech:.1f}/10
- Average Clarity: {avg_clarity:.1f}/10
- Average Visual Quality: {avg_visual:.1f}/10
- Conflicts Detected: {len(conflicts)}

## DETAILED INTERACTION HISTORY:
{history_text}
{visual_context}

Based on this complete interview data, generate the comprehensive JSON evaluation.
Include SPECIFIC examples from the presentation in strengths and weaknesses.
Provide actionable feedback on visuals, slides, and diagrams."""
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.groq_client.chat.completions.create(
                    model=Config.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": self.SUMMARY_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1000
                )
            )
            
            result = self._parse_json_response(response.choices[0].message.content)
            
            # Ensure all required fields exist
            result.setdefault("overall_score", int(avg_score * 10))
            result.setdefault("category_scores", {
                "technical_depth": int(avg_tech * 10),
                "clarity_of_explanation": int(avg_clarity * 10),
                "originality": 50,
                "implementation_understanding": int(avg_score * 10),
                "presentation_formatting": int(avg_visual * 10),
                "visual_aids_quality": int(avg_visual * 10),
                "diagrams_and_charts": 50,
                "code_quality": 50,
                "problem_solving": int(avg_score * 10),
                "communication_skills": int(avg_clarity * 10)
            })
            result.setdefault("strengths", ["Completed the presentation"])
            result.setdefault("weaknesses", ["Could provide more technical depth"])
            result.setdefault("visual_feedback", {
                "slide_design": "Standard presentation format",
                "diagrams": "Consider adding more visual diagrams",
                "code_presentation": "Code was shown during presentation",
                "suggestions": "Add more visual aids to support explanations"
            })
            result.setdefault("content_feedback", {
                "structure": "Presentation had a logical flow",
                "depth": "Technical content was covered",
                "missing_topics": "None identified"
            })
            result.setdefault("summary", f"Completed {len(history)} topics with average score {avg_score:.1f}/10.")
            result.setdefault("recommendation", "PASS" if avg_score >= 6 else "NEEDS_IMPROVEMENT" if avg_score >= 4 else "FAIL")
            
            print(f"[Brain] Summary generated successfully: {result.get('overall_score')}/100")
            return result
            
        except Exception as e:
            print(f"[Brain] Summary error: {e}")
            import traceback
            traceback.print_exc()
            
            avg_score = sum([h.get("score", 0) for h in history]) / len(history) if history else 5
            return {
                "overall_score": int(avg_score * 10),
                "category_scores": {
                    "technical_depth": int(avg_score * 10),
                    "clarity_of_explanation": int(avg_score * 10),
                    "originality": 50,
                    "implementation_understanding": int(avg_score * 10),
                    "presentation_formatting": 50,
                    "visual_aids_quality": 50,
                    "diagrams_and_charts": 50,
                    "code_quality": 50,
                    "problem_solving": 50,
                    "communication_skills": 50
                },
                "strengths": ["Completed presentation", "Engaged with questions"],
                "weaknesses": ["Review technical accuracy", "Add more visual aids"],
                "visual_feedback": {
                    "slide_design": "Could not fully evaluate",
                    "diagrams": "Consider adding diagrams",
                    "code_presentation": "Standard code display",
                    "suggestions": "Add visual flowcharts and architecture diagrams"
                },
                "content_feedback": {
                    "structure": "Standard presentation structure",
                    "depth": "Adequate technical depth",
                    "missing_topics": "None identified"
                },
                "summary": f"Completed {len(history)} topics with average score {avg_score:.1f}/10.",
                "recommendation": "NEEDS_IMPROVEMENT"
            }
    
    def _format_recent_history(self, history: List[Dict]) -> str:
        """Format recent history for context."""
        if not history:
            return "This is the first question."
        
        recent = history[-3:]  # Last 3 interactions
        return "\n".join([
            f"- Q{h.get('slide', '?')}: {h.get('question', '')[:100]}"
            for h in recent
        ])
    
    def _parse_json_response(self, content: str) -> Dict:
        """Parse JSON from LLM response."""
        try:
            # Extract JSON from response
            if "{" in content:
                json_str = content[content.find("{"):content.rfind("}")+1]
                return json.loads(json_str)
            raise ValueError("No JSON found")
        except Exception as e:
            print(f"[Brain] JSON parse error: {e}")
            print(f"[Brain] Raw content: {content[:200]}")
            return {
                "score": 5,
                "conflict_detected": False,
                "conflict_description": "None",
                "feedback": "Parse error",
                "next_question": "Could you explain that further?",
                "question_type": "remediation",
                "topic": "Unknown"
            }
    
    def reset(self):
        """Reset for a new interview."""
        self.conversation_history = []
        self.pending_followup_topic = None
        self.followup_attempts = {}
        self.last_question_time = 0
