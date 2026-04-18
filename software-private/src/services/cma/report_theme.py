"""
Report Theme Engine for CMA / DPR Builder.
Mode-specific design tokens, color palettes, typography, and reusable table builders.
"""

from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import Paragraph, Table, TableStyle, Spacer


class ModeTheme:
    """Design tokens for a specific report mode."""
    def __init__(self, mode_key):
        tokens = _THEME_MAP.get(mode_key, _THEME_MAP["pro"])
        self.PRIMARY_HEX = tokens["primary"]
        self.SECONDARY_HEX = tokens["secondary"]
        self.PRIMARY = HexColor(self.PRIMARY_HEX)
        self.SECONDARY = HexColor(self.SECONDARY_HEX)
        self.ACCENT = HexColor(tokens["accent"])
        self.HEADER_BG = HexColor(tokens["header_bg"])
        self.HEADER_FG = HexColor(tokens["header_fg"])
        self.BAND_ODD = HexColor(tokens["band_odd"])
        self.TOTAL_BG = HexColor(tokens["total_bg"])
        self.BORDER = HexColor(tokens["border"])
        self.TEXT = HexColor(tokens["text"])
        self.MUTED = HexColor(tokens["muted"])
        self.ACCENT_AMBER = HexColor("#F59E0B") # Standard Amber for premium highlights
        self.mode_key = mode_key
        # RGB Tuples for non-ReportLab usage (like Word)
        self.PRIMARY_RGB = self._hex_to_rgb(self.PRIMARY_HEX)
        self.SECONDARY_RGB = self._hex_to_rgb(self.SECONDARY_HEX)
        # Typography sizes
        t = tokens["typo"]
        self.COVER_TITLE_SIZE = t["cover_title"]
        self.SECTION_HEAD_SIZE = t["section_head"]
        self.BODY_SIZE = t["body"]
        self.TABLE_HEAD_SIZE = t["table_head"]
        self.TABLE_BODY_SIZE = t["table_body"]
        # Header label
        self.HEADER_LABEL = tokens["header_label"]

    @staticmethod
    def _hex_to_rgb(hex_str):
        """Converts #RRGGBB to (R, G, B) tuple."""
        hex_str = hex_str.lstrip('#')
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

    def build_styles(self):
        """Returns (title_style, section_style, body_style) for this mode."""
        base = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ReportTitle', parent=base['Heading1'],
            fontSize=self.COVER_TITLE_SIZE, textColor=self.PRIMARY,
            alignment=TA_CENTER, spaceAfter=20, fontName="Helvetica-Bold"
        )
        section_style = ParagraphStyle(
            'SectionHeader', parent=base['Heading2'],
            fontSize=self.SECTION_HEAD_SIZE, textColor=self.PRIMARY,
            alignment=TA_LEFT, spaceBefore=12, spaceAfter=8,
            fontName="Helvetica-Bold",
            borderPadding=(0, 0, 4, 0), borderWidth=0, borderColor=self.PRIMARY
        )
        body_style = ParagraphStyle(
            'BodyText', parent=base['Normal'],
            fontSize=self.BODY_SIZE, textColor=self.TEXT,
            alignment=TA_JUSTIFY, spaceAfter=8, leading=self.BODY_SIZE + 4,
            fontName="Helvetica"
        )
        return title_style, section_style, body_style

    # ── Reusable table builder ──────────────────────────────────────

    def build_table(self, headers, rows, col_widths, total_indices=None,
                    subtotal_indices=None, num_cols_start=1, wrap_style=None):
        """
        Build a professionally styled financial table.
        
        Args:
            headers: list of header strings
            rows: list of row-lists (same length as headers)
            col_widths: list of column widths
            total_indices: row indices (0-based from data, not header) to highlight as totals
            subtotal_indices: row indices to highlight as subtotals
            num_cols_start: column index from which to right-align (numeric columns)
            wrap_style: ParagraphStyle for wrapping text cells; if None, no wrapping
        """
        total_indices = total_indices or []
        subtotal_indices = subtotal_indices or []

        # Build header row
        if wrap_style:
            hdr_row = []
            for h in headers:
                if isinstance(h, Paragraph):
                    hdr_row.append(h)
                else:
                    hdr_row.append(Paragraph(f"<b>{h}</b>", ParagraphStyle(
                        'TblHdr', parent=wrap_style, fontSize=self.TABLE_HEAD_SIZE,
                        fontName='Helvetica-Bold', textColor=self.HEADER_FG,
                        leading=self.TABLE_HEAD_SIZE + 3
                    )))
        else:
            hdr_row = headers

        # Build data rows
        data = [hdr_row]
        cell_style = ParagraphStyle(
            'TblCell', parent=getSampleStyleSheet()['Normal'],
            fontSize=self.TABLE_BODY_SIZE, fontName='Helvetica',
            textColor=self.TEXT, leading=self.TABLE_BODY_SIZE + 3
        ) if wrap_style else None

        for row in rows:
            wrapped = []
            for ci, cell in enumerate(row):
                cell_str = str(cell)
                # Render simple tags if present, otherwise treat as plain text Paragraph
                p_style = cell_style if cell_style else ParagraphStyle('Cell', fontSize=self.TABLE_BODY_SIZE, leading=self.TABLE_BODY_SIZE+2)
                wrapped.append(Paragraph(cell_str, p_style))
            data.append(wrapped)

        t = Table(data, colWidths=col_widths, repeatRows=1)

        # Base style commands
        cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), self.HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.HEADER_FG),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), self.TABLE_HEAD_SIZE),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), self.TABLE_BODY_SIZE),
            ('GRID', (0, 0), (-1, -1), 0.3, self.BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]

        # Right-align numeric columns
        if num_cols_start < len(headers):
            cmds.append(('ALIGN', (num_cols_start, 1), (-1, -1), 'RIGHT'))
            cmds.append(('ALIGN', (num_cols_start, 0), (-1, 0), 'CENTER'))

        # Alternating row bands (data rows only, 1-indexed because row 0 is header)
        for i in range(len(rows)):
            if i % 2 == 1:
                cmds.append(('BACKGROUND', (0, i + 1), (-1, i + 1), self.BAND_ODD))

        # Total row highlighting
        for ti in total_indices:
            ri = ti + 1  # offset for header
            cmds.append(('BACKGROUND', (0, ri), (-1, ri), self.TOTAL_BG))
            cmds.append(('FONTNAME', (0, ri), (-1, ri), 'Helvetica-Bold'))

        # Subtotal row highlighting
        for si in subtotal_indices:
            ri = si + 1
            cmds.append(('FONTNAME', (0, ri), (-1, ri), 'Helvetica-Bold'))

        t.setStyle(TableStyle(cmds))
        return t


# ── Theme Definitions ──────────────────────────────────────────────

_THEME_MAP = {
    "lite": {
        "primary": "#1565C0",
        "secondary": "#42A5F5",
        "accent": "#26A69A",
        "header_bg": "#E3F2FD",
        "header_fg": "#0D47A1",
        "band_odd": "#F5F9FF",
        "total_bg": "#E8F5E9",
        "border": "#CFD8DC",
        "text": "#212121",
        "muted": "#757575",
        "header_label": "Project Report",
        "typo": {
            "cover_title": 22,
            "section_head": 13,
            "body": 10.5,
            "table_head": 9,
            "table_body": 9,
        },
    },
    "pro": {
        "primary": "#0D47A1",
        "secondary": "#1976D2",
        "accent": "#FFC107",
        "header_bg": "#0D47A1",
        "header_fg": "#FFFFFF",
        "band_odd": "#F8F9FA",
        "total_bg": "#E3F2FD",
        "border": "#BDBDBD",
        "text": "#212121",
        "muted": "#757575",
        "header_label": "Detailed Project Report (DPR)",
        "typo": {
            "cover_title": 28,
            "section_head": 16,
            "body": 11,
            "table_head": 10,
            "table_body": 9.5,
        },
    },
    "cma": {
        "primary": "#263238",
        "secondary": "#455A64",
        "accent": "#FF8F00",
        "header_bg": "#37474F",
        "header_fg": "#FFFFFF",
        "band_odd": "#F0F0F0",
        "total_bg": "#FFF3E0",
        "border": "#90A4AE",
        "text": "#212121",
        "muted": "#607D8B",
        "header_label": "CMA Data & Analysis",
        "typo": {
            "cover_title": 20,
            "section_head": 12,
            "body": 10,
            "table_head": 9,
            "table_body": 8.5,
        },
    },
}


def get_theme(report_mode_value: str) -> ModeTheme:
    """Returns the appropriate ModeTheme for the given ReportMode value string."""
    from services.cma.models import ReportMode
    if report_mode_value == ReportMode.LITE.value:
        return ModeTheme("lite")
    elif report_mode_value == ReportMode.CMA.value:
        return ModeTheme("cma")
    else:
        return ModeTheme("pro")
