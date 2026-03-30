"""AI fundamental analyzer using Google Gemini.

Scores tickers on 5 binary dimensions (max 5/5):
  1. news_sentiment   — recent headlines positive/neutral
  2. earnings_risk    — no earnings within 5 sessions
  3. macro_risk       — no major macro event within 3 days
  4. sector_context   — sector favorable
  5. catalyst         — identifiable positive catalyst

Requires GEMINI_API_KEY env var. Gracefully returns None on failure.
"""

import json
import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from shared.events import EventFlags
from shared.news import NewsItem

logger = logging.getLogger(__name__)

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

DIMENSIONS = [
    "news_sentiment",
    "earnings_risk",
    "macro_risk",
    "sector_context",
    "catalyst",
]


@dataclass
class AnalysisResult:
    fundamental_score: int | None = None  # 0-5, None on failure
    dimensions: dict[str, dict] = field(default_factory=dict)
    summary: str = ""
    error: str | None = None


def _build_prompt(
    ticker: str,
    result: dict,
    news: list[NewsItem],
    events: EventFlags,
) -> str:
    """Build the structured analyst prompt."""
    # Technical context
    checks = result.get("checks", {})
    passed = [n for n, c in checks.items() if c["passed"]]
    failed = [n for n, c in checks.items() if not c["passed"]]

    # Format news headlines
    if news:
        news_lines = []
        for n in news[:10]:
            date_str = n.published.strftime("%Y-%m-%d %H:%M")
            news_lines.append(f"- [{date_str}] {n.title} ({n.source})")
        news_text = "\n".join(news_lines)
    else:
        news_text = "No recent news available."

    # Format events
    if events.earnings_within_window:
        earnings_text = f"YES — earnings on {events.earnings_date}"
    else:
        earnings_text = "No earnings within 5 trading sessions."

    if events.macro_events:
        macro_lines = [
            f"- {e['name']} ({e['country']}, {e['date']})"
            for e in events.macro_events
        ]
        macro_text = "\n".join(macro_lines)
    else:
        macro_text = "No high-importance macro events within 3 trading days."

    return f"""You are a risk analyst for a CFD multiday swing trading desk.
A technical screener has selected {ticker} with status {result['status']}, score {result['score']}/{result['max_score']}.

Technical checks passed: {', '.join(passed) if passed else 'none'}
Technical checks failed: {', '.join(failed) if failed else 'none'}
Entry method: {result.get('entry_method', 'N/A')}
Last close: {result.get('last_close', 0):.2f}
Stop loss: {result.get('stop_loss', 0):.2f}
TP1: {result.get('tp1_price', 0):.2f}

Recent news (last 48h):
{news_text}

Upcoming events:
Earnings: {earnings_text}
Macro events:
{macro_text}

Score exactly 5 binary dimensions (1 = favorable for a long swing trade, 0 = unfavorable):

1. news_sentiment: Are recent news headlines positive or neutral for a long position? If no news, score 1.
2. earnings_risk: Is the stock free from imminent earnings (>5 trading days away)? No earnings data = score 1.
3. macro_risk: Are there no high-importance macro events (FOMC, ECB, CPI, NFP) within 3 trading days?
4. sector_context: Is the stock's sector currently favorable (no sector-wide headwinds visible in news)?
5. catalyst: Is there an identifiable positive catalyst that supports a multiday move (upgrade, deal, guidance)?

Return ONLY valid JSON with this exact structure:
{{
  "fundamental_score": <sum of 5 dimension scores, 0-5>,
  "dimensions": {{
    "news_sentiment": {{"score": 0 or 1, "reason": "<max 15 words>"}},
    "earnings_risk": {{"score": 0 or 1, "reason": "<max 15 words>"}},
    "macro_risk": {{"score": 0 or 1, "reason": "<max 15 words>"}},
    "sector_context": {{"score": 0 or 1, "reason": "<max 15 words>"}},
    "catalyst": {{"score": 0 or 1, "reason": "<max 15 words>"}}
  }},
  "summary": "<2-3 sentence analyst assessment>"
}}"""


def _parse_response(text: str) -> AnalysisResult:
    """Parse Gemini JSON response into AnalysisResult."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return AnalysisResult(error=f"JSON parse error: {e}")

    dims = data.get("dimensions", {})
    for dim in DIMENSIONS:
        if dim not in dims:
            dims[dim] = {"score": 0, "reason": "Not evaluated"}

    # Recompute score from dimensions to avoid LLM math errors
    score = sum(dims[d].get("score", 0) for d in DIMENSIONS)

    return AnalysisResult(
        fundamental_score=score,
        dimensions=dims,
        summary=data.get("summary", ""),
    )


def analyze_ticker(
    ticker: str,
    result: dict,
    news: list[NewsItem],
    events: EventFlags,
    config: dict,
) -> AnalysisResult:
    """Run AI fundamental analysis on a ticker.

    Returns AnalysisResult with fundamental_score=None on failure (never raises).
    """
    ai_cfg = config.get("ai", {})
    if not ai_cfg.get("enabled", True):
        return AnalysisResult(error="AI analysis disabled in config")

    if not GEMINI_API_KEY:
        return AnalysisResult(error="GEMINI_API_KEY not set")

    model = ai_cfg.get("model", "gemini-3-flash-preview")

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return AnalysisResult(error="google-genai not installed")

    prompt = _build_prompt(ticker, result, news, events)

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=500,
            ),
        )

        if not response.text:
            return AnalysisResult(error="Empty response from Gemini")

        result_obj = _parse_response(response.text)
        logger.info(
            "AI analysis for %s: fundamental_score=%s",
            ticker, result_obj.fundamental_score,
        )
        return result_obj

    except Exception as e:
        logger.warning("Gemini API call failed for %s: %s", ticker, e)
        return AnalysisResult(error=f"API error: {e}")
