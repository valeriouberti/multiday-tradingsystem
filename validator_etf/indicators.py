import pandas_ta as ta

from shared.data import get_daily


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


