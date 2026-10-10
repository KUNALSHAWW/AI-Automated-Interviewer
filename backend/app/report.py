"""PDF report (ReportLab). Mirrors the JSON report: score table, verbatim evidence, flags, repo checks, screens."""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BLUE, GREEN, AMBER, RED, MUTED = (colors.HexColor(c) for c in ("#1a56db", "#059669", "#d97706", "#dc2626", "#6b7280"))


def _t(s) -> str:
    """Helvetica has no Devanagari glyphs; unsupported characters become '?' (the web report and JSON keep them)."""
    return escape(str(s or "").encode("latin-1", "replace").decode("latin-1"))


def _mmss(sec: float) -> str:
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"


def build_pdf(report: dict, meta: dict, session_id: str, thumbs: list[tuple[Path, str]]) -> bytes:
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=BLUE, fontSize=20, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=BLUE, fontSize=13, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=MUTED)
    quote = ParagraphStyle("q", parent=body, leftIndent=10, textColor=colors.HexColor("#374151"), fontName="Helvetica-Oblique")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"NavAI Viva report {session_id}", author="NavAI Viva")
    el: list = []
    ov = report["overall"]
    el.append(Paragraph("NavAI Viva: project defense report", h1))
    el.append(Paragraph(_t(f"Session {session_id} | {datetime.fromtimestamp(meta.get('created', 0)):%Y-%m-%d %H:%M} | "
                           f"rubric: {report['rubric']['title']} | language: {meta.get('language', 'en')}"), small))
    if meta.get("repo_url"):
        el.append(Paragraph(_t(f"Repository: {meta['repo_url']}"), small))
    el.append(Spacer(1, 6))
    el.append(Paragraph(_t(report["disclaimer"]), small))

    score = "n/a" if ov["score"] is None else f"{ov['score']:.1f} / 4  ({ov['pct']}%)"
    el.append(Paragraph("Overall", h2))
    el.append(Paragraph(f"<b>{_t(ov['band'])}</b> | score {_t(score)} | rubric coverage {round(ov['coverage'] * 100)}%", body))
    rv = report["review"]
    if rv["needs_human_review"]:
        el.append(Paragraph("<font color='#dc2626'><b>Human review recommended</b></font>", body))
        for r in rv["reasons"]:
            el.append(Paragraph("- " + _t(r), body))

    el.append(Paragraph("Rubric dimensions", h2))
    rows = [["Dimension", "Score", "Evidence", "Graders"]]
    for d in report["dimensions"]:
        sc = "not observed" if d["final"] is None else f"{d['final']:.1f}"
        gr = ", ".join(f"{s:.1f}" for s in d.get("council_scores", [])) or "-"
        rows.append([Paragraph(_t(d["label"]), body), sc, str(d["n_obs"]), gr])
    tbl = Table(rows, colWidths=[78 * mm, 28 * mm, 22 * mm, 40 * mm])
    tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                             ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el.append(tbl)

    if report["strengths"] or report["growth"]:
        el.append(Paragraph("What went well", h2))
        for p in report["strengths"]:
            el.append(Paragraph(_t("- " + p["text"]) + f" <font color='#6b7280'>[{', '.join(p['evidence'])}]</font>", body))
        el.append(Paragraph("What to work on", h2))
        for p in report["growth"]:
            el.append(Paragraph(_t("- " + p["text"]) + f" <font color='#6b7280'>[{', '.join(p['evidence'])}]</font>", body))
    elif report["process"]["narrative_status"] == "unavailable":
        el.append(Paragraph("Narrative feedback was unavailable (no grading model responded). Scores above are computed "
                            "directly from verified quotes.", body))
    if report["next_steps"]:
        el.append(Paragraph("Next steps", h2))
        for s in report["next_steps"]:
            el.append(Paragraph("- " + _t(s), body))

    cl = report.get("claims") or {}
    if cl:
        el.append(Paragraph("What was said vs the repository", h2))
        el.append(Paragraph(_t("Supported: " + (", ".join(cl.get("supported", [])) or "none")), body))
        el.append(Paragraph(_t("Mentioned but not found in repository evidence: " + (", ".join(cl.get("not_found", [])) or "none")), body))
        el.append(Paragraph(_t("Numeric claims without support: " + (", ".join(cl.get("unverified_metrics", [])) or "none")), body))
        el.append(Paragraph("Automated checks are hints: the repository sample may be incomplete.", small))
    if report["flags"]:
        el.append(Paragraph("Consistency flags", h2))
        for f in report["flags"]:
            el.append(Paragraph(_t(f"[{_mmss(f.get('t', 0))}] {f['kind']}: {f['detail']}"), body))

    el.append(Paragraph("Evidence (verbatim quotes)", h2))
    for d in report["dimensions"]:
        if not d["evidence"]:
            continue
        el.append(Paragraph(f"<b>{_t(d['label'])}</b>", body))
        for e in d["evidence"]:
            el.append(Paragraph(_t(f"[{e['id']} | {_mmss(e['t'])} | {e['source']} | score {e['score']}] \"{e['quote']}\""), quote))
    if report["not_observed"]:
        el.append(Spacer(1, 4))
        el.append(Paragraph(_t("Not observed in this session: " + ", ".join(report["not_observed"])), body))

    shown = [(p, c) for p, c in thumbs if Path(p).exists()][:6]
    if shown:
        el.append(Paragraph("Screens shown", h2))
        for p, cap in shown:
            el.append(Image(str(p), width=70 * mm, height=39 * mm))
            el.append(Paragraph(_t(cap), small))

    pr = report["process"]
    el.append(Paragraph("How this report was produced", h2))
    el.append(Paragraph(_t(
        f"{pr['utterances']} utterances, {pr['questions']} questions, {pr['screens']} screens, {pr['observations']} verified "
        f"observations ({pr['dropped_unverified']} model claims dropped because the quote could not be found). "
        f"Graders: {', '.join(pr['council']) or 'none'}. Duration {_mmss(pr['duration_s'])}."), small))
    doc.build(el)
    return buf.getvalue()
