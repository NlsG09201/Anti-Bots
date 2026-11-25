"""Tenant-scoped PDF report rendering for Power BI analytics exports."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#142338")
MUTED = colors.HexColor("#53657c")
ACCENT = colors.HexColor("#087f68")
PALE = colors.HexColor("#edf4f3")
GRID = colors.HexColor("#d9e2ea")
COLOMBIA_TZ = timezone(timedelta(hours=-5))


def _register_fonts() -> tuple[str, str]:
    import reportlab

    fonts_dir = Path(reportlab.__file__).parent / "fonts"
    regular_name = "StreamShieldVera"
    bold_name = "StreamShieldVera-Bold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular_name, str(fonts_dir / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont(bold_name, str(fonts_dir / "VeraBd.ttf")))
    return regular_name, bold_name


def _number(value: Any, decimals: int = 0) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return f"{number:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _safe_paragraph(value: Any) -> str:
    return escape(str(value if value is not None else "—"), quote=True)


def _footer(canvas, document) -> None:
    canvas.saveState()
    width, _ = letter
    canvas.setStrokeColor(GRID)
    canvas.line(0.6 * inch, 0.52 * inch, width - 0.6 * inch, 0.52 * inch)
    canvas.setFont("StreamShieldVera", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.6 * inch, 0.34 * inch, "StreamShield · Informe de análisis de seguridad")
    canvas.drawRightString(width - 0.6 * inch, 0.34 * inch, f"Página {document.page}")
    canvas.restoreState()


def _table(rows: Iterable[list[Any]], widths: list[float], *, header: bool = True) -> Table:
    body = list(rows)
    table = Table(body, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, GRID),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
        ])
    table.setStyle(TableStyle(commands))
    return table


def build_executive_pdf(report: Dict[str, Any]) -> bytes:
    """Render real tenant-scoped analytics into a downloadable Spanish PDF."""
    regular_font, bold_font = _register_fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], fontName=bold_font,
        fontSize=21, leading=26, textColor=INK, alignment=TA_LEFT,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle", parent=styles["Normal"], fontName=regular_font,
        fontSize=9, leading=13, textColor=MUTED, spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="ReportSection", parent=styles["Heading2"], fontName=bold_font,
        fontSize=12, leading=15, textColor=ACCENT, spaceBefore=12,
        spaceAfter=7, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="ReportBody", parent=styles["BodyText"], fontName=regular_font,
        fontSize=9, leading=13, textColor=INK,
    ))
    styles.add(ParagraphStyle(
        name="ReportCell", parent=styles["BodyText"], fontName=regular_font,
        fontSize=8, leading=10, textColor=INK,
    ))
    styles.add(ParagraphStyle(
        name="ReportHeaderCell", parent=styles["BodyText"], fontName=bold_font,
        fontSize=8, leading=10, textColor=ACCENT,
    ))

    executive = report.get("executive_summary") or {}
    operations = report.get("realtime_operations") or {}
    ai = report.get("ai_intelligence") or {}
    generated_at = report.get("generated_at")
    try:
        generated = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        generated = generated.astimezone(COLOMBIA_TZ)
        generated_label = generated.strftime("%d/%m/%Y %H:%M COT")
    except (TypeError, ValueError):
        generated_label = str(generated_at or "")

    posture = str(executive.get("posture") or "stable")
    posture_labels = {
        "stable": "Estable",
        "elevated": "Elevado",
        "high": "Alto",
        "critical": "Crítico",
    }
    recommendations = {
        "stable": "Mantén el monitoreo programado y revisa las alertas cuando aparezcan.",
        "elevated": "Mantén el monitoreo activo y revisa el crecimiento, los follows y el chat sospechosos.",
        "high": "Aumenta la revisión de canales de alto riesgo y valida las señales de actividad coordinada.",
        "critical": "Activa el procedimiento de respuesta y prioriza los ataques coordinados y canales afectados.",
    }

    body_style = styles["ReportBody"]
    cell_style = styles["ReportCell"]
    header_style = styles["ReportHeaderCell"]
    story = [
        Paragraph("Informe ejecutivo de seguridad", styles["ReportTitle"]),
        Paragraph(
            f"StreamShield SOC · Generado {escape(generated_label)} · Ventana: "
            f"{_number(report.get('window_hours'))} horas",
            styles["ReportSubtitle"],
        ),
        Paragraph("Resumen", styles["ReportSection"]),
        Paragraph(
            f"Estado de riesgo: <b>{posture_labels.get(posture, _safe_paragraph(posture))}</b>. "
            f"{_safe_paragraph(recommendations.get(posture, executive.get('recommendation')))}",
            body_style,
        ),
        Spacer(1, 8),
    ]

    metrics = [
        ["Indicador", "Resultado", "Indicador", "Resultado"],
        ["Riesgo global", f"{_number(executive.get('global_risk'), 1)}/100", "Amenaza global", f"{_number(executive.get('global_threat_score'), 1)}/100"],
        ["Engagement real", f"{_number(executive.get('real_engagement_percentage'), 1)}%", "Porcentaje de bots", f"{_number(executive.get('bot_percentage'), 1)}%"],
        ["Ataques activos", _number(executive.get("active_attacks")), "Espectadores monitoreados", _number(executive.get("monitored_viewers"))],
        ["Espectadores sospechosos", _number(executive.get("suspicious_viewers")), "Anomalías", _number(operations.get("anomalies"))],
    ]
    metrics_cells = [
        [Paragraph(_safe_paragraph(value), header_style if row_index == 0 else cell_style) for value in row]
        for row_index, row in enumerate(metrics)
    ]
    story.append(_table(metrics_cells, [2.0 * inch, 1.35 * inch, 2.3 * inch, 1.65 * inch]))

    story.extend([
        Paragraph("Actividad reciente", styles["ReportSection"]),
        Paragraph(
            f"Espectadores por minuto: {_number(operations.get('viewers_per_minute'), 2)} · "
            f"Follows por minuto: {_number(operations.get('follows_per_minute'), 2)} · "
            f"Mensajes por minuto: {_number(operations.get('messages_per_minute'), 2)} · "
            f"Incidentes críticos detectados: {_number(operations.get('suspicious_spikes'))} · "
            f"Redadas activas: {_number(operations.get('active_raids') )}.",
            body_style,
        ),
        Paragraph("Canales con mayor riesgo", styles["ReportSection"]),
    ])

    stream_rows = [["Canal / plataforma", "Espectadores", "Riesgo", "Audiencia sospechosa"]]
    for row in (report.get("highest_risk_streams") or [])[:10]:
        stream_rows.append([
            Paragraph(f"{_safe_paragraph(row.get('channel_name'))} / {_safe_paragraph(row.get('platform_key'))}", cell_style),
            _number(row.get("viewer_count")),
            f"{_number(row.get('threat_score'), 1)}/100",
            f"{_number(float(row.get('suspicious_ratio') or 0) * 100, 1)}%",
        ])
    if len(stream_rows) == 1:
        stream_rows.append(["Sin canales con registros en el período", "—", "—", "—"])
    stream_cells = [[Paragraph(_safe_paragraph(value), header_style if row_index == 0 else cell_style)
                     for value in row] for row_index, row in enumerate(stream_rows)]
    story.append(_table(stream_cells, [2.65 * inch, 1.0 * inch, 0.85 * inch, 1.35 * inch]))

    story.append(Paragraph("Tipos de ataque", styles["ReportSection"]))
    attack_rows = [["Tipo", "Cantidad"]]
    for row in (report.get("top_attack_types") or [])[:10]:
        attack_rows.append([Paragraph(_safe_paragraph(row.get("attack_type")), cell_style), _number(row.get("count"))])
    if len(attack_rows) == 1:
        attack_rows.append(["Sin ataques registrados en el período", "0"])
    attack_cells = [[Paragraph(_safe_paragraph(value), header_style if row_index == 0 else cell_style)
                     for value in row] for row_index, row in enumerate(attack_rows)]
    story.append(_table(attack_cells, [4.0 * inch, 1.5 * inch]))

    story.extend([
        Paragraph("Señales de inteligencia artificial", styles["ReportSection"]),
        Paragraph(
            f"Predicciones disponibles: {_number(ai.get('predictions_total'))} · "
            f"Riesgo promedio: {_number(ai.get('threat_score_avg'), 1)} · "
            f"Probabilidad promedio de bots: {_number(float(ai.get('bot_probability_avg') or 0) * 100, 1)}% · "
            f"Anomalía promedio: {_number(ai.get('anomaly_score_avg'), 1)} · "
            f"Señales coordinadas: {_number(ai.get('viewers_coordinados'))}.",
            body_style,
        ),
        Spacer(1, 10),
        Paragraph(
            "Fuente: métricas operativas y eventos de la cuenta autenticada. "
            "Los resultados reflejan únicamente los datos disponibles para el período seleccionado.",
            styles["ReportSubtitle"],
        ),
    ])

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.72 * inch,
        title="Informe ejecutivo de seguridad - StreamShield",
        author="StreamShield SOC",
    )
    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output.getvalue()
