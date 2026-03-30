"""Send reports to Telegram via Bot API.

Reads config from environment variables:
  TELEGRAM_BOT_TOKEN  — token from @BotFather
  TELEGRAM_CHAT_ID    — your chat/group ID

If either is missing, sending is silently skipped.
"""

import json
import logging
import os
import uuid
import urllib.request
import urllib.error

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def is_configured() -> bool:
    return bool(BOT_TOKEN and CHAT_ID)


TELEGRAM_MAX_LENGTH = 4096


def _send_single(text: str, parse_mode: str) -> bool:
    """Send a single message (must be <= TELEGRAM_MAX_LENGTH)."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True
            logger.warning("Telegram API returned %d", resp.status)
            return False
    except urllib.error.URLError as e:
        logger.warning("Telegram send failed: %s", e)
        return False


def _split_message(text: str, max_len: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """Split a long message into chunks that respect Telegram's limit.

    Splits on blank lines (paragraph boundaries) first, then on newlines.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current = ""

    # Split on double-newline (paragraph) boundaries
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_len:
            current = candidate
        elif not current:
            # Single paragraph exceeds limit — split on newlines
            for line in para.split("\n"):
                line_candidate = f"{current}\n{line}" if current else line
                if len(line_candidate) <= max_len:
                    current = line_candidate
                else:
                    if current:
                        chunks.append(current)
                    current = line[:max_len]
            pass
        else:
            chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    return chunks


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message to the configured Telegram chat.

    Automatically splits messages exceeding Telegram's 4096 char limit.
    Returns True if all chunks were sent successfully.
    """
    if not is_configured():
        logger.debug("Telegram not configured, skipping")
        return False

    chunks = _split_message(text)
    all_ok = True
    for i, chunk in enumerate(chunks):
        ok = _send_single(chunk, parse_mode)
        if ok:
            logger.info("Telegram message sent (%d/%d)", i + 1, len(chunks))
        else:
            all_ok = False
    return all_ok


def send_document(file_path: str, caption: str = "") -> bool:
    """Send a file (e.g. PDF) to the configured Telegram chat via sendDocument API."""
    if not is_configured():
        logger.debug("Telegram not configured, skipping document send")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    boundary = uuid.uuid4().hex

    with open(file_path, "rb") as f:
        file_data = f.read()

    filename = os.path.basename(file_path)

    # Build multipart/form-data body
    body = b""
    # chat_id field
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
    body += f"{CHAT_ID}\r\n".encode()
    # caption field
    if caption:
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
        body += f"{caption}\r\n".encode()
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="parse_mode"\r\n\r\n'
        body += b"HTML\r\n"
    # document field
    body += f"--{boundary}\r\n".encode()
    body += (
        f'Content-Disposition: form-data; name="document"; '
        f'filename="{filename}"\r\n'
    ).encode()
    body += b"Content-Type: application/pdf\r\n\r\n"
    body += file_data
    body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                logger.info("Telegram document sent: %s", filename)
                return True
            logger.warning("Telegram sendDocument returned %d", resp.status)
            return False
    except urllib.error.URLError as e:
        logger.warning("Telegram document send failed: %s", e)
        return False


def send_ita_report(results: list[dict], config: dict) -> bool:
    """Format and send ITA CFD report to Telegram."""
    lines = ["<b>ITA CFD Report</b>", ""]

    if results:
        gates = results[0].get("gates", {})
        vix = gates.get("vix_value", 0)
        vix_ok = gates.get("vix_ok", True)
        adx = gates.get("adx_value", 0)
        adx_ok = gates.get("adx_ok", True)
        lines.append(
            f"Gates: VIX {vix} {'OK' if vix_ok else 'HIGH'} | "
            f"ADX {adx} {'OK' if adx_ok else 'LOW'}"
        )
        lines.append("")

    go_results = [r for r in results if r["status"] == "GO"]
    watch_results = [r for r in results if r["status"] == "WATCH"]
    skip_results = [r for r in results if r["status"] == "SKIP"]

    if go_results:
        lines.append(f"<b>GO ({len(go_results)})</b>")
        for r in go_results:
            _append_ita_ticker(lines, r, config)
        lines.append("")

    if watch_results:
        lines.append(f"<b>WATCH ({len(watch_results)})</b>")
        for r in watch_results:
            gate_info = f"  [{','.join(r['gate_reasons'])}]" if r.get("gate_reasons") else ""
            _append_ita_ticker(lines, r, config, gate_info)
        lines.append("")

    if skip_results:
        tickers = ", ".join(r["ticker"] for r in skip_results)
        lines.append(f"<i>Skip ({len(skip_results)}): {tickers}</i>")
        lines.append("")

    lines.append(
        f"<b>{len(go_results)} GO | {len(watch_results)} WATCH | "
        f"{len(skip_results)} SKIP</b>"
    )
    return send_message("\n".join(lines))


def _append_ita_ticker(
    lines: list[str], r: dict, config: dict, suffix: str = "",
) -> None:
    """Append a single ITA ticker block to lines."""
    pm = f"{r['premarket_pct']:+.1f}%"
    lines.append(
        f"  <b>{r['ticker']}</b> {r['score']}/{r['max_score']} "
        f"{r['entry_method']} {pm}{suffix}"
    )
    lines.append(
        f"  SL {r['stop_loss']:.2f} | TP1 {r['tp1_price']:.2f} | "
        f"Trail {r['chandelier_stop']:.2f}"
    )
    close = r.get("last_close", 0)
    size = r["position_size"]
    if close > 0 and size > 0:
        leverage = config.get("position_sizing", {}).get("leverage", 5)
        notional = size * close
        margin = notional / leverage if leverage > 0 else notional
        lines.append(f"  {size} sh / {notional:,.0f} not. / {margin:,.0f} margin")


def send_ita_ai_report(results: list[dict], config: dict) -> bool:
    """Run AI analysis for top-N ITA GO/WATCH tickers, generate PDF, send via Telegram."""
    actionable = [r for r in results if r["status"] in ("GO", "WATCH")]
    if not actionable:
        logger.debug("No GO/WATCH tickers, skipping AI report")
        return False

    # Rank by score desc, then entry method priority, take top N
    entry_priority = {"GAP_UP": 4, "BONE_ZONE": 3, "PULLBACK": 2, "ORB": 1, "WAIT": 0}
    actionable.sort(
        key=lambda r: (r["score"], entry_priority.get(r.get("entry_method", ""), 0)),
        reverse=True,
    )
    max_tickers = config.get("ai", {}).get("max_tickers", 5)
    actionable = actionable[:max_tickers]

    return _run_ai_pipeline(
        actionable, results, config,
        strategy_name="ITA CFD",
        output_dir=config.get("output", {}).get("csv_dir", "output/reports_ita"),
    )


def send_etf_report(results: list[dict], config: dict, correlations: dict) -> bool:
    """Format and send ETF report to Telegram."""
    lines = ["\U0001f4ca <b>ETF Report</b>", ""]

    # Gates
    if results:
        gates = results[0].get("gates", {})
        vix = gates.get("vix_value", 0)
        vix_ok = gates.get("vix_ok", True)
        bench_ok = gates.get("bench_ok", True)
        adx = gates.get("adx_value", 0)
        adx_ok = gates.get("adx_ok", True)
        bench = config.get("benchmark", "CSSPX.MI")

        lines.append(
            f"VIX: {vix} {'✅' if vix_ok else '❌'} | "
            f"{bench}: {'✅' if bench_ok else '❌'} | "
            f"ADX: {adx} {'✅' if adx_ok else '❌'}"
        )

        if correlations.get("any_correlated"):
            for t1, t2, corr in correlations["correlated_pairs"]:
                lines.append(f"⚠️ CORR: {t1}/{t2} = {corr}")
        lines.append("")

    # Table
    for r in results:
        status = r["status"]
        icon = {"GO": "🟢", "WATCH": "🟡", "SKIP": "🔴"}.get(status, "⚪")
        gate_info = ""
        if r.get("gate_reasons"):
            gate_info = f" ({','.join(r['gate_reasons'])})"

        lines.append(
            f"{icon} <b>{r['ticker']}</b> {r['score']}/{r['max_score']} "
            f"{status}{gate_info}"
        )

        if status in ("GO", "WATCH"):
            pm = f"{r['premarket_pct']:+.2f}%"
            lines.append(f"   Premkt: {pm}")
            lines.append(
                f"   Stop: €{r['stop_loss']:.2f} | TP1: €{r['tp1_price']:.2f} | "
                f"Trail: €{r['chandelier_stop']:.2f}"
            )
            close = r.get("last_close", 0)
            size = r["position_size"]
            if close > 0 and size > 0:
                notional = size * close
                comm = config.get("position_sizing", {}).get("commission", 2.95)
                lines.append(
                    f"   Size: {size} shares (€{notional:,.0f}) | "
                    f"Comm: €{comm * 2:.2f} RT"
                )
            lines.append("")

    # Summary
    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    lines.append(f"<b>{go} GO | {watch} WATCH | {skip} SKIP</b>")

    return send_message("\n".join(lines))


# =========================================================================
# US S&P 500 CFD
# =========================================================================

def send_us_report(results: list[dict], config: dict) -> bool:
    """Format and send US S&P 500 CFD report to Telegram.

    Shows top-N ranked tickers in detail, remaining GO/WATCH compactly.
    """
    top_n = config.get("alerts", {}).get("top_n", 5)
    lines = [f"<b>US S&P 500 CFD — Top {top_n}</b>", ""]

    if results:
        gates = results[0].get("gates", {})
        vix = gates.get("vix_value", 0)
        vix_ok = gates.get("vix_ok", True)
        adx = gates.get("adx_value", 0)
        adx_ok = gates.get("adx_ok", True)
        lines.append(
            f"Gates: VIX {vix} {'OK' if vix_ok else 'HIGH'} | "
            f"ADX {adx} {'OK' if adx_ok else 'LOW'}"
        )
        lines.append("")

    ranked = [r for r in results if r.get("rank", 0) > 0]
    remaining = [r for r in results if r["status"] in ("GO", "WATCH") and r.get("rank", 0) == 0]

    for r in ranked:
        gate_info = f"  [{','.join(r['gate_reasons'])}]" if r.get("gate_reasons") else ""
        rs_pct = f" | RS {r.get('rs_value', 0):+.1f}%" if r.get("rs_value") else ""
        pm = f"{r['premarket_pct']:+.1f}%"

        lines.append(
            f"#{r['rank']} <b>{r['ticker']}</b> {r['status']} "
            f"{r['score']}/{r['max_score']}{rs_pct}{gate_info}"
        )
        lines.append(
            f"  {r['entry_method']} | Premkt {pm}"
        )
        lines.append(
            f"  SL {r['stop_loss']:.2f} | TP1 {r['tp1_price']:.2f} | "
            f"Trail {r['chandelier_stop']:.2f}"
        )
        close = r.get("last_close", 0)
        size = r["position_size"]
        if close > 0 and size > 0:
            leverage = config.get("position_sizing", {}).get("leverage", 5)
            notional = size * close
            margin = notional / leverage if leverage > 0 else notional
            lines.append(f"  {size} sh / ${notional:,.0f} not. / ${margin:,.0f} margin")
        lines.append("")

    if remaining:
        tickers_str = ", ".join(f"{r['ticker']}({r['score']})" for r in remaining)
        lines.append(f"<i>Also GO/WATCH: {tickers_str}</i>")
        lines.append("")

    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    lines.append(f"<b>{go} GO | {watch} WATCH | {skip} SKIP</b>")

    return send_message("\n".join(lines))


def send_us_ai_report(results: list[dict], config: dict) -> bool:
    """Run AI analysis for US ranked tickers, generate PDF, send via Telegram."""
    actionable = [r for r in results if r.get("rank", 0) > 0]
    if not actionable:
        logger.debug("No ranked US tickers, skipping AI report")
        return False

    return _run_ai_pipeline(
        actionable, results, config,
        strategy_name="US S&P 500 CFD",
        output_dir=config.get("output", {}).get("csv_dir", "output/reports_us"),
    )


def _run_ai_pipeline(
    actionable: list[dict],
    all_results: list[dict],
    config: dict,
    strategy_name: str,
    output_dir: str,
) -> bool:
    """Shared AI enrichment pipeline: news -> events -> LLM -> PDF -> Telegram.

    Enriches result dicts in-place with 'news', 'events', 'ai_analysis' fields.
    """
    from shared.analyzer import analyze_ticker
    from shared.events import check_events
    from shared.news import fetch_news
    from shared.pdf_report import generate_report

    for r in actionable:
        ticker = r["ticker"]
        logger.info("AI pipeline: enriching %s", ticker)

        # Fetch news
        news = fetch_news(ticker, config)
        r["news"] = news

        # Check events
        events = check_events(ticker, config)
        r["events"] = events

        # AI analysis
        ai_result = analyze_ticker(ticker, r, news, events, config)
        r["ai_analysis"] = ai_result

    # Generate PDF
    pdf_path = generate_report(all_results, config, strategy_name, output_dir)

    if pdf_path:
        go_count = sum(1 for r in actionable if r["status"] == "GO")
        watch_count = sum(1 for r in actionable if r["status"] == "WATCH")
        caption = (
            f"<b>{strategy_name} Analysis</b>\n"
            f"{go_count} GO | {watch_count} WATCH"
        )
        return send_document(pdf_path, caption=caption)

    logger.warning("PDF generation failed, skipping Telegram document send")
    return False
