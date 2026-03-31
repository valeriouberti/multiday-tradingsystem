"""Vectorized signal generation for backtesting.

Translates the point-in-time checks from core/indicators.py into full
time-series signals so each bar gets a GO/WATCH/SKIP status.
"""

import pandas as pd
import pandas_ta as ta


def compute_all_signals(
    df_daily: pd.DataFrame,
    df_weekly: pd.DataFrame,
    bench_daily: pd.DataFrame,
    vix_daily: pd.DataFrame,
    cfg: dict,
    mode: str = "ita",
) -> pd.DataFrame:
    """Compute all 6 checks + gates as boolean Series aligned to df_daily index.

    Returns a DataFrame with columns:
        check_ema_d, check_ema_w, check_macd, check_rsi, check_mfi, check_rs,
        gate_vix, gate_adx, gate_bench (ETF only),
        score, go, atr
    """
    strat = cfg["strategy"]
    idx = df_daily.index
    signals = pd.DataFrame(index=idx)

    # --- Check 1: Daily EMA cross ---
    ema_fast = ta.ema(df_daily["Close"], length=strat["ema_fast"])
    ema_slow = ta.ema(df_daily["Close"], length=strat["ema_slow"])
    signals["check_ema_d"] = (ema_fast > ema_slow).fillna(False)

    # --- Check 2: Weekly EMA cross (forward-filled to daily) ---
    w_fast = strat.get("weekly_ema_fast", 20)
    w_slow = strat.get("weekly_ema_slow", 50)
    ema_w_fast = ta.ema(df_weekly["Close"], length=w_fast)
    ema_w_slow = ta.ema(df_weekly["Close"], length=w_slow)
    weekly_signal = (ema_w_fast > ema_w_slow).fillna(False)
    # Align weekly to daily via forward-fill
    weekly_signal.index = weekly_signal.index.tz_localize(None) if weekly_signal.index.tz else weekly_signal.index
    daily_idx = idx.tz_localize(None) if idx.tz else idx
    signals["check_ema_w"] = weekly_signal.reindex(daily_idx, method="ffill").fillna(False).values

    # --- Check 3: MACD > Signal ---
    macd_result = ta.macd(
        df_daily["Close"],
        fast=strat["macd_fast"],
        slow=strat["macd_slow"],
        signal=strat["macd_signal"],
    )
    if macd_result is not None and not macd_result.empty:
        macd_cols = [c for c in macd_result.columns if c.startswith("MACD_")]
        signal_cols = [c for c in macd_result.columns if c.startswith("MACDs_")]
        if macd_cols and signal_cols:
            signals["check_macd"] = (
                macd_result[macd_cols[0]] > macd_result[signal_cols[0]]
            ).fillna(False)
        else:
            signals["check_macd"] = False
    else:
        signals["check_macd"] = False

    # --- Check 4: RSI > threshold ---
    rsi = ta.rsi(df_daily["Close"], length=strat["rsi_length"])
    signals["check_rsi"] = (rsi > strat["rsi_threshold"]).fillna(False) if rsi is not None else False

    # --- Check 5: MFI > threshold ---
    mfi = ta.mfi(
        df_daily["High"], df_daily["Low"], df_daily["Close"], df_daily["Volume"],
        length=strat.get("mfi_length", 14),
    )
    signals["check_mfi"] = (mfi > strat.get("mfi_threshold", 50)).fillna(False) if mfi is not None else False

    # --- Check 6: RS vs benchmark rising (5d ROC over 20d lookback) ---
    roc_days = strat.get("rs_roc_days", 5)
    common_idx = df_daily.index.intersection(bench_daily.index)
    if len(common_idx) > roc_days:
        rs = df_daily.loc[common_idx, "Close"] / bench_daily.loc[common_idx, "Close"]
        rs_rising = rs > rs.shift(roc_days)
        signals["check_rs"] = rs_rising.reindex(idx).fillna(False)
    else:
        signals["check_rs"] = False

    # --- Score ---
    check_cols = ["check_ema_d", "check_ema_w", "check_macd", "check_rsi", "check_mfi", "check_rs"]
    signals["score"] = signals[check_cols].sum(axis=1).astype(int)

    # --- Gate: VIX < threshold ---
    vix_thresh = strat.get("vix_threshold", 25)
    if not vix_daily.empty:
        vix_aligned = vix_daily["Close"].reindex(idx, method="ffill")
        signals["gate_vix"] = (vix_aligned < vix_thresh).fillna(True)
    else:
        signals["gate_vix"] = True

    # --- Gate: ADX on benchmark >= threshold ---
    adx_length = strat.get("adx_length", 14)
    adx_thresh = strat.get("adx_threshold", 20)
    if not bench_daily.empty:
        adx = ta.adx(bench_daily["High"], bench_daily["Low"], bench_daily["Close"], length=adx_length)
        if adx is not None and not adx.empty:
            adx_col = [c for c in adx.columns if c.startswith("ADX_")]
            if adx_col:
                adx_series = adx[adx_col[0]].reindex(idx, method="ffill")
                signals["gate_adx"] = (adx_series >= adx_thresh).fillna(True)
            else:
                signals["gate_adx"] = True
        else:
            signals["gate_adx"] = True
    else:
        signals["gate_adx"] = True

    # --- Gate: Benchmark health (ETF only) ---
    if mode == "etf":
        bench_fast = strat.get("bench_ema_fast", 20)
        bench_slow = strat.get("bench_ema_slow", 50)
        if not bench_daily.empty:
            b_ema_f = ta.ema(bench_daily["Close"], length=bench_fast)
            b_ema_s = ta.ema(bench_daily["Close"], length=bench_slow)
            bench_health = (b_ema_f > b_ema_s).fillna(False)
            signals["gate_bench"] = bench_health.reindex(idx, method="ffill").fillna(True)
        else:
            signals["gate_bench"] = True
    else:
        signals["gate_bench"] = True

    # --- GO signal: score >= go_threshold AND all gates pass ---
    go_thresh = cfg["alerts"]["go_threshold"]
    signals["go"] = (
        (signals["score"] >= go_thresh)
        & signals["gate_vix"]
        & signals["gate_adx"]
        & signals["gate_bench"]
    )

    # --- ATR for stop/TP computation ---
    atr = ta.atr(
        df_daily["High"], df_daily["Low"], df_daily["Close"],
        length=strat["atr_length"],
    )
    signals["atr"] = atr if atr is not None else 0.0

    # --- Close price for convenience ---
    signals["close"] = df_daily["Close"]

    return signals
