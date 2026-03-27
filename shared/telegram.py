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
