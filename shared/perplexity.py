"""Query Perplexity Sonar API for fundamental risk checks on GO/WATCH tickers.

Reads config from environment variable:
  PERPLEXITY_API_KEY  — API key from perplexity.ai/settings/api

If missing, the check is silently skipped and the manual Telegram prompt
is sent instead (existing fallback behaviour).
"""

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
API_URL = "https://api.perplexity.ai/chat/completions"
MODEL = "sonar"


def is_configured() -> bool:
    return bool(API_KEY)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d (%A)")


def _next_week_range() -> str:
    today = datetime.now()
    end = today + timedelta(days=9)
    return f"{today.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"


def _build_ita_prompt(actionable: list[dict]) -> str:
    ticker_lines = []
    for r in actionable:
        checks = r["checks"]
        failed = [n for n, c in checks.items() if not c["passed"]]
        passed = [n for n, c in checks.items() if c["passed"]]
        fail_str = f" | Fail: {', '.join(failed)}" if failed else ""
        ticker_lines.append(
            f"- {r['ticker']} {r['status']} {r['score']}/6 | "
            f"Close: {r.get('last_close', 0):.2f} | "
            f"Entry: {r['entry_method']} | "
            f"SL: {r['stop_loss']:.2f} | TP1: {r['tp1_price']:.2f} | "
            f"Pass: {', '.join(passed)}{fail_str}"
        )
    tickers_str = "\n".join(ticker_lines)

    return (
        f"Data di oggi: {_today()}\n"
        f"Finestra di rischio: {_next_week_range()} (7 sessioni di borsa)\n\n"
        "Sei un analista rischio su azioni italiane FTSE MIB. "
        "Il mio screening tecnico automatico ha selezionato questi titoli "
        "per CFD multiday (3-7 sessioni, leva 5:1 broker):\n\n"
        f"{tickers_str}\n\n"
        "I tecnici sono validati. Cerca SOLO deal-breaker fondamentali "
        "che il tecnico non vede.\n\n"
        "Per ogni titolo cerca:\n"
        "1. EARNINGS: Trimestrali/semestrali nei prossimi 7gg di borsa? "
        "Data esatta se disponibile.\n"
        "2. EX-DIVIDENDO: Data ex-dividendo nei prossimi 7gg? "
        "Importo se disponibile.\n"
        "3. CATALYST: Catalyst attivo ultime 48h (upgrade/downgrade analyst, "
        "M&A, contratti, guidance)? Ha gambe multiday o gia prezzato?\n"
        "4. EVENTO MACRO: Evento specifico nei prossimi 2gg (BCE, asta BTP, "
        "dato macro EU, scadenza tecnica/opzioni) che impatta il titolo?\n"
        "5. RISCHIO SETTORIALE: Per bancari (ISP, UCG, BPE, FBK, MB) "
        "spread BTP-Bund in allargamento? Per energy (ENI, ERG) movimenti "
        "oil/gas rilevanti?\n\n"
        "Rispondi in JSON. Esempio:\n"
        "```json\n"
        "{\n"
        '  "macro": "BCE meeting 3 Apr, attesa tassi invariati",\n'
        '  "tickers": [\n'
        "    {\n"
        '      "ticker": "ISP.MI",\n'
        '      "earnings": {"flag": false, "detail": "prossima: 5 Mag"},\n'
        '      "ex_dividend": {"flag": false, "detail": "ex-div 19 Mag, 0.17"},\n'
        '      "catalyst": {"level": "NONE", "detail": ""},\n'
        '      "event": {"flag": false, "detail": ""},\n'
        '      "sector_risk": "spread BTP-Bund stabile 115bp",\n'
        '      "verdict": "ENTRY",\n'
        '      "reason": "Nessun deal-breaker, tecnici solidi"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n\n"
        "Regole verdetto:\n"
        "- Earnings entro 3gg = SKIP automatico\n"
        "- Earnings 4-7gg = WAIT (rischio volatilita pre-earnings)\n"
        "- Ex-dividendo entro 2gg = WAIT (gap down atteso)\n"
        "- Evento macro domani + no catalyst = SKIP\n"
        "- Catalyst ACTIVE + no evento = ENTRY\n"
        "- Catalyst FADING = WAIT\n"
        "- Nessun rischio trovato = ENTRY"
    )


def _build_us_prompt(actionable: list[dict]) -> str:
    ticker_lines = []
    for r in actionable:
        checks = r["checks"]
        failed = [n for n, c in checks.items() if not c["passed"]]
        passed = [n for n, c in checks.items() if c["passed"]]
        fail_str = f" | Fail: {', '.join(failed)}" if failed else ""
        ticker_lines.append(
            f"- {r['ticker']} {r['status']} {r['score']}/6 | "
            f"Close: ${r.get('last_close', 0):.2f} | "
            f"Entry: {r['entry_method']} | "
            f"SL: ${r['stop_loss']:.2f} | TP1: ${r['tp1_price']:.2f} | "
            f"Pass: {', '.join(passed)}{fail_str}"
        )
    tickers_str = "\n".join(ticker_lines)

    return (
        f"Today's date: {_today()}\n"
        f"Risk window: {_next_week_range()} (7 trading sessions)\n\n"
        "You are a risk analyst covering US large-cap equities (S&P 500). "
        "My automated technical screener selected these stocks for CFD "
        "multiday swing trades (3-7 sessions, 5:1 leverage via broker):\n\n"
        f"{tickers_str}\n\n"
        "Technicals are validated. Find ONLY fundamental deal-breakers "
        "that technicals cannot see.\n\n"
        "For each stock search:\n"
        "1. EARNINGS: Reports earnings in the next 7 trading days? "
        "Exact date if available.\n"
        "2. EX-DIVIDEND: Ex-dividend date in the next 7 days? "
        "Amount if available.\n"
        "3. CATALYST: Active catalyst in last 48h (analyst upgrade/downgrade, "
        "M&A, contracts, guidance revision)? Multi-day legs or priced in?\n"
        "4. MACRO EVENT: Specific event next 2 days (FOMC, CPI, NFP, PPI, "
        "options expiry) that impacts this stock?\n"
        "5. SECTOR RISK: For rate-sensitive (banks, REITs, utilities) "
        "note 10Y yield move. For tech, any regulatory/antitrust action?\n\n"
        "Respond in JSON. Example:\n"
        "```json\n"
        "{\n"
        '  "macro": "FOMC minutes Apr 2, CPI Apr 4",\n'
        '  "tickers": [\n'
        "    {\n"
        '      "ticker": "AAPL",\n'
        '      "earnings": {"flag": false, "detail": "next: May 1"},\n'
        '      "ex_dividend": {"flag": false, "detail": "ex-div May 10, $0.25"},\n'
        '      "catalyst": {"level": "ACTIVE", "detail": "new product launch"},\n'
        '      "event": {"flag": false, "detail": ""},\n'
        '      "sector_risk": "no tech regulatory risk this week",\n'
        '      "verdict": "ENTRY",\n'
        '      "reason": "Active catalyst, no blockers"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n\n"
        "Verdict rules:\n"
        "- Earnings within 3 days = SKIP automatic\n"
        "- Earnings 4-7 days = WAIT (pre-earnings volatility risk)\n"
        "- Ex-dividend within 2 days = WAIT (expected gap down)\n"
        "- Macro event tomorrow + no catalyst = SKIP\n"
        "- Active catalyst + no event = ENTRY\n"
        "- Fading catalyst = WAIT\n"
        "- No risk found = ENTRY"
    )


def _call_api(prompt: str) -> dict | None:
    """Call Perplexity Sonar API and return parsed response."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a concise financial risk analyst. "
                    "Respond ONLY with valid JSON, no markdown fences, "
                    "no commentary before or after the JSON. "
                    "Always use the exact JSON schema requested."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "search_recency_filter": "week",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            citations = body.get("citations", [])
    except urllib.error.HTTPError as e:
        logger.warning("Perplexity API HTTP error %d: %s", e.code, e.reason)
        return None
    except urllib.error.URLError as e:
        logger.warning("Perplexity API connection error: %s", e)
        return None
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.warning("Perplexity API unexpected response: %s", e)
        return None

    # Parse JSON from response — strip markdown fences if present
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        parsed = json.loads(text)
        parsed["_citations"] = citations
        return parsed
    except json.JSONDecodeError:
        logger.warning("Perplexity returned non-JSON, using raw text")
        return {"_raw": content, "_citations": citations}


def check_news_risk_ita(results: list[dict]) -> dict | None:
    """Run news risk check for ITA GO/WATCH tickers. Returns parsed dict or None."""
    actionable = [r for r in results if r["status"] in ("GO", "WATCH")]
    if not actionable:
        logger.debug("No GO/WATCH ITA tickers, skipping news check")
        return None
    if not is_configured():
        logger.debug("PERPLEXITY_API_KEY not set, skipping news check")
        return None

    logger.info("Querying Perplexity for %d ITA tickers...", len(actionable))
    prompt = _build_ita_prompt(actionable)
    return _call_api(prompt)


def check_news_risk_us(results: list[dict]) -> dict | None:
    """Run news risk check for US ranked tickers. Returns parsed dict or None."""
    actionable = [r for r in results if r.get("rank", 0) > 0]
    if not actionable:
        logger.debug("No ranked US tickers, skipping news check")
        return None
    if not is_configured():
        logger.debug("PERPLEXITY_API_KEY not set, skipping news check")
        return None

    logger.info("Querying Perplexity for %d US tickers...", len(actionable))
    prompt = _build_us_prompt(actionable)
    return _call_api(prompt)
