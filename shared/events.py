"""Event risk filter: earnings proximity + macro events.

Earnings: yfinance Ticker.calendar (free, already in stack).
Macro events: static calendar from config (FOMC/ECB dates published 12+ months in advance).

Returns safe defaults on failure (never blocks pipeline).
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class EventFlags:
    earnings_within_window: bool = False
    earnings_date: str | None = None  # ISO date string
    macro_events: list[dict] = field(default_factory=list)


def _check_earnings(ticker: str, blackout_days: int = 5) -> tuple[bool, str | None]:
    """Check if earnings are within blackout_days trading days.

    Returns (within_window, earnings_date_str).
    """
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None:
            return False, None

        # yfinance calendar can return a dict or DataFrame depending on version
        earnings_date = None
        if isinstance(cal, dict):
            for key in ("Earnings Date", "earningsDate", "earnings_date"):
                val = cal.get(key)
                if val is not None:
                    if isinstance(val, list) and val:
                        earnings_date = val[0]
                    elif isinstance(val, (datetime, date)):
                        earnings_date = val
                    break
        elif isinstance(cal, pd.DataFrame):
            if "Earnings Date" in cal.columns:
                vals = cal["Earnings Date"].dropna()
                if len(vals) > 0:
                    earnings_date = vals.iloc[0]
            elif "Earnings Date" in cal.index:
                vals = cal.loc["Earnings Date"].dropna()
                if len(vals) > 0:
                    earnings_date = vals.iloc[0]

        if earnings_date is None:
            return False, None

        # Convert to date
        if isinstance(earnings_date, datetime):
            earnings_dt = earnings_date.date()
        elif isinstance(earnings_date, date):
            earnings_dt = earnings_date
        elif isinstance(earnings_date, str):
            earnings_dt = datetime.strptime(earnings_date[:10], "%Y-%m-%d").date()
        elif isinstance(earnings_date, pd.Timestamp):
            earnings_dt = earnings_date.date()
        else:
            return False, None

        today = date.today()
        if earnings_dt < today:
            return False, None

        # Count trading days between today and earnings
        bdays = len(pd.bdate_range(today, earnings_dt)) - 1  # exclude today
        within = bdays <= blackout_days

        return within, earnings_dt.isoformat()

    except Exception as e:
        logger.warning("Earnings check failed for %s: %s", ticker, e)
        return False, None


def _check_macro_events(
    ticker: str, config: dict, blackout_days: int = 3,
) -> list[dict]:
    """Check static macro event calendar from config.

    Config format under events.macro_calendar:
      - date: "2026-04-02"
        name: "ECB Rate Decision"
        country: EU
      - date: "2026-05-07"
        name: "FOMC Rate Decision"
        country: US
    """
    calendar = config.get("events", {}).get("macro_calendar", [])
    if not calendar:
        return []

    today = date.today()
    window_end = today + timedelta(days=blackout_days + 4)  # +4 for weekends

    # Determine country filter based on ticker
    if ticker.endswith(".MI"):
        countries = {"EU", "IT", "DE", "FR", "EA"}
    else:
        countries = {"US"}

    events = []
    for item in calendar:
        item_country = item.get("country", "")
        if item_country not in countries:
            continue

        try:
            event_date = date.fromisoformat(item["date"])
        except (ValueError, KeyError):
            continue

        if today <= event_date <= window_end:
            # Check trading day distance
            bdays = len(pd.bdate_range(today, event_date)) - 1
            if bdays <= blackout_days:
                events.append({
                    "name": item.get("name", "Unknown"),
                    "date": item["date"],
                    "country": item_country,
                    "importance": "High",
                })

    return events


def check_events(ticker: str, config: dict) -> EventFlags:
    """Check earnings proximity and macro events for a ticker.

    Returns EventFlags with safe defaults on failure (never raises).
    """
    events_cfg = config.get("events", {})
    blackout_earnings = events_cfg.get("earnings_blackout_days", 5)
    blackout_macro = events_cfg.get("macro_blackout_days", 3)

    within, earnings_date = _check_earnings(ticker, blackout_earnings)
    macro = _check_macro_events(ticker, config, blackout_macro)

    flags = EventFlags(
        earnings_within_window=within,
        earnings_date=earnings_date,
        macro_events=macro,
    )

    if within:
        logger.info("Earnings flag for %s: %s", ticker, earnings_date)
    if macro:
        logger.info("Macro events for %s: %d high-impact events", ticker, len(macro))

    return flags
