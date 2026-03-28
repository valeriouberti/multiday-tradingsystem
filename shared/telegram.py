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


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message to the configured Telegram chat. Returns True on success."""
    if not is_configured():
        logger.debug("Telegram not configured, skipping")
        return False

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
                logger.info("Telegram message sent")
                return True
            logger.warning("Telegram API returned %d", resp.status)
            return False
    except urllib.error.URLError as e:
        logger.warning("Telegram send failed: %s", e)
        return False


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
