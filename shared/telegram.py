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


def _format_news_risk_telegram(news_risk: dict) -> list[str]:
    """Format structured Perplexity news risk for Telegram HTML."""
    lines = ["<b>NEWS RISK (Perplexity)</b>"]

    if "_raw" in news_risk:
        lines.append(news_risk["_raw"])
        return lines

    macro = news_risk.get("macro", "")
    if macro:
        lines.append(f"<i>Macro: {macro}</i>")
        lines.append("")

    for t in news_risk.get("tickers", []):
        ticker = t.get("ticker", "???")
        verdict = t.get("verdict", "???").upper()
        reason = t.get("reason", "")

        if verdict == "SKIP":
            icon = "\u274c"
        elif verdict == "WAIT":
            icon = "\u26a0\ufe0f"
        else:
            icon = "\u2705"

        lines.append(f"{icon} <b>{ticker}</b> {verdict} \u2014 {reason}")

        flags = []
        earn = t.get("earnings", {})
        if earn.get("flag"):
            flags.append(f"Earnings: {earn.get('detail', 'YES')}")
        exdiv = t.get("ex_dividend", {})
        if exdiv.get("flag"):
            flags.append(f"Ex-div: {exdiv.get('detail', 'YES')}")
        event = t.get("event", {})
        if event.get("flag"):
            flags.append(f"Event: {event.get('detail', 'YES')}")
        if flags:
            lines.append(f"   {' | '.join(flags)}")

    return lines


def send_ita_report(results: list[dict], config: dict, *, news_risk: dict | None = None) -> bool:
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

    if news_risk:
        lines.append("")
        lines.extend(_format_news_risk_telegram(news_risk))

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

def send_us_report(results: list[dict], config: dict, *, news_risk: dict | None = None) -> bool:
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

    if news_risk:
        lines.append("")
        lines.extend(_format_news_risk_telegram(news_risk))

    return send_message("\n".join(lines))


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
