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


def send_ita_report(results: list[dict], config: dict) -> bool:
    """Format and send ITA CFD report to Telegram."""
    lines = ["\U0001f1ee\U0001f1f9 <b>ITA CFD Report</b>", ""]

    # Gates
    if results:
        gates = results[0].get("gates", {})
        vix = gates.get("vix_value", 0)
        vix_ok = gates.get("vix_ok", True)
        adx = gates.get("adx_value", 0)
        adx_ok = gates.get("adx_ok", True)
        lines.append(f"VIX: {vix} {'✅' if vix_ok else '❌'} | ADX: {adx} {'✅' if adx_ok else '❌'}")
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
            lines.append(
                f"   Entry: {r['entry_method']} | Premkt: {pm}"
            )
            lines.append(
                f"   Stop: €{r['stop_loss']:.2f} | TP1: €{r['tp1_price']:.2f} | "
                f"Trail: €{r['chandelier_stop']:.2f}"
            )
            close = r.get("last_close", 0)
            size = r["position_size"]
            if close > 0 and size > 0:
                leverage = config.get("position_sizing", {}).get("leverage", 5)
                notional = size * close
                margin = notional / leverage if leverage > 0 else notional
                lines.append(
                    f"   Size: {size} shares (€{notional:,.0f} not. / €{margin:,.0f} margin)"
                )
            lines.append("")

    # Summary
    go = sum(1 for r in results if r["status"] == "GO")
    watch = sum(1 for r in results if r["status"] == "WATCH")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    lines.append(f"<b>{go} GO | {watch} WATCH | {skip} SKIP</b>")

    return send_message("\n".join(lines))


def _build_ticker_block(r: dict, idx: int, config: dict) -> str:
    """Build a compact ticker context block for the deep-dive prompt."""
    checks = r["checks"]
    passed = [name for name, c in checks.items() if c["passed"]]
    failed = [name for name, c in checks.items() if not c["passed"]]
    close = r.get("last_close", 0)
    leverage = config.get("position_sizing", {}).get("leverage", 5)
    notional = r["position_size"] * close if close > 0 else 0
    margin = notional / leverage if leverage > 0 else notional

    return (
        f"{idx}. {r['ticker']} — {r['status']} ({r['score']}/{r['max_score']})\n"
        f"   Close: €{close:.2f} | Premkt: {r['premarket_pct']:+.2f}% | "
        f"Entry: {r['entry_method']}\n"
        f"   SL: €{r['stop_loss']:.2f} | TP1: €{r['tp1_price']:.2f} | "
        f"Trail: €{r['chandelier_stop']:.2f}\n"
        f"   Size: {r['position_size']} shares (€{notional:,.0f} not. / €{margin:,.0f} margin)\n"
        f"   ✅ {', '.join(passed)}"
        + (f" | ❌ {', '.join(failed)}" if failed else "")
    )


def send_ita_deepdive_prompt(results: list[dict], config: dict) -> bool:
    """Build and send Prompt 2 (deep-dive) with GO/WATCH tickers pre-filled.

    Sends two Telegram messages:
    1. Ticker context block (what the script found)
    2. The prompt to paste into Perplexity
    """
    actionable = [r for r in results if r["status"] in ("GO", "WATCH")]
    if not actionable:
        logger.debug("No GO/WATCH tickers, skipping deep-dive prompt")
        return False

    # --- Message 1: Ticker context ---
    gates = actionable[0].get("gates", {})
    vix_val = gates.get("vix_value", 0)
    adx_val = gates.get("adx_value", 0)

    ticker_blocks = [
        _build_ticker_block(r, i, config)
        for i, r in enumerate(actionable, 1)
    ]

    context_msg = (
        "📋 <b>Prompt 2 — Deep Dive</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{len(actionable)} titoli operabili</b> | "
        f"VIX: {vix_val} | ADX: {adx_val}\n\n"
        + "\n\n".join(ticker_blocks)
    )
    send_message(context_msg)

    # --- Message 2: The prompt (copy-paste to Perplexity) ---
    # Build compact ticker summary for the prompt itself
    ticker_summary = []
    for r in actionable:
        checks = r["checks"]
        failed = [name for name, c in checks.items() if not c["passed"]]
        fail_str = f" (manca: {', '.join(failed)})" if failed else ""
        ticker_summary.append(
            f"- {r['ticker']} {r['status']} {r['score']}/6{fail_str} | "
            f"€{r.get('last_close', 0):.2f} | SL €{r['stop_loss']:.2f}"
        )
    tickers_str = "\n".join(ticker_summary)

    prompt = (
        "⬇️ <b>Copia da qui su Perplexity</b> ⬇️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Cerca notizie in tempo reale. Sei un analista rischio su azioni "
        "italiane FTSE MIB.\n\n"
        "Il mio screening tecnico automatico ha selezionato questi titoli "
        "per CFD multiday (3-7 sessioni, leva 5:1 Fineco):\n\n"
        f"{tickers_str}\n\n"
        "I tecnici sono gia validati dallo script. Tu devi cercare SOLO "
        "deal-breaker fondamentali che il tecnico non vede.\n\n"
        "Per OGNI titolo rispondi a queste 3 domande:\n\n"
        "1. EARNINGS RISK: Pubblica trimestrali nei prossimi 7 giorni di borsa?\n"
        "   → ⛔ SI (data) / ✅ NO\n"
        "   Se SI → e un veto automatico, non si entra mai prima degli earnings con CFD.\n\n"
        "2. CATALYST: Qual e il catalyst attivo nelle ultime 48h per questo titolo? "
        "Ha gambe multiday (3-7 sessioni) o e gia prezzato?\n"
        "   → 🟢 ATTIVO (catalyst + perche ha gambe in 1 frase)\n"
        "   → 🟡 DEBOLE (catalyst in esaurimento)\n"
        "   → 🔴 NESSUNO (no catalyst o gia prezzato)\n\n"
        "3. EVENTO KILLER prossime 48h: C'e un evento specifico (BCE, asta BTP, "
        "dato macro, ex-dividendo, scadenza tecnica) che potrebbe invertire "
        "questo titolo prima del mio TP1?\n"
        "   → ⚠️ SI (evento + data) / ✅ NO\n\n"
        "OUTPUT (rigoroso, una riga per titolo + verdetto):\n\n"
        "[ticker.MI] | ⛔/✅ Earnings | 🟢/🟡/🔴 Catalyst | ⚠️/✅ Evento\n"
        "→ ENTRY / WAIT / SKIP + motivo in max 10 parole\n\n"
        "REGOLE:\n"
        "- ⛔ Earnings = SKIP automatico, non serve altro\n"
        "- 🔴 Nessun catalyst + ⚠️ Evento = SKIP\n"
        "- 🟡 Catalyst debole = WAIT (monitorare, non entrare oggi)\n"
        "- 🟢 Catalyst + ✅ No evento = ENTRY\n"
        "- Per bancari (ISP, UCG, BPE, FBK, MB): aggiungi nota su spread "
        "BTP-Bund se in allargamento >5bp oggi"
    )

    return send_message(prompt)


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

    Only sends top-N ranked tickers (determined by rank_results in scorer).
    Remaining GO/WATCH tickers are listed compactly at the bottom.
    """
    top_n = config.get("alerts", {}).get("top_n", 5)
    lines = [f"\U0001f1fa\U0001f1f8 <b>US S&P 500 CFD Report — Top {top_n}</b>", ""]

    if results:
        gates = results[0].get("gates", {})
        vix = gates.get("vix_value", 0)
        vix_ok = gates.get("vix_ok", True)
        adx = gates.get("adx_value", 0)
        adx_ok = gates.get("adx_ok", True)
        lines.append(f"VIX: {vix} {'\u2705' if vix_ok else '\u274c'} | ADX: {adx} {'\u2705' if adx_ok else '\u274c'}")
        lines.append("")

    ranked = [r for r in results if r.get("rank", 0) > 0]
    remaining = [r for r in results if r["status"] in ("GO", "WATCH") and r.get("rank", 0) == 0]

    for r in ranked:
        status = r["status"]
        icon = {"GO": "\U0001f7e2", "WATCH": "\U0001f7e1"}.get(status, "\u26aa")
        gate_info = ""
        if r.get("gate_reasons"):
            gate_info = f" ({','.join(r['gate_reasons'])})"

        rs_pct = f" | RS: {r.get('rs_value', 0):+.1f}%" if r.get("rs_value") else ""
        lines.append(
            f"#{r['rank']} {icon} <b>{r['ticker']}</b> {r['score']}/{r['max_score']} "
            f"{status}{gate_info}{rs_pct}"
        )
        pm = f"{r['premarket_pct']:+.2f}%"
        lines.append(f"   Entry: {r['entry_method']} | Premkt: {pm}")
        lines.append(
            f"   Stop: ${r['stop_loss']:.2f} | TP1: ${r['tp1_price']:.2f} | "
            f"Trail: ${r['chandelier_stop']:.2f}"
        )
        close = r.get("last_close", 0)
        size = r["position_size"]
        if close > 0 and size > 0:
            leverage = config.get("position_sizing", {}).get("leverage", 5)
            notional = size * close
            margin = notional / leverage if leverage > 0 else notional
            lines.append(
                f"   Size: {size} shares (${notional:,.0f} not. / ${margin:,.0f} margin)"
            )
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


def _build_ticker_block_us(r: dict, idx: int, config: dict) -> str:
    """Build a compact ticker context block for the US deep-dive prompt."""
    checks = r["checks"]
    passed = [name for name, c in checks.items() if c["passed"]]
    failed = [name for name, c in checks.items() if not c["passed"]]
    close = r.get("last_close", 0)
    leverage = config.get("position_sizing", {}).get("leverage", 5)
    notional = r["position_size"] * close if close > 0 else 0
    margin = notional / leverage if leverage > 0 else notional

    return (
        f"{idx}. {r['ticker']} \u2014 {r['status']} ({r['score']}/{r['max_score']})\n"
        f"   Close: ${close:.2f} | Premkt: {r['premarket_pct']:+.2f}% | "
        f"Entry: {r['entry_method']}\n"
        f"   SL: ${r['stop_loss']:.2f} | TP1: ${r['tp1_price']:.2f} | "
        f"Trail: ${r['chandelier_stop']:.2f}\n"
        f"   Size: {r['position_size']} shares (${notional:,.0f} not. / ${margin:,.0f} margin)\n"
        f"   \u2705 {', '.join(passed)}"
        + (f" | \u274c {', '.join(failed)}" if failed else "")
    )


def send_us_deepdive_prompt(results: list[dict], config: dict) -> bool:
    """Build and send US deep-dive Prompt 2 with top-N ranked tickers pre-filled."""
    actionable = [r for r in results if r.get("rank", 0) > 0]
    if not actionable:
        logger.debug("No GO/WATCH US tickers, skipping deep-dive prompt")
        return False

    gates = actionable[0].get("gates", {})
    vix_val = gates.get("vix_value", 0)
    adx_val = gates.get("adx_value", 0)

    ticker_blocks = [
        _build_ticker_block_us(r, i, config)
        for i, r in enumerate(actionable, 1)
    ]

    context_msg = (
        "\U0001f4cb <b>Prompt 2 \u2014 US Deep Dive</b>\n"
        "\u2501" * 30 + "\n\n"
        f"<b>{len(actionable)} actionable stocks</b> | "
        f"VIX: {vix_val} | ADX: {adx_val}\n\n"
        + "\n\n".join(ticker_blocks)
    )
    send_message(context_msg)

    ticker_summary = []
    for r in actionable:
        checks = r["checks"]
        failed = [name for name, c in checks.items() if not c["passed"]]
        fail_str = f" (miss: {', '.join(failed)})" if failed else ""
        ticker_summary.append(
            f"- {r['ticker']} {r['status']} {r['score']}/6{fail_str} | "
            f"${r.get('last_close', 0):.2f} | SL ${r['stop_loss']:.2f}"
        )
    tickers_str = "\n".join(ticker_summary)

    prompt = (
        "\u2b07\ufe0f <b>Copy from here to Perplexity</b> \u2b07\ufe0f\n"
        "\u2501" * 30 + "\n\n"
        "Search real-time news. You are a risk analyst covering US large-cap "
        "equities (S&P 500).\n\n"
        "My automated technical screener selected these stocks for CFD "
        "multiday swing trades (3-7 sessions, 5:1 leverage via Fineco):\n\n"
        f"{tickers_str}\n\n"
        "Technicals are already validated by the screener. Your job is to find "
        "ONLY fundamental deal-breakers that technicals cannot see.\n\n"
        "For EACH stock answer these 3 questions:\n\n"
        "1. EARNINGS RISK: Does it report earnings in the next 7 trading days?\n"
        "   \u2192 \u26d4 YES (date) / \u2705 NO\n"
        "   If YES \u2192 automatic veto, never hold CFD through earnings.\n\n"
        "2. CATALYST: What is the active catalyst in the last 48h? "
        "Does it have multi-day legs (3-7 sessions) or already priced in?\n"
        "   \u2192 \U0001f7e2 ACTIVE (catalyst + why it has legs in 1 sentence)\n"
        "   \u2192 \U0001f7e1 FADING (catalyst weakening)\n"
        "   \u2192 \U0001f534 NONE (no catalyst or already priced in)\n\n"
        "3. KILLER EVENT next 48h: Specific event (FOMC, CPI, NFP, "
        "PPI, ex-dividend, antitrust) that could reverse this stock?\n"
        "   \u2192 \u26a0\ufe0f YES (event + date) / \u2705 NO\n\n"
        "OUTPUT (strict, one line per stock + verdict):\n\n"
        "[TICKER] | \u26d4/\u2705 Earnings | \U0001f7e2/\U0001f7e1/\U0001f534 Catalyst | \u26a0\ufe0f/\u2705 Event\n"
        "\u2192 ENTRY / WAIT / SKIP + reason in max 10 words\n\n"
        "RULES:\n"
        "- \u26d4 Earnings = SKIP automatic\n"
        "- \U0001f534 No catalyst + \u26a0\ufe0f Event = SKIP\n"
        "- \U0001f7e1 Fading catalyst = WAIT\n"
        "- \U0001f7e2 Active catalyst + \u2705 No event = ENTRY\n"
        "- For rate-sensitive (banks, REITs, utilities): note 10Y yield move"
    )

    return send_message(prompt)
