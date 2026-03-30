"""Professional PDF report generator for trading analysis.

Uses fpdf2 to generate PDF reports with technical + fundamental analysis.
No system dependencies — works on Linux/GitHub Actions out of the box.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

logger = logging.getLogger(__name__)

# Map Unicode chars unsupported by Helvetica (Latin-1) to safe equivalents
_SANITIZE_MAP = str.maketrans({
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote (smart quote)
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u2013": "-",   # en dash
    "\u2014": "--",  # em dash
    "\u2026": "...", # ellipsis
    "\u2022": "-",   # bullet
    "\u00a0": " ",   # non-breaking space
    "\u20ac": "EUR", # euro sign
})


def _sanitize(text: str) -> str:
    """Replace Unicode chars that Helvetica (Latin-1) can't render."""
    return text.translate(_SANITIZE_MAP)

# Colors
DARK_BLUE = (25, 55, 95)
LIGHT_BLUE = (230, 240, 250)
GREEN = (34, 139, 34)
YELLOW_BG = (255, 248, 220)
RED = (180, 30, 30)
GRAY = (100, 100, 100)
LIGHT_GRAY = (240, 240, 240)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


class TradingReportPDF(FPDF):
    """Custom PDF with header and footer for trading reports."""

    def __init__(self, strategy_name: str, report_date: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.strategy_name = strategy_name
        self.report_date = report_date
        self.set_auto_page_break(auto=True, margin=20)

    def cell(self, *args, **kwargs):
        """Override to sanitize text for Latin-1 font compatibility."""
        args = list(args)
        for i, a in enumerate(args):
            if isinstance(a, str):
                args[i] = _sanitize(a)
        for k, v in kwargs.items():
            if isinstance(v, str):
                kwargs[k] = _sanitize(v)
        return super().cell(*args, **kwargs)

    def multi_cell(self, *args, **kwargs):
        """Override to sanitize text for Latin-1 font compatibility."""
        args = list(args)
        for i, a in enumerate(args):
            if isinstance(a, str):
                args[i] = _sanitize(a)
        for k, v in kwargs.items():
            if isinstance(v, str):
                kwargs[k] = _sanitize(v)
        return super().multi_cell(*args, **kwargs)

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*DARK_BLUE)
        self.cell(0, 8, self.strategy_name, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*GRAY)
        self.cell(0, 5, self.report_date, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*DARK_BLUE)
        self.set_line_width(0.5)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*GRAY)
        self.cell(
            0, 10,
            f"Multiday Trading Validator | Page {self.page_no()}/{{nb}}",
            align="C",
        )

    def _section_title(self, title: str, bg_color: tuple = DARK_BLUE):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(*bg_color)
        self.set_text_color(*WHITE)
        self.cell(0, 7, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*BLACK)
        self.ln(1)

    def _key_value(self, key: str, value: str, bold_value: bool = False):
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRAY)
        self.cell(40, 5, key)
        style = "B" if bold_value else ""
        self.set_font("Helvetica", style, 8)
        self.set_text_color(*BLACK)
        self.cell(0, 5, value, new_x="LMARGIN", new_y="NEXT")

    def _check_row(self, name: str, passed: bool, display: str):
        icon = "PASS" if passed else "FAIL"
        color = GREEN if passed else RED
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*color)
        self.cell(12, 5, icon)
        self.set_text_color(*BLACK)
        self.cell(25, 5, name)
        self.set_text_color(*GRAY)
        self.cell(0, 5, display, new_x="LMARGIN", new_y="NEXT")


def _add_ticker_section(
    pdf: TradingReportPDF,
    result: dict,
    config: dict,
    strategy: str,
) -> None:
    """Add a complete ticker analysis section to the PDF."""
    ticker = result["ticker"]
    status = result["status"]
    score = result["score"]
    max_score = result["max_score"]

    # Check if we need a new page (at least 80mm needed for a ticker section)
    if pdf.get_y() > 220:
        pdf.add_page()

    # --- Ticker header ---
    status_color = GREEN if status == "GO" else YELLOW_BG
    header_bg = (220, 245, 220) if status == "GO" else (255, 245, 200)
    pdf.set_fill_color(*header_bg)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*DARK_BLUE)

    rank_str = ""
    if result.get("rank", 0) > 0:
        rank_str = f"#{result['rank']} "

    pdf.cell(
        0, 8,
        f"  {rank_str}{ticker}    {status} {score}/{max_score}",
        fill=True, new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(2)

    # --- Technical Analysis ---
    pdf._section_title("Technical Analysis")

    checks = result.get("checks", {})
    for name, check in checks.items():
        pdf._check_row(name, check["passed"], check.get("display", ""))

    pdf._key_value("Entry Method", result.get("entry_method", "N/A"))
    pdf._key_value(
        "Premarket",
        f"{result.get('premarket_pct', 0):+.1f}%",
    )
    pdf.ln(2)

    # --- Fundamental Analysis ---
    ai = result.get("ai_analysis")
    if ai and ai.fundamental_score is not None:
        pdf._section_title("Fundamental Analysis", bg_color=(60, 120, 60))
        pdf._key_value(
            "Fundamental Score",
            f"{ai.fundamental_score}/5",
            bold_value=True,
        )
        pdf.ln(1)

        for dim_name, dim_data in ai.dimensions.items():
            label = dim_name.replace("_", " ").title()
            passed = dim_data.get("score", 0) == 1
            reason = dim_data.get("reason", "")
            pdf._check_row(label, passed, reason)

        pdf.ln(2)

        # AI Summary
        if ai.summary:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*GRAY)
            pdf.multi_cell(0, 4, f"AI: {ai.summary}")
            pdf.ln(2)
    elif ai and ai.error:
        pdf._section_title("Fundamental Analysis", bg_color=(60, 120, 60))
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*RED)
        pdf.cell(
            0, 5, f"AI analysis unavailable: {ai.error}",
            new_x="LMARGIN", new_y="NEXT",
        )
        pdf.ln(2)

    # --- News Digest ---
    news_items = result.get("news", [])
    if news_items:
        pdf._section_title("News Digest", bg_color=(80, 80, 120))
        for item in news_items[:3]:
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*GRAY)
            date_str = item.published.strftime("%m/%d %H:%M")
            pdf.cell(18, 4, date_str)
            pdf.set_text_color(*BLACK)
            # Truncate long titles
            title = item.title[:90] + "..." if len(item.title) > 90 else item.title
            pdf.cell(0, 4, title, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "I", 6)
            pdf.set_text_color(*GRAY)
            pdf.cell(18, 3, "")
            pdf.cell(0, 3, item.source, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # --- Event Flags ---
    events = result.get("events")
    if events:
        pdf._section_title("Event Risk", bg_color=(140, 80, 40))
        if events.earnings_within_window:
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*RED)
            pdf.cell(
                0, 5,
                f"WARNING: Earnings on {events.earnings_date}",
                new_x="LMARGIN", new_y="NEXT",
            )
        else:
            pdf._key_value("Earnings", "None within 5 sessions")

        if events.macro_events:
            for evt in events.macro_events[:3]:
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(*RED)
                pdf.cell(
                    0, 4,
                    f"  MACRO: {evt['name']} ({evt['country']}, {evt['date']})",
                    new_x="LMARGIN", new_y="NEXT",
                )
        else:
            pdf._key_value("Macro Events", "None within 3 sessions")
        pdf.ln(2)

    # --- Entry Parameters ---
    pdf._section_title("Entry Parameters", bg_color=(50, 50, 50))

    currency = "$" if not ticker.endswith(".MI") else "EUR "
    close = result.get("last_close", 0)
    size = result.get("position_size", 0)
    leverage = config.get("position_sizing", {}).get("leverage", 5)
    notional = size * close if close > 0 else 0
    margin = notional / leverage if leverage > 0 else notional

    pdf._key_value("Stop Loss", f"{currency}{result.get('stop_loss', 0):.2f}")
    pdf._key_value("TP1", f"{currency}{result.get('tp1_price', 0):.2f}")
    pdf._key_value("Trailing Stop", f"{currency}{result.get('chandelier_stop', 0):.2f}")
    pdf._key_value("Position Size", f"{size} shares")
    pdf._key_value("Notional", f"{currency}{notional:,.0f}")
    pdf._key_value("Margin", f"{currency}{margin:,.0f}")
    pdf.ln(4)

    # Separator line
    pdf.set_draw_color(*LIGHT_GRAY)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)


def generate_report(
    results: list[dict],
    config: dict,
    strategy_name: str,
    output_dir: str,
) -> str | None:
    """Generate a PDF analysis report for GO/WATCH tickers.

    Args:
        results: List of enriched result dicts (with news, events, ai_analysis fields).
        config: Strategy config dict.
        strategy_name: "ITA CFD" or "US S&P 500 CFD".
        output_dir: Directory to save the PDF.

    Returns:
        File path of generated PDF, or None on failure.
    """
    actionable = [r for r in results if r["status"] in ("GO", "WATCH")]
    if not actionable:
        logger.info("No GO/WATCH tickers, skipping PDF report")
        return None

    try:
        now = datetime.now(timezone.utc)
        report_date = now.strftime("%Y-%m-%d %H:%M UTC")
        date_str = now.strftime("%Y-%m-%d")

        pdf = TradingReportPDF(
            strategy_name=f"{strategy_name} Analysis Report",
            report_date=report_date,
        )
        pdf.alias_nb_pages()
        pdf.add_page()

        # --- Gate summary ---
        if actionable:
            gates = actionable[0].get("gates", {})
            pdf.set_font("Helvetica", "", 9)
            vix = gates.get("vix_value", 0)
            vix_ok = gates.get("vix_ok", True)
            adx = gates.get("adx_value", 0)
            adx_ok = gates.get("adx_ok", True)

            pdf.set_text_color(*BLACK)
            vix_status = "OK" if vix_ok else "HIGH"
            adx_status = "OK" if adx_ok else "LOW"
            pdf.cell(
                0, 6,
                f"Gates:  VIX {vix:.1f} ({vix_status})  |  ADX {adx:.1f} ({adx_status})",
                new_x="LMARGIN", new_y="NEXT",
            )

            # Count summary
            go_count = sum(1 for r in results if r["status"] == "GO")
            watch_count = sum(1 for r in results if r["status"] == "WATCH")
            skip_count = sum(1 for r in results if r["status"] == "SKIP")
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(
                0, 6,
                f"{go_count} GO  |  {watch_count} WATCH  |  {skip_count} SKIP",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.ln(4)

        # --- Per-ticker sections ---
        for r in actionable:
            _add_ticker_section(pdf, r, config, strategy_name)

        # --- Save ---
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f"{date_str}_analysis.pdf")
        pdf.output(filepath)

        logger.info("PDF report saved: %s", filepath)
        return filepath

    except Exception as e:
        logger.error("PDF report generation failed: %s", e)
        return None
