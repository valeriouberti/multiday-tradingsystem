import pandas_ta as ta

from core.data import get_daily, get_premarket_change
from core.indicators import (
    check_ema_cross,
    check_macd,
    check_mfi,
    check_rs_vs_benchmark,
    check_rsi,
    check_weekly_ema,
    get_atr_stop,
    get_chandelier_stop,
    get_tp1_price,
)
from core.position_sizing import get_etf_position_size as get_position_size


def score_ticker(ticker: str, cfg: dict, gates: dict) -> dict:
    """Run 6 scored checks + apply 4 gates for a sector ETF.

    Scored checks (6):
      1. EMA20 > EMA50 Daily    (trend)
      2. Weekly EMA20 > EMA50   (structural trend)
      3. MACD > Signal          (momentum)
      4. RSI > 50               (momentum filter)
      5. MFI > 50               (money flow)
      6. RS vs benchmark rising (sector rotation, 20d/5d ROC)

    Gates (4):
      - VIX Regime: VIX < 25
      - Benchmark Health: EMA20 > EMA50
      - Correlation: pairwise corr < 0.7
      - ADX Regime: ADX(14) >= 20 on benchmark
    """
    df_daily = get_daily(ticker, cfg)

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
    premarket_pct = get_premarket_change(ticker)

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
    if not gates.get("bench_ok", True):
        gate_reasons.append("BENCH")
    if gates.get("is_correlated", False):
        gate_reasons.append("CORR")
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
        "premarket_pct": premarket_pct,
        "status": status,
    }


def _empty_result(ticker: str, cfg: dict, gates: dict) -> dict:
    benchmark = cfg.get("benchmark", "CSSPX.MI")
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
        "premarket_pct": 0.0,
        "status": "SKIP",
    }


# =========================================================================
# ETF-specific gates (was validator_etf/indicators.py)
# =========================================================================

def check_bench_health(cfg: dict) -> tuple[bool, str]:
    """Gate: Benchmark EMA fast > EMA slow (broad market uptrend)."""
    benchmark = cfg.get("benchmark", "CSSPX.MI")
    fast = cfg["strategy"].get("bench_ema_fast", 20)
    slow = cfg["strategy"].get("bench_ema_slow", 50)
    try:
        df = get_daily(benchmark, cfg)
        if df.empty:
            return False, ""
        ema_fast = ta.ema(df["Close"], length=fast)
        ema_slow = ta.ema(df["Close"], length=slow)
        if ema_fast is None or ema_slow is None:
            return False, ""
        return bool(ema_fast.iloc[-1] > ema_slow.iloc[-1]), ""
    except Exception:
        return False, ""


def check_correlations(tickers: list[str], cfg: dict) -> dict:
    """Gate: Pairwise correlation of daily returns.

    If two sector ETFs are >0.7 correlated over 20 days, they are
    effectively the same trade — combined position size should be halved.
    """
    lookback = cfg["strategy"].get("correlation_lookback", 20)
    threshold = cfg["strategy"].get("correlation_threshold", 0.7)
    returns = {}
    for ticker in tickers:
        df = get_daily(ticker, cfg)
        if df.empty or len(df) < lookback + 1:
            continue
        ret = df["Close"].pct_change().dropna().iloc[-lookback:]
        returns[ticker] = ret

    correlated_pairs = []
    tickers_with_data = list(returns.keys())
    for i in range(len(tickers_with_data)):
        for j in range(i + 1, len(tickers_with_data)):
            t1, t2 = tickers_with_data[i], tickers_with_data[j]
            common = returns[t1].index.intersection(returns[t2].index)
            if len(common) < 10:
                continue
            corr = float(returns[t1].loc[common].corr(returns[t2].loc[common]))
            if corr > threshold:
                correlated_pairs.append((t1, t2, round(corr, 2)))

    return {
        "correlated_pairs": correlated_pairs,
        "any_correlated": len(correlated_pairs) > 0,
    }
