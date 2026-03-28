from shared.data import get_daily, get_h1, get_premarket_change
from shared.indicators import (
    check_ema_cross,
    check_macd,
    check_mfi,
    check_rs_vs_benchmark,
    check_rsi,
    check_weekly_ema,
    detect_entry_method,
    get_atr_stop,
    get_chandelier_stop,
    get_mfi_value,
    get_rs_roc_value,
    get_rsi_value,
    get_tp1_price,
)
from shared.position_sizing import get_cfd_position_size as get_position_size

# Entry method priority for ranking (higher = better)
ENTRY_PRIORITY = {"GAP_UP": 4, "BONE_ZONE": 3, "PULLBACK": 2, "ORB": 1, "WAIT": 0}


def score_ticker(ticker: str, cfg: dict, gates: dict) -> dict:
    """Run 6 scored checks + apply 2 gates for a US S&P 500 stock.

    Scored checks (6):
      1. EMA20 > EMA50 Daily    (trend)
      2. Weekly EMA20 > EMA50   (structural trend)
      3. MACD > Signal          (momentum)
      4. RSI > threshold        (momentum filter)
      5. MFI > threshold        (money flow)
      6. RS vs SPY rising       (relative strength, 20d/5d ROC)

    Gates (2):
      - VIX Regime: VIX < threshold
      - ADX Regime: ADX(14) >= threshold on SPY
    """
    df_daily = get_daily(ticker, cfg)
    df_h1 = get_h1(ticker, cfg)

    if df_daily.empty:
        return _empty_result(ticker, cfg, gates)

    ema_pass, ema_disp = check_ema_cross(df_daily, cfg)
    weekly_pass, weekly_disp = check_weekly_ema(ticker, cfg)
    macd_pass, macd_disp = check_macd(df_daily, cfg)
    rsi_pass, rsi_disp = check_rsi(df_daily, cfg)
    mfi_pass, mfi_disp = check_mfi(df_daily, cfg)
    rs_pass, rs_disp = check_rs_vs_benchmark(df_daily, cfg)

    checks = {
        "EMA D": {"passed": ema_pass, "display": ema_disp},
        "EMA W": {"passed": weekly_pass, "display": weekly_disp},
        "MACD": {"passed": macd_pass, "display": macd_disp},
        "RSI": {"passed": rsi_pass, "display": rsi_disp},
        "MFI": {"passed": mfi_pass, "display": mfi_disp},
        "RS": {"passed": rs_pass, "display": rs_disp},
    }

    score = sum(1 for c in checks.values() if c["passed"])
    stop_loss = get_atr_stop(df_daily, cfg)
    chandelier_stop = get_chandelier_stop(df_daily, cfg)
    tp1_price = get_tp1_price(df_daily, cfg)
    pos_size = get_position_size(df_daily, cfg)
    entry_method = detect_entry_method(df_daily, df_h1, cfg)
    premarket_pct = get_premarket_change(ticker)

    # Numeric values for ranking
    rs_value = get_rs_roc_value(df_daily, cfg)
    rsi_value = get_rsi_value(df_daily, cfg)
    mfi_value = get_mfi_value(df_daily, cfg)

    go_thresh = cfg["alerts"]["go_threshold"]
    watch_thresh = cfg["alerts"]["watch_threshold"]
    if score >= go_thresh:
        status = "GO"
    elif score >= watch_thresh:
        status = "WATCH"
    else:
        status = "SKIP"

    gate_reasons = []
    if not gates.get("vix_ok", True):
        gate_reasons.append("VIX")
    if not gates.get("adx_ok", True):
        gate_reasons.append("ADX")

    if status == "GO" and gate_reasons:
        status = "WATCH"

    last_close = round(float(df_daily["Close"].iloc[-1]), 2)

    return {
        "ticker": ticker,
        "score": score,
        "max_score": 6,
        "checks": checks,
        "gates": gates,
        "gate_reasons": gate_reasons,
        "last_close": last_close,
        "stop_loss": stop_loss,
        "chandelier_stop": chandelier_stop,
        "tp1_price": tp1_price,
        "position_size": pos_size,
        "entry_method": entry_method,
        "premarket_pct": premarket_pct,
        "status": status,
        "rs_value": rs_value,
        "rsi_value": rsi_value,
        "mfi_value": mfi_value,
    }


def _empty_result(ticker: str, cfg: dict, gates: dict) -> dict:
    benchmark = cfg.get("benchmark", "SPY")
    return {
        "ticker": ticker,
        "score": 0,
        "max_score": 6,
        "checks": {
            "EMA D": {"passed": False, "display": ""},
            "EMA W": {"passed": False, "display": ""},
            "MACD": {"passed": False, "display": ""},
            "RSI": {"passed": False, "display": ""},
            "MFI": {"passed": False, "display": ""},
            "RS": {"passed": False, "display": benchmark},
        },
        "gates": gates,
        "gate_reasons": [],
        "last_close": 0.0,
        "stop_loss": 0.0,
        "chandelier_stop": 0.0,
        "tp1_price": 0.0,
        "position_size": 0,
        "entry_method": "WAIT",
        "premarket_pct": 0.0,
        "status": "SKIP",
        "rs_value": 0.0,
        "rsi_value": 0.0,
        "mfi_value": 0.0,
    }


def rank_results(results: list[dict], top_n: int = 5) -> list[dict]:
    """Rank GO/WATCH results and return the top N.

    Ranking criteria (lexicographic):
      1. Score (descending) — 6/6 beats 5/6
      2. RS ROC % (descending) — strongest relative momentum vs SPY
      3. Entry method priority (descending) — active setup beats WAIT

    SKIP results are excluded. All results get a 'rank' field
    (1-based for top-N, 0 for non-ranked).
    """
    actionable = [r for r in results if r["status"] in ("GO", "WATCH")]
    skips = [r for r in results if r["status"] == "SKIP"]

    actionable.sort(
        key=lambda r: (
            r["score"],
            r.get("rs_value", 0.0),
            ENTRY_PRIORITY.get(r["entry_method"], 0),
        ),
        reverse=True,
    )

    for i, r in enumerate(actionable):
        r["rank"] = i + 1 if i < top_n else 0

    for r in skips:
        r["rank"] = 0

    return actionable[:top_n] + actionable[top_n:] + skips
