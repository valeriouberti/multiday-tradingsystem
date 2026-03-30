"""Fetch recent news for tickers.

US tickers: Finnhub REST API (requires FINNHUB_API_KEY env var).
ITA tickers (.MI suffix): DuckDuckGo news search (no API key needed).

If API keys are missing or requests fail, returns empty list (never blocks pipeline).
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import yfinance as yf
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

# Cache for company name resolution (ticker -> shortName)
_name_cache: dict[str, str] = {}


@dataclass
class NewsItem:
    title: str
    source: str
    published: datetime
    sentiment_score: float | None  # Finnhub only; None for DDG
    url: str


def _get_company_name(ticker: str) -> str:
    """Resolve ticker to human-readable company name (cached)."""
    if ticker in _name_cache:
        return _name_cache[ticker]
    try:
        info = yf.Ticker(ticker).info
        name = info.get("shortName") or info.get("longName") or ticker
        _name_cache[ticker] = name
        return name
    except Exception:
        # Strip .MI suffix as fallback
        name = ticker.replace(".MI", "")
        _name_cache[ticker] = name
        return name


def _fetch_finnhub(ticker: str, lookback_hours: int = 48) -> list[NewsItem]:
    """Fetch news from Finnhub for US tickers."""
    if not FINNHUB_API_KEY:
        logger.warning("FINNHUB_API_KEY not set, skipping Finnhub news")
        return []

    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d")
    date_to = now.strftime("%Y-%m-%d")

    url = (
        f"https://finnhub.io/api/v1/company-news"
        f"?symbol={ticker}&from={date_from}&to={date_to}"
        f"&token={FINNHUB_API_KEY}"
    )

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning("Finnhub news fetch failed for %s: %s", ticker, e)
        return []

    items = []
    for article in data[:15]:  # Cap at 15 articles
        try:
            items.append(NewsItem(
                title=article.get("headline", ""),
                source=article.get("source", ""),
                published=datetime.fromtimestamp(
                    article.get("datetime", 0), tz=timezone.utc
                ),
                sentiment_score=article.get("sentiment"),
                url=article.get("url", ""),
            ))
        except (ValueError, TypeError):
            continue

    return items


def _fetch_duckduckgo(ticker: str, max_results: int = 10) -> list[NewsItem]:
    """Fetch news from DuckDuckGo for ITA tickers."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("ddgs not installed, skipping DDG news")
            return []

    company_name = _get_company_name(ticker)
    query = f"{company_name} azioni borsa"

    try:
        with DDGS() as ddgs:
            results = ddgs.news(
                keywords=query,
                region="it-it",
                max_results=max_results,
                timelimit="w",  # Past week, filter post-hoc
            )
    except Exception as e:
        logger.warning("DuckDuckGo news fetch failed for %s: %s", ticker, e)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    items = []
    for r in results:
        try:
            # DDG returns date as string; parse it
            pub_str = r.get("date", "")
            if pub_str:
                # DDG format varies; try common patterns
                for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                    try:
                        pub = datetime.strptime(pub_str[:25], fmt)
                        if pub.tzinfo is None:
                            pub = pub.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                else:
                    pub = datetime.now(timezone.utc)
            else:
                pub = datetime.now(timezone.utc)

            if pub < cutoff:
                continue

            items.append(NewsItem(
                title=r.get("title", ""),
                source=r.get("source", ""),
                published=pub,
                sentiment_score=None,
                url=r.get("url", ""),
            ))
        except (ValueError, TypeError):
            continue

    return items


def fetch_news(ticker: str, config: dict) -> list[NewsItem]:
    """Fetch recent news for a ticker.

    Uses Finnhub for US tickers, DuckDuckGo for ITA (.MI) tickers.
    Returns empty list on failure (never raises).
    """
    news_cfg = config.get("news", {})

    if ticker.endswith(".MI"):
        max_results = news_cfg.get("duckduckgo_max_results", 10)
        items = _fetch_duckduckgo(ticker, max_results=max_results)
        # Rate-limit DDG calls
        time.sleep(1)
    else:
        lookback = news_cfg.get("finnhub_lookback_hours", 48)
        items = _fetch_finnhub(ticker, lookback_hours=lookback)

    logger.info("Fetched %d news items for %s", len(items), ticker)
    return items
