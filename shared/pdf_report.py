"""Generate clean PDF reports for ITA, US, and ETF strategies.

Uses fpdf2 to produce table-based PDF documents suitable for
Telegram delivery.
"""

import os
import tempfile
from datetime import datetime

from fpdf import FPDF


# ── Colours ──────────────────────────────────────────────────────────────
_GREEN = (34, 139, 34)
_RED = (200, 30, 30)
_YELLOW = (200, 160, 0)
_GREY = (120, 120, 120)
_WHITE = (255, 255, 255)
_HEADER_BG = (40, 60, 90)
_ROW_ALT = (240, 245, 250)
_ROW_NORMAL = (255, 255, 255)


def _pass_fail(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _status_colour(status: str):
    return {"GO": _GREEN, "WATCH": _YELLOW, "SKIP": _RED}.get(status, _GREY)


class _ReportPDF(FPDF):
    """Base PDF with shared header/footer styling."""

    title_text: str = ""
    date_text: str = ""

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(255, 255, 255)
        self.set_fill_color(*_HEADER_BG)
        self.cell(0, 10, self.title_text, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*_GREY)
        self.cell(0, 6, self.date_text, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*_GREY)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    # ── helpers ───────────────────────────────────────────────────────
    def _section_title(self, text: str):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(30, 30, 30)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def _gate_line(self, label: str, value, ok: bool):
        self.set_font("Helvetica", "", 9)
        colour = _GREEN if ok else _RED
        status = "OK" if ok else ("HIGH" if "VIX" in label else "LOW")
        self.set_text_color(*colour)
        self.cell(0, 5, f"  {label}: {value}  {status}", new_x="LMARGIN", new_y="NEXT")

    def _summary_line(self, go: int, watch: int, skip: int):
        self.ln(3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*_GREEN)
        self.cell(25, 6, f"{go} GO")
        self.set_text_color(*_YELLOW)
        self.cell(35, 6, f"{watch} WATCH")
        self.set_text_color(*_RED)
        self.cell(25, 6, f"{skip} SKIP", new_x="LMARGIN", new_y="NEXT")

    def _table_header(self, columns: list[tuple[str, int]]):
        self.set_font("Helvetica", "B", 7)
        self.set_fill_color(*_HEADER_BG)
        self.set_text_color(*_WHITE)
        for col_name, col_w in columns:
            self.cell(col_w, 6, col_name, border=1, align="C", fill=True)
        self.ln()

    def _table_row(self, values: list[str], widths: list[int], row_idx: int,
                   status: str = ""):
        bg = _ROW_ALT if row_idx % 2 == 0 else _ROW_NORMAL
        self.set_fill_color(*bg)
        self.set_font("Helvetica", "", 7)
        for i, (val, w) in enumerate(zip(values, widths)):
            # Colour the status column
            if i == len(values) - 1 and status:
                self.set_text_color(*_status_colour(status))
            else:
                self.set_text_color(30, 30, 30)
            self.cell(w, 5, val, border=1, align="C", fill=True)
        self.ln()

    def _copyable_block(self, title: str, text: str):
        """Render a monospaced, markdown-style text block easy to copy."""
        # Strip consecutive blank lines → single blank line, trim edges
        lines: list[str] = []
        prev_blank = False
        for raw in text.split("\n"):
            stripped = raw.strip()
            if not stripped:
                if not prev_blank:
                    lines.append("")
                prev_blank = True
            else:
                lines.append(raw)
                prev_blank = False

        # Start on a new page
        self.add_page()
        self._section_title(title)
        self.ln(1)
        # Light grey background box
        self.set_fill_color(245, 245, 245)
        self.set_draw_color(200, 200, 200)
        self.set_font("Courier", "", 7.5)
        self.set_text_color(30, 30, 30)

        x0 = self.get_x()
        page_w = self.w - self.l_margin - self.r_margin
        line_h = 3.5

        for line in lines:
            if self.get_y() + line_h > self.h - self.b_margin:
                self.add_page()
                self.set_fill_color(245, 245, 245)
                self.set_draw_color(200, 200, 200)
                self.set_font("Courier", "", 7.5)
                self.set_text_color(30, 30, 30)
            self.set_x(x0)
            self.cell(page_w, line_h, line, fill=True,
                      new_x="LMARGIN", new_y="NEXT")


# ═════════════════════════════════════════════════════════════════════════
# ITA PDF
# ═════════════════════════════════════════════════════════════════════════

def generate_ita_pdf(results: list[dict], config: dict) -> str:
    """Generate ITA CFD PDF report. Returns path to temp PDF file."""
    tz = config["session"]["timezone"]
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo(tz))
    except Exception:
        now = datetime.now()

    pdf = _ReportPDF("L", "mm", "A4")
    pdf.title_text = "ITA CFD Report"
    pdf.date_text = now.strftime("%Y-%m-%d %H:%M %Z")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Gates
    if results:
        gates = results[0].get("gates", {})
        pdf._section_title("Gates")
        pdf._gate_line("VIX", f"{gates.get('vix_value', 0):.1f}", gates.get("vix_ok", True))
        benchmark = config.get("benchmark", "ETFMIB.MI")
        pdf._gate_line(f"ADX ({benchmark})", f"{gates.get('adx_value', 0):.1f}",
                       gates.get("adx_ok", True))
        pdf.ln(3)

    # Position sizing
    ps = config.get("position_sizing", {})
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_GREY)
    capital = ps.get("capital", 1000)
    leverage = ps.get("leverage", 5)
    risk_pct = ps.get("risk_per_trade", 0.02)
    pdf.cell(0, 5,
             f"Capital: {capital:,.0f} EUR | Risk/trade: {risk_pct*100:.1f}% | "
             f"Leverage: {leverage}:1",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Sort: GO > WATCH > SKIP, then by score desc — keep only top 5
    status_order = {"GO": 0, "WATCH": 1, "SKIP": 2}
    sorted_results = sorted(
        results,
        key=lambda r: (status_order.get(r["status"], 9), -r["score"]),
    )
    top5 = sorted_results[:5]

    # Table
    cols = [
        ("#", 8), ("Stock", 18), ("Score", 12), ("EMA D", 12), ("EMA W", 12),
        ("MACD", 12), ("RSI", 14), ("MFI", 14), ("RS", 12),
        ("Premkt", 16), ("Stop", 18), ("TP1", 18), ("Trail", 18),
        ("Size", 14), ("Entry", 20), ("Status", 17),
    ]
    widths = [c[1] for c in cols]

    pdf._section_title("Top 5 Results")
    pdf._table_header(cols)

    for i, r in enumerate(top5):
        checks = r["checks"]
        values = [
            str(i + 1),
            r["ticker"],
            f"{r['score']}/{r['max_score']}",
            _pass_fail(checks["EMA D"]["passed"]),
            _pass_fail(checks["EMA W"]["passed"]),
            _pass_fail(checks["MACD"]["passed"]),
            _pass_fail(checks["RSI"]["passed"]),
            _pass_fail(checks["MFI"]["passed"]),
            _pass_fail(checks["RS"]["passed"]),
            f"{r['premarket_pct']:+.2f}%",
            f"{r['stop_loss']:.2f}" if r["stop_loss"] > 0 else "N/A",
            f"{r['tp1_price']:.2f}" if r["tp1_price"] > 0 else "N/A",
            f"{r['chandelier_stop']:.2f}" if r["chandelier_stop"] > 0 else "N/A",
            str(r["position_size"]) if r["position_size"] > 0 else "N/A",
            r["entry_method"],
            r["status"],
        ]
        pdf._table_row(values, widths, i, status=r["status"])

    # Summary
    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    pdf._summary_line(go, watch, skip)

    # Action plan for top-5 GO/WATCH tickers
    actionable = [r for r in top5 if r["status"] in ("GO", "WATCH") and r["entry_method"] != "WAIT"]
    if actionable:
        pdf.ln(4)
        pdf._section_title("Action Plan")
        pdf.set_font("Helvetica", "", 8)
        for r in actionable:
            colour = _GREEN if r["status"] == "GO" else _YELLOW
            pdf.set_text_color(*colour)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(0, 5, f"{r['ticker']} - {r['entry_method']}",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30, 30, 30)
            pdf.set_font("Helvetica", "", 8)
            close = r.get("last_close", 0)
            notional = r["position_size"] * close
            margin = notional / leverage if leverage > 0 else notional
            pdf.cell(0, 4,
                     f"  Close: {close:.2f} | SL: {r['stop_loss']:.2f} | "
                     f"TP1: {r['tp1_price']:.2f} | Trail: {r['chandelier_stop']:.2f}",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.cell(0, 4,
                     f"  {r['position_size']} shares | {notional:,.0f} EUR notional | "
                     f"{margin:,.0f} EUR margin",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    # Perplexity prompt (copy-friendly) — only for top-5 GO/WATCH
    prompt_tickers = [r for r in top5 if r["status"] in ("GO", "WATCH")]
    if prompt_tickers:
        prompt = _build_ita_perplexity_prompt(prompt_tickers)
        pdf._copyable_block("Perplexity Prompt  (copy & paste)", prompt)

    # Save
    out_dir = config.get("output", {}).get("csv_dir", "output/reports_ita")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, now.strftime("%Y-%m-%d") + ".pdf")
    pdf.output(path)
    return path


def _build_ita_perplexity_prompt(actionable: list[dict]) -> str:
    """Build the ITA Perplexity deep-dive prompt as plain markdown text."""
    ticker_lines = []
    for r in actionable:
        checks = r["checks"]
        failed = [n for n, c in checks.items() if not c["passed"]]
        fail_str = f" (manca: {', '.join(failed)})" if failed else ""
        ticker_lines.append(
            f"- {r['ticker']} {r['status']} {r['score']}/6{fail_str} | "
            f"{r.get('last_close', 0):.2f} | SL {r['stop_loss']:.2f}"
        )
    tickers_str = "\n".join(ticker_lines)

    return (
        "Cerca notizie in tempo reale. Sei un analista rischio su azioni italiane FTSE MIB.\n"
        "\n"
        "Il mio screening tecnico automatico ha selezionato questi titoli "
        "per CFD multiday (3-7 sessioni, leva 5:1 broker):\n"
        f"{tickers_str}\n"
        "\n"
        "I tecnici sono validati. Cerca SOLO deal-breaker fondamentali che il tecnico non vede.\n"
        "Per ogni titolo rispondi:\n"
        "\n"
        "1. EARNINGS: Pubblica trimestrali nei prossimi 7gg? SI (data) = veto / NO\n"
        "2. CATALYST: Catalyst attivo ultime 48h? Gambe multiday o prezzato?\n"
        "   ATTIVO (motivo) / DEBOLE / NESSUNO\n"
        "3. EVENTO KILLER 48h: Evento specifico (BCE, asta BTP, dato macro,\n"
        "   ex-dividendo, scadenza tecnica) che puo invertire prima del TP1?\n"
        "   SI (evento + data) / NO\n"
        "\n"
        "Output (una riga per titolo):\n"
        "[ticker.MI] | Earnings: SI/NO | Catalyst: ATTIVO/DEBOLE/NESSUNO | Evento: SI/NO\n"
        "Verdetto: ENTRY / WAIT / SKIP + motivo (max 10 parole)\n"
        "\n"
        "Regole:\n"
        "- Earnings = SKIP automatico\n"
        "- Nessun catalyst + Evento = SKIP\n"
        "- Catalyst debole = WAIT\n"
        "- Catalyst attivo + No evento = ENTRY\n"
        "- Bancari (ISP, UCG, BPE, FBK, MB): nota spread BTP-Bund se >5bp"
    )


# ═════════════════════════════════════════════════════════════════════════
# US PDF
# ═════════════════════════════════════════════════════════════════════════

def generate_us_pdf(results: list[dict], config: dict) -> str:
    """Generate US S&P 500 CFD PDF report. Returns path to temp PDF file."""
    tz = config["session"]["timezone"]
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo(tz))
    except Exception:
        now = datetime.now()

    pdf = _ReportPDF("L", "mm", "A4")
    pdf.title_text = "US S&P 500 CFD Report"
    pdf.date_text = now.strftime("%Y-%m-%d %H:%M %Z")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Gates
    if results:
        gates = results[0].get("gates", {})
        pdf._section_title("Gates")
        pdf._gate_line("VIX", f"{gates.get('vix_value', 0):.1f}", gates.get("vix_ok", True))
        benchmark = config.get("benchmark", "SPY")
        pdf._gate_line(f"ADX ({benchmark})", f"{gates.get('adx_value', 0):.1f}",
                       gates.get("adx_ok", True))
        pdf.ln(3)

    # Position sizing
    ps = config.get("position_sizing", {})
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_GREY)
    capital = ps.get("capital", 1000)
    leverage = ps.get("leverage", 5)
    risk_pct = ps.get("risk_per_trade", 0.02)
    pdf.cell(0, 5,
             f"Capital: ${capital:,.0f} | Risk/trade: {risk_pct*100:.1f}% | "
             f"Leverage: {leverage}:1",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Top 5: prefer ranked tickers, fall back to top 5 by status/score
    top_n = config.get("alerts", {}).get("top_n", 5)
    ranked = sorted(
        [r for r in results if r.get("rank", 0) > 0],
        key=lambda r: r["rank"],
    )
    if ranked:
        top5 = ranked[:top_n]
    else:
        status_order = {"GO": 0, "WATCH": 1, "SKIP": 2}
        top5 = sorted(
            results,
            key=lambda r: (status_order.get(r["status"], 9), -r["score"]),
        )[:top_n]

    # Table
    cols = [
        ("#", 8), ("Stock", 16), ("Score", 12), ("EMA D", 12), ("EMA W", 12),
        ("MACD", 12), ("RSI", 14), ("MFI", 14), ("RS", 12), ("RS%", 14),
        ("Premkt", 16), ("Stop", 16), ("TP1", 16), ("Trail", 16),
        ("Size", 12), ("Entry", 18), ("Status", 15),
    ]
    widths = [c[1] for c in cols]

    pdf._section_title(f"Top {len(top5)} Results")
    pdf._table_header(cols)

    for i, r in enumerate(top5):
        rank = r.get("rank", 0) or (i + 1)
        checks = r["checks"]
        rs_pct = f"{r.get('rs_value', 0):+.1f}%" if r.get("rs_value") else ""
        values = [
            str(rank) if rank > 0 else "",
            r["ticker"],
            f"{r['score']}/{r['max_score']}",
            _pass_fail(checks["EMA D"]["passed"]),
            _pass_fail(checks["EMA W"]["passed"]),
            _pass_fail(checks["MACD"]["passed"]),
            _pass_fail(checks["RSI"]["passed"]),
            _pass_fail(checks["MFI"]["passed"]),
            _pass_fail(checks["RS"]["passed"]),
            rs_pct,
            f"{r['premarket_pct']:+.2f}%",
            f"{r['stop_loss']:.2f}" if r["stop_loss"] > 0 else "N/A",
            f"{r['tp1_price']:.2f}" if r["tp1_price"] > 0 else "N/A",
            f"{r['chandelier_stop']:.2f}" if r["chandelier_stop"] > 0 else "N/A",
            str(r["position_size"]) if r["position_size"] > 0 else "N/A",
            r["entry_method"],
            r["status"],
        ]
        pdf._table_row(values, widths, i, status=r["status"])

    # Summary
    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    pdf._summary_line(go, watch, skip)

    # Action plan for top-5 tickers
    ranked = [r for r in top5 if r["status"] in ("GO", "WATCH") and r["entry_method"] != "WAIT"]
    if ranked:
        pdf.ln(4)
        pdf._section_title("Action Plan (Top Ranked)")
        pdf.set_font("Helvetica", "", 8)
        for r in ranked:
            colour = _GREEN if r["status"] == "GO" else _YELLOW
            pdf.set_text_color(*colour)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(0, 5, f"#{r['rank']} {r['ticker']} - {r['entry_method']}",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30, 30, 30)
            pdf.set_font("Helvetica", "", 8)
            close = r.get("last_close", 0)
            notional = r["position_size"] * close
            margin = notional / leverage if leverage > 0 else notional
            pdf.cell(0, 4,
                     f"  Close: ${close:.2f} | SL: ${r['stop_loss']:.2f} | "
                     f"TP1: ${r['tp1_price']:.2f} | Trail: ${r['chandelier_stop']:.2f}",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.cell(0, 4,
                     f"  {r['position_size']} shares | ${notional:,.0f} notional | "
                     f"${margin:,.0f} margin",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    # Perplexity prompt (copy-friendly) — only for top-5 GO/WATCH
    prompt_tickers = [r for r in top5 if r["status"] in ("GO", "WATCH")]
    if prompt_tickers:
        prompt = _build_us_perplexity_prompt(prompt_tickers)
        pdf._copyable_block("Perplexity Prompt  (copy & paste)", prompt)

    # Save
    out_dir = config.get("output", {}).get("csv_dir", "output/reports_us")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, now.strftime("%Y-%m-%d") + ".pdf")
    pdf.output(path)
    return path


def _build_us_perplexity_prompt(actionable: list[dict]) -> str:
    """Build the US Perplexity deep-dive prompt as plain markdown text."""
    ticker_lines = []
    for r in actionable:
        checks = r["checks"]
        failed = [n for n, c in checks.items() if not c["passed"]]
        fail_str = f" (miss: {', '.join(failed)})" if failed else ""
        ticker_lines.append(
            f"- {r['ticker']} {r['status']} {r['score']}/6{fail_str} | "
            f"${r.get('last_close', 0):.2f} | SL ${r['stop_loss']:.2f}"
        )
    tickers_str = "\n".join(ticker_lines)

    return (
        "Search real-time news. You are a risk analyst covering US large-cap equities (S&P 500).\n"
        "\n"
        "My automated technical screener selected these stocks for CFD "
        "multiday swing trades (3-7 sessions, 5:1 leverage via broker):\n"
        f"{tickers_str}\n"
        "\n"
        "Technicals are validated. Find ONLY fundamental deal-breakers that technicals cannot see.\n"
        "For each stock:\n"
        "\n"
        "1. EARNINGS: Reports earnings in next 7 trading days? YES (date) = veto / NO\n"
        "2. CATALYST: Active catalyst in last 48h? Multi-day legs or priced in?\n"
        "   ACTIVE (reason) / FADING / NONE\n"
        "3. KILLER EVENT next 48h: Specific event (FOMC, CPI, NFP, PPI,\n"
        "   ex-dividend, antitrust) that could reverse before TP1?\n"
        "   YES (event + date) / NO\n"
        "\n"
        "Output (one line per stock):\n"
        "[TICKER] | Earnings: YES/NO | Catalyst: ACTIVE/FADING/NONE | Event: YES/NO\n"
        "Verdict: ENTRY / WAIT / SKIP + reason (max 10 words)\n"
        "\n"
        "Rules:\n"
        "- Earnings = SKIP automatic\n"
        "- No catalyst + Event = SKIP\n"
        "- Fading catalyst = WAIT\n"
        "- Active catalyst + No event = ENTRY\n"
        "- Rate-sensitive (banks, REITs, utilities): note 10Y yield move"
    )


# ═════════════════════════════════════════════════════════════════════════
# ETF PDF
# ═════════════════════════════════════════════════════════════════════════

def generate_etf_pdf(results: list[dict], config: dict,
                     correlations: dict) -> str:
    """Generate ETF PDF report. Returns path to temp PDF file."""
    tz = config["session"]["timezone"]
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo(tz))
    except Exception:
        now = datetime.now()

    pdf = _ReportPDF("L", "mm", "A4")
    pdf.title_text = "ETF Sector Report"
    pdf.date_text = now.strftime("%Y-%m-%d %H:%M %Z")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Gates
    if results:
        gates = results[0].get("gates", {})
        benchmark = config.get("benchmark", "CSSPX.MI")
        pdf._section_title("Gates")
        pdf._gate_line("VIX", f"{gates.get('vix_value', 0):.1f}", gates.get("vix_ok", True))
        bench_ok = gates.get("bench_ok", True)
        pdf._gate_line(f"Benchmark ({benchmark})",
                       "Uptrend" if bench_ok else "Downtrend", bench_ok)
        pdf._gate_line("ADX", f"{gates.get('adx_value', 0):.1f}", gates.get("adx_ok", True))

        if correlations.get("any_correlated"):
            pdf.set_text_color(*_YELLOW)
            pdf.set_font("Helvetica", "B", 9)
            for t1, t2, corr in correlations["correlated_pairs"]:
                pdf.cell(0, 5, f"  CORRELATION: {t1}/{t2} = {corr}",
                         new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    # Position sizing
    ps = config.get("position_sizing", {})
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_GREY)
    capital = ps.get("capital", 4000)
    risk_pct = ps.get("risk_per_trade", 0.015)
    commission = ps.get("commission", 2.95)
    pdf.cell(0, 5,
             f"Capital: {capital:,.0f} EUR | Risk/trade: {risk_pct*100:.1f}% | "
             f"Commission: {commission:.2f} EUR/trade",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Table
    cols = [
        ("ETF", 22), ("Score", 14), ("EMA D", 14), ("EMA W", 14),
        ("MACD", 14), ("RSI", 16), ("MFI", 16), ("RS", 14),
        ("Premkt", 18), ("Stop", 20), ("TP1", 20), ("Trail", 20),
        ("Size", 16), ("Status", 19),
    ]
    widths = [c[1] for c in cols]

    pdf._section_title("Results")
    pdf._table_header(cols)

    for i, r in enumerate(results):
        checks = r["checks"]
        gate_info = f" ({','.join(r['gate_reasons'])})" if r.get("gate_reasons") else ""
        values = [
            r["ticker"],
            f"{r['score']}/{r['max_score']}",
            _pass_fail(checks["EMA D"]["passed"]),
            _pass_fail(checks["EMA W"]["passed"]),
            _pass_fail(checks["MACD"]["passed"]),
            _pass_fail(checks["RSI"]["passed"]),
            _pass_fail(checks["MFI"]["passed"]),
            _pass_fail(checks["RS"]["passed"]),
            f"{r['premarket_pct']:+.2f}%",
            f"{r['stop_loss']:.2f}" if r["stop_loss"] > 0 else "N/A",
            f"{r['tp1_price']:.2f}" if r["tp1_price"] > 0 else "N/A",
            f"{r['chandelier_stop']:.2f}" if r["chandelier_stop"] > 0 else "N/A",
            str(r["position_size"]) if r["position_size"] > 0 else "N/A",
            r["status"] + gate_info,
        ]
        pdf._table_row(values, widths, i, status=r["status"])

    # Summary
    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    pdf._summary_line(go, watch, skip)

    # Action plan for GO
    go_etfs = [r for r in results if r["status"] == "GO"]
    if go_etfs:
        pdf.ln(4)
        pdf._section_title("Action Plan")
        pdf.set_font("Helvetica", "", 8)
        for r in go_etfs:
            pdf.set_text_color(*_GREEN)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(0, 5, f"{r['ticker']} - BUY",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30, 30, 30)
            pdf.set_font("Helvetica", "", 8)
            close = r.get("last_close", 0)
            notional = r["position_size"] * close
            pdf.cell(0, 4,
                     f"  Close: {close:.2f} EUR | SL: {r['stop_loss']:.2f} | "
                     f"TP1: {r['tp1_price']:.2f} | Trail: {r['chandelier_stop']:.2f}",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.cell(0, 4,
                     f"  {r['position_size']} shares | {notional:,.0f} EUR | "
                     f"Comm: {commission * 2:.2f} EUR RT",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    # Save
    out_dir = config.get("output", {}).get("csv_dir", "output/reports_etf")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, now.strftime("%Y-%m-%d") + ".pdf")
    pdf.output(path)
    return path
