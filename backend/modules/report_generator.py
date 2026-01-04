"""
PDF Report Generator Module
Generates professional PDF reports for interview assessments.

Uses ReportLab for PDF generation with:
- Professional header and styling
- Score visualizations (bar charts)
- Detailed feedback sections
- Category breakdowns
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable, ListFlowable, ListItem
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics import renderPDF

from .config import Config


class PDFReportGenerator:
    """
    Generates professional PDF reports from interview summary data.
    
    Features:
    - Header with logo and title
    - Overall score with visual indicator
    - Category score bar chart
    - Strengths and weaknesses sections
    - Visual and content feedback
    - Recommendation with color coding
    """
    
    # Color scheme
    COLORS = {
        "primary": colors.HexColor("#1a56db"),
        "success": colors.HexColor("#059669"),
        "warning": colors.HexColor("#d97706"),
        "danger": colors.HexColor("#dc2626"),
        "light_gray": colors.HexColor("#f3f4f6"),
        "dark_gray": colors.HexColor("#374151"),
        "text": colors.HexColor("#1f2937"),
        "muted": colors.HexColor("#6b7280"),
    }
    
    def __init__(self, reports_dir: str = None):
        """Initialize the PDF generator."""
        self.reports_dir = Path(reports_dir or Config.REPORTS_DIR)
        self.reports_dir.mkdir(exist_ok=True)
        self.styles = self._create_styles()
    
    def _create_styles(self) -> Dict[str, ParagraphStyle]:
        """Create custom paragraph styles."""
        base_styles = getSampleStyleSheet()
        
        custom_styles = {
            "title": ParagraphStyle(
                "CustomTitle",
                parent=base_styles["Heading1"],
                fontSize=28,
                textColor=self.COLORS["primary"],
                spaceAfter=20,
                alignment=TA_CENTER,
                fontName="Helvetica-Bold"
            ),
            "subtitle": ParagraphStyle(
                "CustomSubtitle",
                parent=base_styles["Normal"],
                fontSize=12,
                textColor=self.COLORS["muted"],
                spaceAfter=30,
                alignment=TA_CENTER,
            ),
            "section_header": ParagraphStyle(
                "SectionHeader",
                parent=base_styles["Heading2"],
                fontSize=16,
                textColor=self.COLORS["primary"],
                spaceBefore=20,
                spaceAfter=12,
                fontName="Helvetica-Bold",
                borderPadding=(0, 0, 5, 0),
            ),
            "body": ParagraphStyle(
                "CustomBody",
                parent=base_styles["Normal"],
                fontSize=11,
                textColor=self.COLORS["text"],
                spaceAfter=8,
                leading=16,
                alignment=TA_JUSTIFY,
            ),
            "score_large": ParagraphStyle(
                "ScoreLarge",
                parent=base_styles["Normal"],
                fontSize=48,
                textColor=self.COLORS["primary"],
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
            ),
            "score_label": ParagraphStyle(
                "ScoreLabel",
                parent=base_styles["Normal"],
                fontSize=14,
                textColor=self.COLORS["muted"],
                alignment=TA_CENTER,
            ),
            "recommendation_pass": ParagraphStyle(
                "RecommendationPass",
                parent=base_styles["Normal"],
                fontSize=18,
                textColor=self.COLORS["success"],
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
                spaceBefore=10,
            ),
            "recommendation_fail": ParagraphStyle(
                "RecommendationFail",
                parent=base_styles["Normal"],
                fontSize=18,
                textColor=self.COLORS["danger"],
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
                spaceBefore=10,
            ),
            "recommendation_improve": ParagraphStyle(
                "RecommendationImprove",
                parent=base_styles["Normal"],
                fontSize=18,
                textColor=self.COLORS["warning"],
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
                spaceBefore=10,
            ),
            "bullet": ParagraphStyle(
                "BulletPoint",
                parent=base_styles["Normal"],
                fontSize=11,
                textColor=self.COLORS["text"],
                leftIndent=20,
                spaceAfter=6,
                leading=14,
            ),
            "feedback_header": ParagraphStyle(
                "FeedbackHeader",
                parent=base_styles["Normal"],
                fontSize=12,
                textColor=self.COLORS["dark_gray"],
                fontName="Helvetica-Bold",
                spaceBefore=8,
                spaceAfter=4,
            ),
            "footer": ParagraphStyle(
                "Footer",
                parent=base_styles["Normal"],
                fontSize=9,
                textColor=self.COLORS["muted"],
                alignment=TA_CENTER,
            ),
        }
        
        return custom_styles
    
    def _get_score_color(self, score: int) -> colors.Color:
        """Get color based on score value."""
        if score >= 70:
            return self.COLORS["success"]
        elif score >= 50:
            return self.COLORS["warning"]
        else:
            return self.COLORS["danger"]
    
    def _get_recommendation_style(self, recommendation: str) -> ParagraphStyle:
        """Get style based on recommendation."""
        rec_upper = recommendation.upper()
        if "PASS" in rec_upper:
            return self.styles["recommendation_pass"]
        elif "FAIL" in rec_upper:
            return self.styles["recommendation_fail"]
        else:
            return self.styles["recommendation_improve"]
    
    def _create_score_bar_chart(self, category_scores: Dict[str, int]) -> Drawing:
        """Create a horizontal bar chart for category scores."""
        drawing = Drawing(500, 280)
        
        # Prepare data
        categories = list(category_scores.keys())
        scores = list(category_scores.values())
        
        # Format category names (replace underscores, title case)
        formatted_categories = [
            cat.replace("_", " ").title() for cat in categories
        ]
        
        # Create bar chart
        chart = HorizontalBarChart()
        chart.x = 180
        chart.y = 20
        chart.width = 280
        chart.height = 240
        
        chart.data = [scores]
        chart.categoryAxis.categoryNames = formatted_categories
        chart.categoryAxis.labels.fontName = "Helvetica"
        chart.categoryAxis.labels.fontSize = 9
        chart.categoryAxis.labels.dx = -5
        
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = 100
        chart.valueAxis.valueStep = 20
        chart.valueAxis.labels.fontName = "Helvetica"
        chart.valueAxis.labels.fontSize = 8
        
        # Color bars based on score
        chart.bars[0].fillColor = self.COLORS["primary"]
        
        # Individual bar colors based on value
        for i, score in enumerate(scores):
            chart.bars[0].fillColor = self._get_score_color(score)
        
        chart.barWidth = 15
        chart.barSpacing = 3
        
        drawing.add(chart)
        return drawing
    
    def _create_score_display(self, score: int) -> List:
        """Create the large score display section."""
        elements = []
        
        # Score value with color
        score_color = self._get_score_color(score)
        score_style = ParagraphStyle(
            "DynamicScore",
            parent=self.styles["score_large"],
            textColor=score_color,
        )
        
        elements.append(Paragraph(f"{score}/100", score_style))
        elements.append(Paragraph("Overall Score", self.styles["score_label"]))
        
        return elements
    
    def _create_strengths_section(self, strengths: List[str]) -> List:
        """Create the strengths bullet list."""
        elements = []
        elements.append(Paragraph("✅ Strengths", self.styles["section_header"]))
        
        for strength in strengths:
            bullet_text = f"• {strength}"
            elements.append(Paragraph(bullet_text, self.styles["bullet"]))
        
        return elements
    
    def _create_weaknesses_section(self, weaknesses: List[str]) -> List:
        """Create the weaknesses/areas for improvement bullet list."""
        elements = []
        elements.append(Paragraph("⚠️ Areas for Improvement", self.styles["section_header"]))
        
        for weakness in weaknesses:
            bullet_text = f"• {weakness}"
            elements.append(Paragraph(bullet_text, self.styles["bullet"]))
        
        return elements
    
    def _create_visual_feedback_section(self, visual_feedback: Dict[str, str]) -> List:
        """Create the visual feedback section."""
        elements = []
        elements.append(Paragraph("🎨 Visual & Presentation Feedback", self.styles["section_header"]))
        
        feedback_items = [
            ("Slide Design", visual_feedback.get("slide_design", "N/A")),
            ("Diagrams & Charts", visual_feedback.get("diagrams", "N/A")),
            ("Code Presentation", visual_feedback.get("code_presentation", "N/A")),
            ("Suggestions", visual_feedback.get("suggestions", "N/A")),
        ]
        
        for label, content in feedback_items:
            elements.append(Paragraph(label, self.styles["feedback_header"]))
            elements.append(Paragraph(content, self.styles["body"]))
        
        return elements
    
    def _create_content_feedback_section(self, content_feedback: Dict[str, str]) -> List:
        """Create the content feedback section."""
        elements = []
        elements.append(Paragraph("📝 Content Feedback", self.styles["section_header"]))
        
        feedback_items = [
            ("Structure", content_feedback.get("structure", "N/A")),
            ("Technical Depth", content_feedback.get("depth", "N/A")),
            ("Missing Topics", content_feedback.get("missing_topics", "N/A")),
        ]
        
        for label, content in feedback_items:
            elements.append(Paragraph(label, self.styles["feedback_header"]))
            elements.append(Paragraph(content, self.styles["body"]))
        
        return elements
    
    def _create_category_scores_table(self, category_scores: Dict[str, int]) -> Table:
        """Create a styled table for category scores."""
        # Prepare data
        data = [["Category", "Score", "Rating"]]
        
        for category, score in category_scores.items():
            formatted_cat = category.replace("_", " ").title()
            rating = "Excellent" if score >= 80 else "Good" if score >= 60 else "Needs Work" if score >= 40 else "Poor"
            data.append([formatted_cat, f"{score}/100", rating])
        
        # Create table
        table = Table(data, colWidths=[3*inch, 1*inch, 1.5*inch])
        
        # Style the table
        style = TableStyle([
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["primary"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            
            # Data rows
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
            ("TOPPADDING", (0, 1), (-1, -1), 8),
            
            # Alternating row colors
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, self.COLORS["light_gray"]]),
            
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, self.COLORS["muted"]),
        ])
        
        table.setStyle(style)
        return table
    
    def generate(
        self,
        summary: Dict[str, Any],
        session_id: str,
        candidate_name: str = "Candidate",
        history: List[Dict] = None
    ) -> str:
        """
        Generate a PDF report from interview summary data.
        
        Args:
            summary: The interview summary dict from InterviewBrain.generate_summary()
            session_id: Unique session identifier
            candidate_name: Name of the candidate (if known)
            history: Optional interview history for additional context
            
        Returns:
            Path to the generated PDF file
        """
        # Create PDF file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{session_id}_{timestamp}.pdf"
        filepath = self.reports_dir / filename
        
        # Create document
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        # Build content
        elements = []
        
        # === Header Section ===
        elements.append(Paragraph("NavAI Technical Assessment Report", self.styles["title"]))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
            self.styles["subtitle"]
        ))
        
        # Horizontal line
        elements.append(HRFlowable(
            width="100%",
            thickness=2,
            color=self.COLORS["primary"],
            spaceBefore=10,
            spaceAfter=20
        ))
        
        # === Overall Score Section ===
        overall_score = summary.get("overall_score", 0)
        recommendation = summary.get("recommendation", "NEEDS_REVIEW")
        
        # Score display
        elements.extend(self._create_score_display(overall_score))
        
        # Recommendation
        rec_style = self._get_recommendation_style(recommendation)
        recommendation_display = recommendation.replace("_", " ")
        elements.append(Paragraph(f"📋 {recommendation_display}", rec_style))
        elements.append(Spacer(1, 20))
        
        # Summary text
        summary_text = summary.get("summary", "No summary available.")
        elements.append(Paragraph(summary_text, self.styles["body"]))
        elements.append(Spacer(1, 20))
        
        # === Category Scores Section ===
        category_scores = summary.get("category_scores", {})
        if category_scores:
            elements.append(Paragraph("📊 Category Breakdown", self.styles["section_header"]))
            elements.append(Spacer(1, 10))
            
            # Bar chart
            chart = self._create_score_bar_chart(category_scores)
            elements.append(chart)
            elements.append(Spacer(1, 20))
            
            # Detailed table
            table = self._create_category_scores_table(category_scores)
            elements.append(table)
            elements.append(Spacer(1, 20))
        
        # === Strengths Section ===
        strengths = summary.get("strengths", [])
        if strengths:
            elements.extend(self._create_strengths_section(strengths))
            elements.append(Spacer(1, 15))
        
        # === Weaknesses Section ===
        weaknesses = summary.get("weaknesses", [])
        if weaknesses:
            elements.extend(self._create_weaknesses_section(weaknesses))
            elements.append(Spacer(1, 15))
        
        # === Visual Feedback Section ===
        visual_feedback = summary.get("visual_feedback", {})
        if visual_feedback:
            elements.extend(self._create_visual_feedback_section(visual_feedback))
            elements.append(Spacer(1, 15))
        
        # === Content Feedback Section ===
        content_feedback = summary.get("content_feedback", {})
        if content_feedback:
            elements.extend(self._create_content_feedback_section(content_feedback))
            elements.append(Spacer(1, 20))
        
        # === Footer ===
        elements.append(HRFlowable(
            width="100%",
            thickness=1,
            color=self.COLORS["muted"],
            spaceBefore=20,
            spaceAfter=10
        ))
        elements.append(Paragraph(
            f"Session ID: {session_id} | NavAI Real-Time Interviewer | Confidential",
            self.styles["footer"]
        ))
        
        # Build PDF
        doc.build(elements)
        
        print(f"[ReportGen] PDF generated: {filepath}")
        return str(filepath)
    
    def get_report_path(self, session_id: str) -> Optional[str]:
        """
        Find an existing report for a session ID.
        
        Args:
            session_id: The session ID to search for
            
        Returns:
            Path to the report if found, None otherwise
        """
        for filepath in self.reports_dir.glob(f"report_{session_id}_*.pdf"):
            return str(filepath)
        return None
    
    def list_reports(self) -> List[Dict[str, str]]:
        """
        List all generated reports.
        
        Returns:
            List of report metadata dicts
        """
        reports = []
        for filepath in sorted(self.reports_dir.glob("*.pdf"), reverse=True):
            parts = filepath.stem.split("_")
            session_id = parts[1] if len(parts) > 1 else "unknown"
            reports.append({
                "filename": filepath.name,
                "session_id": session_id,
                "path": str(filepath),
                "created": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()
            })
        return reports
