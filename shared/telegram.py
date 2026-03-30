"""Send reports to Telegram via Bot API.

Reads config from environment variables:
  TELEGRAM_BOT_TOKEN  — token from @BotFather
  TELEGRAM_CHAT_ID    — your chat/group ID

If either is missing, sending is silently skipped.
"""

import json
import logging
import os
import urllib.request
import urllib.error

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TOP_N_CAPTION = 5


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


def send_document(file_path: str, caption: str = "",
                  parse_mode: str = "HTML") -> bool:
    """Send a document (PDF) to the configured Telegram chat."""
    if not is_configured():
        logger.debug("Telegram not configured, skipping")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    boundary = "----TelegramBoundary"

    # Build multipart/form-data body
    parts: list[bytes] = []

    # chat_id field
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n')
    parts.append(f"{CHAT_ID}\r\n".encode())

    # caption field (max 1024 chars for documents)
    if caption:
        truncated = caption[:1024]
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(b'Content-Disposition: form-data; name="caption"\r\n\r\n')
        parts.append(f"{truncated}\r\n".encode())

        parts.append(f"--{boundary}\r\n".encode())
        parts.append(b'Content-Disposition: form-data; name="parse_mode"\r\n\r\n')
        parts.append(f"{parse_mode}\r\n".encode())

    # document file
    filename = os.path.basename(file_path)
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="document"; '
        f'filename="{filename}"\r\n'.encode()
    )
    parts.append(b"Content-Type: application/pdf\r\n\r\n")
    with open(file_path, "rb") as f:
        parts.append(f.read())
    parts.append(b"\r\n")

    # Closing boundary
    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
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
        logger.warning("Telegram sendDocument failed: %s", e)
        return False


# ─── Top-5 selection helper ─────────────────────────────────────────────

def _top_n_results(results: list[dict], n: int = TOP_N_CAPTION) -> list[dict]:
    """Return top N results sorted by status (GO > WATCH) then score desc."""
    status_order = {"GO": 0, "WATCH": 1, "SKIP": 2}
    actionable = [r for r in results if r["status"] in ("GO", "WATCH")]
    ranked = sorted(
        actionable,
        key=lambda r: (status_order.get(r["status"], 9), -r["score"]),
    )
    return ranked[:n]


# ═════════════════════════════════════════════════════════════════════════
# ITA
# ═════════════════════════════════════════════════════════════════════════

def send_ita_report(results: list[dict], config: dict) -> bool:
    """Generate ITA PDF report and send via Telegram with top-5 caption."""
    from shared.pdf_report import generate_ita_pdf

    pdf_path = generate_ita_pdf(results, config)
    caption = _build_ita_caption(results, config)
    ok = send_document(pdf_path, caption=caption)
    return ok


def _build_ita_caption(results: list[dict], config: dict) -> str:
    """Build short caption with top 5 tickers for ITA."""
    lines = ["<b>ITA CFD Report</b>"]

    if results:
        gates = results[0].get("gates", {})
        vix = gates.get("vix_value", 0)
        vix_ok = "OK" if gates.get("vix_ok", True) else "HIGH"
        adx = gates.get("adx_value", 0)
        adx_ok = "OK" if gates.get("adx_ok", True) else "LOW"
        lines.append(f"VIX {vix:.0f} {vix_ok} | ADX {adx:.0f} {adx_ok}")
        lines.append("")

    top = _top_n_results(results)
    if top:
        lines.append("<b>Top 5:</b>")
        for r in top:
            pm = f"{r['premarket_pct']:+.1f}%"
            lines.append(
                f"{r['status']} {r['ticker']} {r['score']}/{r['max_score']} "
                f"| {r['entry_method']} | SL {r['stop_loss']:.2f}"
            )
        lines.append("")

    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    lines.append(f"{go} GO | {watch} WATCH | {skip} SKIP")

    return "\n".join(lines)


def send_ita_deepdive_prompt(results: list[dict], config: dict) -> bool:
    """Send ITA deep-dive prompt (two messages: context + Perplexity prompt)."""
    actionable = [r for r in results if r["status"] in ("GO", "WATCH")]
    if not actionable:
        logger.debug("No GO/WATCH tickers, skipping deep-dive prompt")
        return False

    # --- Message 1: Ticker context ---
    gates = actionable[0].get("gates", {})
    ctx_lines = [
        f"<b>Deep Dive — ITA ({len(actionable)} titoli)</b>",
        f"VIX {gates.get('vix_value', 0)} | ADX {gates.get('adx_value', 0)}",
        "",
    ]
    for i, r in enumerate(actionable, 1):
        checks = r["checks"]
        passed = [n for n, c in checks.items() if c["passed"]]
        failed = [n for n, c in checks.items() if not c["passed"]]
        close = r.get("last_close", 0)
        leverage = config.get("position_sizing", {}).get("leverage", 5)
        notional = r["position_size"] * close if close > 0 else 0
        margin = notional / leverage if leverage > 0 else notional

        ctx_lines.append(
            f"{i}. <b>{r['ticker']}</b> {r['status']} {r['score']}/{r['max_score']}"
        )
        ctx_lines.append(
            f"   {close:.2f} | Premkt {r['premarket_pct']:+.1f}% | {r['entry_method']}"
        )
        ctx_lines.append(
            f"   SL {r['stop_loss']:.2f} | TP1 {r['tp1_price']:.2f} | "
            f"Trail {r['chandelier_stop']:.2f}"
        )
        ctx_lines.append(
            f"   {r['position_size']} sh / {notional:,.0f} not. / {margin:,.0f} margin"
        )
        fail_str = f" | Fail: {', '.join(failed)}" if failed else ""
        ctx_lines.append(f"   Pass: {', '.join(passed)}{fail_str}")
        ctx_lines.append("")

    send_message("\n".join(ctx_lines))

    # --- Message 2: Perplexity prompt ---
    ticker_summary = []
    for r in actionable:
        checks = r["checks"]
        failed = [n for n, c in checks.items() if not c["passed"]]
        fail_str = f" (manca: {', '.join(failed)})" if failed else ""
        ticker_summary.append(
            f"- {r['ticker']} {r['status']} {r['score']}/6{fail_str} | "
            f"{r.get('last_close', 0):.2f} | SL {r['stop_loss']:.2f}"
        )
    tickers_str = "\n".join(ticker_summary)

    prompt = (
        "<b>Copia su Perplexity</b>\n"
        "---\n\n"
        "Cerca notizie in tempo reale. Sei un analista rischio su azioni "
        "italiane FTSE MIB.\n\n"
        "Il mio screening tecnico automatico ha selezionato questi titoli "
        "per CFD multiday (3-7 sessioni, leva 5:1 broker):\n\n"
        f"{tickers_str}\n\n"
        "I tecnici sono validati. Cerca SOLO deal-breaker fondamentali "
        "che il tecnico non vede.\n\n"
        "Per ogni titolo rispondi:\n\n"
        "1. EARNINGS: Pubblica trimestrali nei prossimi 7gg di borsa?\n"
        "   SI (data) = veto automatico / NO\n\n"
        "2. CATALYST: Catalyst attivo ultime 48h? Ha gambe multiday "
        "(3-7 sessioni) o gia prezzato?\n"
        "   ATTIVO (motivo) / DEBOLE / NESSUNO\n\n"
        "3. EVENTO KILLER 48h: Evento specifico (BCE, asta BTP, dato macro, "
        "ex-dividendo, scadenza tecnica) che puo invertire prima del TP1?\n"
        "   SI (evento + data) / NO\n\n"
        "Output (una riga per titolo):\n"
        "[ticker.MI] | Earnings: SI/NO | Catalyst: ATTIVO/DEBOLE/NESSUNO "
        "| Evento: SI/NO\n"
        "Verdetto: ENTRY / WAIT / SKIP + motivo (max 10 parole)\n\n"
        "Regole:\n"
        "- Earnings = SKIP automatico\n"
        "- Nessun catalyst + Evento = SKIP\n"
        "- Catalyst debole = WAIT\n"
        "- Catalyst attivo + No evento = ENTRY\n"
        "- Per bancari (ISP, UCG, BPE, FBK, MB): nota su spread "
        "BTP-Bund se in allargamento >5bp"
    )

    return send_message(prompt)


# ═════════════════════════════════════════════════════════════════════════
# ETF
# ═════════════════════════════════════════════════════════════════════════

def send_etf_report(results: list[dict], config: dict,
                    correlations: dict) -> bool:
    """Generate ETF PDF report and send via Telegram with top-5 caption."""
    from shared.pdf_report import generate_etf_pdf

    pdf_path = generate_etf_pdf(results, config, correlations)
    caption = _build_etf_caption(results, config, correlations)
    ok = send_document(pdf_path, caption=caption)
    return ok


def _build_etf_caption(results: list[dict], config: dict,
                       correlations: dict) -> str:
    """Build short caption with top 5 ETFs."""
    lines = ["<b>ETF Report</b>"]

    if results:
        gates = results[0].get("gates", {})
        vix = gates.get("vix_value", 0)
        vix_ok = "OK" if gates.get("vix_ok", True) else "HIGH"
        bench_ok = "OK" if gates.get("bench_ok", True) else "DOWN"
        adx = gates.get("adx_value", 0)
        adx_ok = "OK" if gates.get("adx_ok", True) else "LOW"
        lines.append(f"VIX {vix:.0f} {vix_ok} | Bench {bench_ok} | ADX {adx:.0f} {adx_ok}")
        lines.append("")

    top = _top_n_results(results)
    if top:
        lines.append("<b>Top 5:</b>")
        for r in top:
            lines.append(
                f"{r['status']} {r['ticker']} {r['score']}/{r['max_score']} "
                f"| SL {r['stop_loss']:.2f} | {r['position_size']} sh"
            )
        lines.append("")

    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    lines.append(f"{go} GO | {watch} WATCH | {skip} SKIP")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# US S&P 500 CFD
# ═════════════════════════════════════════════════════════════════════════

def send_us_report(results: list[dict], config: dict) -> bool:
    """Generate US PDF report and send via Telegram with top-5 caption."""
    from shared.pdf_report import generate_us_pdf

    pdf_path = generate_us_pdf(results, config)
    caption = _build_us_caption(results, config)
    ok = send_document(pdf_path, caption=caption)
    return ok


def _build_us_caption(results: list[dict], config: dict) -> str:
    """Build short caption with top 5 US tickers (uses rank if available)."""
    lines = ["<b>US S&P 500 CFD Report</b>"]

    if results:
        gates = results[0].get("gates", {})
        vix = gates.get("vix_value", 0)
        vix_ok = "OK" if gates.get("vix_ok", True) else "HIGH"
        adx = gates.get("adx_value", 0)
        adx_ok = "OK" if gates.get("adx_ok", True) else "LOW"
        lines.append(f"VIX {vix:.0f} {vix_ok} | ADX {adx:.0f} {adx_ok}")
        lines.append("")

    # Prefer ranked tickers; fall back to top-N by score
    ranked = [r for r in results if r.get("rank", 0) > 0]
    if ranked:
        ranked.sort(key=lambda r: r["rank"])
        top = ranked[:TOP_N_CAPTION]
    else:
        top = _top_n_results(results)

    if top:
        lines.append("<b>Top 5:</b>")
        for r in top:
            rank_str = f"#{r['rank']} " if r.get("rank", 0) > 0 else ""
            rs_str = f" RS{r.get('rs_value', 0):+.1f}%" if r.get("rs_value") else ""
            lines.append(
                f"{rank_str}{r['status']} {r['ticker']} "
                f"{r['score']}/{r['max_score']}{rs_str} | {r['entry_method']}"
            )
        lines.append("")

    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    lines.append(f"{go} GO | {watch} WATCH | {skip} SKIP")

    return "\n".join(lines)


def send_us_deepdive_prompt(results: list[dict], config: dict) -> bool:
    """Send US deep-dive prompt (two messages: context + Perplexity prompt)."""
    actionable = [r for r in results if r.get("rank", 0) > 0]
    if not actionable:
        logger.debug("No ranked US tickers, skipping deep-dive prompt")
        return False

    # --- Message 1: Ticker context ---
    gates = actionable[0].get("gates", {})
    ctx_lines = [
        f"<b>Deep Dive — US ({len(actionable)} stocks)</b>",
        f"VIX {gates.get('vix_value', 0)} | ADX {gates.get('adx_value', 0)}",
        "",
    ]
    for i, r in enumerate(actionable, 1):
        checks = r["checks"]
        passed = [n for n, c in checks.items() if c["passed"]]
        failed = [n for n, c in checks.items() if not c["passed"]]
        close = r.get("last_close", 0)
        leverage = config.get("position_sizing", {}).get("leverage", 5)
        notional = r["position_size"] * close if close > 0 else 0
        margin = notional / leverage if leverage > 0 else notional

        ctx_lines.append(
            f"{i}. <b>{r['ticker']}</b> {r['status']} {r['score']}/{r['max_score']}"
        )
        ctx_lines.append(
            f"   ${close:.2f} | Premkt {r['premarket_pct']:+.1f}% | {r['entry_method']}"
        )
        ctx_lines.append(
            f"   SL {r['stop_loss']:.2f} | TP1 {r['tp1_price']:.2f} | "
            f"Trail {r['chandelier_stop']:.2f}"
        )
        ctx_lines.append(
            f"   {r['position_size']} sh / ${notional:,.0f} not. / ${margin:,.0f} margin"
        )
        fail_str = f" | Fail: {', '.join(failed)}" if failed else ""
        ctx_lines.append(f"   Pass: {', '.join(passed)}{fail_str}")
        ctx_lines.append("")

    send_message("\n".join(ctx_lines))

    # --- Message 2: Perplexity prompt ---
    ticker_summary = []
    for r in actionable:
        checks = r["checks"]
        failed = [n for n, c in checks.items() if not c["passed"]]
        fail_str = f" (miss: {', '.join(failed)})" if failed else ""
        ticker_summary.append(
            f"- {r['ticker']} {r['status']} {r['score']}/6{fail_str} | "
            f"${r.get('last_close', 0):.2f} | SL ${r['stop_loss']:.2f}"
        )
    tickers_str = "\n".join(ticker_summary)

    prompt = (
        "<b>Copy to Perplexity</b>\n"
        "---\n\n"
        "Search real-time news. You are a risk analyst covering US large-cap "
        "equities (S&P 500).\n\n"
        "My automated technical screener selected these stocks for CFD "
        "multiday swing trades (3-7 sessions, 5:1 leverage via broker):\n\n"
        f"{tickers_str}\n\n"
        "Technicals are validated. Find ONLY fundamental deal-breakers "
        "that technicals cannot see.\n\n"
        "For each stock:\n\n"
        "1. EARNINGS: Reports earnings in the next 7 trading days?\n"
        "   YES (date) = automatic veto / NO\n\n"
        "2. CATALYST: Active catalyst in last 48h? Multi-day legs "
        "(3-7 sessions) or already priced in?\n"
        "   ACTIVE (reason) / FADING / NONE\n\n"
        "3. KILLER EVENT next 48h: Specific event (FOMC, CPI, NFP, "
        "PPI, ex-dividend, antitrust) that could reverse before TP1?\n"
        "   YES (event + date) / NO\n\n"
        "Output (one line per stock):\n"
        "[TICKER] | Earnings: YES/NO | Catalyst: ACTIVE/FADING/NONE "
        "| Event: YES/NO\n"
        "Verdict: ENTRY / WAIT / SKIP + reason (max 10 words)\n\n"
        "Rules:\n"
        "- Earnings = SKIP automatic\n"
        "- No catalyst + Event = SKIP\n"
        "- Fading catalyst = WAIT\n"
        "- Active catalyst + No event = ENTRY\n"
        "- Rate-sensitive (banks, REITs, utilities): note 10Y yield move"
    )

    return send_message(prompt)
