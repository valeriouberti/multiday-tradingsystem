import pandas as pd
import pandas_ta as ta

from shared.data import get_daily, get_weekly


# =========================================================================
# 6 SCORED CHECKS (common to ITA and ETF)
# =========================================================================

def check_ema_cross(df: pd.DataFrame, cfg: dict) -> tuple[bool, str]:
    """Check 1: Daily EMA fast > EMA slow (trend direction)."""
    ema_fast = ta.ema(df["Close"], length=cfg["strategy"]["ema_fast"])
    ema_slow = ta.ema(df["Close"], length=cfg["strategy"]["ema_slow"])
    if ema_fast is None or ema_slow is None:
        return False, ""
    return bool(ema_fast.iloc[-1] > ema_slow.iloc[-1]), ""


def check_weekly_ema(ticker: str, cfg: dict) -> tuple[bool, str]:
    """Check 2: Weekly EMA fast > EMA slow (structural trend)."""
    df_w = get_weekly(ticker, cfg)
    if df_w.empty:
        return False, ""
    fast = cfg["strategy"].get("weekly_ema_fast", 20)
    slow = cfg["strategy"].get("weekly_ema_slow", 50)
    ema_fast = ta.ema(df_w["Close"], length=fast)
    ema_slow = ta.ema(df_w["Close"], length=slow)
    if ema_fast is None or ema_slow is None:
        return False, ""
    return bool(ema_fast.iloc[-1] > ema_slow.iloc[-1]), ""


def check_macd(df: pd.DataFrame, cfg: dict) -> tuple[bool, str]:
    """Check 3: MACD line > Signal line (momentum confirmation)."""
    macd_result = ta.macd(
        df["Close"],
        fast=cfg["strategy"]["macd_fast"],
        slow=cfg["strategy"]["macd_slow"],
        signal=cfg["strategy"]["macd_signal"],
    )
    if macd_result is None or macd_result.empty:
        return False, ""
    macd_col = [c for c in macd_result.columns if c.startswith("MACD_")]
    signal_col = [c for c in macd_result.columns if c.startswith("MACDs_")]
    if not macd_col or not signal_col:
        return False, ""
    return bool(macd_result[macd_col[0]].iloc[-1] > macd_result[signal_col[0]].iloc[-1]), ""


def check_rsi(df: pd.DataFrame, cfg: dict) -> tuple[bool, str]:
    """Check 4: RSI > threshold (momentum filter)."""
    rsi = ta.rsi(df["Close"], length=cfg["strategy"]["rsi_length"])
    if rsi is None:
        return False, ""
    rsi_val = round(rsi.iloc[-1])
    return bool(rsi_val > cfg["strategy"]["rsi_threshold"]), str(rsi_val)


def check_mfi(df: pd.DataFrame, cfg: dict) -> tuple[bool, str]:
    """Check 5: MFI > threshold (Money Flow Index).

    MFI is more reliable than OBV on Italian stocks and ETFs where
    volume can be lower or distorted by market makers / creation-redemption.
    """
    length = cfg["strategy"].get("mfi_length", 14)
    threshold = cfg["strategy"].get("mfi_threshold", 50)
    mfi = ta.mfi(df["High"], df["Low"], df["Close"], df["Volume"], length=length)
    if mfi is None:
        return False, ""
    mfi_val = round(mfi.iloc[-1])
    return bool(mfi_val > threshold), str(mfi_val)


def check_rs_vs_benchmark(
    ticker_df: pd.DataFrame, cfg: dict
) -> tuple[bool, str]:
    """Check 6: RS vs benchmark rising (20d lookback, 5d ROC)."""
    benchmark = cfg.get("benchmark", "ETFMIB.MI")
    lookback = cfg["strategy"].get("rs_lookback_days", 20)
    roc_days = cfg["strategy"].get("rs_roc_days", 5)
    try:
        bench_df = get_daily(benchmark, cfg)
        if ticker_df.empty or bench_df.empty:
            return False, benchmark
        common_idx = ticker_df.index.intersection(bench_df.index)
        if len(common_idx) < lookback + 1:
            return False, benchmark
        ticker_close = ticker_df.loc[common_idx, "Close"]
        bench_close = bench_df.loc[common_idx, "Close"]
        rs = ticker_close / bench_close
        if len(rs) < roc_days + 1:
            return False, benchmark
        passed = bool(rs.iloc[-1] > rs.iloc[-roc_days - 1])
        return passed, benchmark
    except Exception:
        return False, benchmark


# =========================================================================
# NUMERIC VALUES (for ranking)
# =========================================================================

def get_rs_roc_value(ticker_df: pd.DataFrame, cfg: dict) -> float:
    """Return the numeric RS ROC (%) vs benchmark over the lookback window.

    Positive = outperforming benchmark, higher = stronger relative momentum.
    Returns 0.0 on error.
    """
    benchmark = cfg.get("benchmark", "ETFMIB.MI")
    roc_days = cfg["strategy"].get("rs_roc_days", 5)
    try:
        bench_df = get_daily(benchmark, cfg)
        if ticker_df.empty or bench_df.empty:
            return 0.0
        common_idx = ticker_df.index.intersection(bench_df.index)
        if len(common_idx) < roc_days + 1:
            return 0.0
        ticker_close = ticker_df.loc[common_idx, "Close"]
        bench_close = bench_df.loc[common_idx, "Close"]
        rs = ticker_close / bench_close
        prev = float(rs.iloc[-roc_days - 1])
        if prev == 0:
            return 0.0
        return float((rs.iloc[-1] - prev) / prev * 100)
    except Exception:
        return 0.0


def get_rsi_value(df: pd.DataFrame, cfg: dict) -> float:
    """Return the current RSI value (0-100). Returns 0.0 on error."""
    rsi = ta.rsi(df["Close"], length=cfg["strategy"]["rsi_length"])
    if rsi is None:
        return 0.0
    return round(float(rsi.iloc[-1]), 1)


def get_mfi_value(df: pd.DataFrame, cfg: dict) -> float:
    """Return the current MFI value (0-100). Returns 0.0 on error."""
    length = cfg["strategy"].get("mfi_length", 14)
    mfi = ta.mfi(df["High"], df["Low"], df["Close"], df["Volume"], length=length)
    if mfi is None:
        return 0.0
    return round(float(mfi.iloc[-1]), 1)


# =========================================================================
# GATES (common)
# =========================================================================

def check_vix_regime(cfg: dict) -> tuple[bool, float]:
    """Gate: VIX must be below threshold."""
    threshold = cfg["strategy"].get("vix_threshold", 25)
    try:
        vix_df = get_daily("^VIX", cfg)
        if vix_df.empty:
            return True, 0.0
        vix_val = float(vix_df["Close"].iloc[-1])
        return vix_val < threshold, round(vix_val, 1)
    except Exception:
        return True, 0.0


def check_adx_regime(cfg: dict) -> tuple[bool, float]:
    """Gate: ADX on benchmark must be above threshold (trending market)."""
    benchmark = cfg.get("benchmark", "ETFMIB.MI")
    length = cfg["strategy"].get("adx_length", 14)
    threshold = cfg["strategy"].get("adx_threshold", 20)
    try:
        df = get_daily(benchmark, cfg)
        if df.empty:
            return True, 0.0
        adx = ta.adx(df["High"], df["Low"], df["Close"], length=length)
        if adx is None or adx.empty:
            return True, 0.0
        adx_col = [c for c in adx.columns if c.startswith("ADX_")]
        if not adx_col:
            return True, 0.0
        adx_val = float(adx[adx_col[0]].iloc[-1])
        return adx_val >= threshold, round(adx_val, 1)
    except Exception:
        return True, 0.0


# =========================================================================
# ENTRY HELPERS
# =========================================================================

def get_atr_stop(df: pd.DataFrame, cfg: dict) -> float:
    """Stop loss price: Close - ATR * multiplier."""
    atr = ta.atr(
        df["High"], df["Low"], df["Close"], length=cfg["strategy"]["atr_length"]
    )
    if atr is None:
        return 0.0
    latest_close = df["Close"].iloc[-1]
    latest_atr = atr.iloc[-1]
    stop = latest_close - latest_atr * cfg["strategy"]["atr_multiplier"]
    return round(float(stop), 2)


def get_chandelier_stop(df: pd.DataFrame, cfg: dict) -> float:
    """Chandelier Exit: Highest(High, lookback) - ATR * multiplier."""
    lookback = cfg["strategy"].get("chandelier_lookback", 22)
    atr_mult = cfg["strategy"].get("chandelier_atr_mult", 3.0)
    atr_length = cfg["strategy"]["atr_length"]

    atr = ta.atr(df["High"], df["Low"], df["Close"], length=atr_length)
    if atr is None or len(df) < lookback:
        return 0.0

    highest_high = float(df["High"].iloc[-lookback:].max())
    latest_atr = float(atr.iloc[-1])
    stop = highest_high - latest_atr * atr_mult
    return round(stop, 2)


def get_tp1_price(df: pd.DataFrame, cfg: dict) -> float:
    """TP1: Close + ATR * multiplier. Close 50%, move stop to breakeven."""
    atr = ta.atr(
        df["High"], df["Low"], df["Close"], length=cfg["strategy"]["atr_length"]
    )
    if atr is None:
        return 0.0
    latest_close = float(df["Close"].iloc[-1])
    latest_atr = float(atr.iloc[-1])
    tp1 = latest_close + latest_atr * cfg["strategy"]["atr_multiplier"]
    return round(tp1, 2)


def detect_entry_method(df_daily: pd.DataFrame, df_h1: pd.DataFrame, cfg: dict) -> str:
    """Detect entry method: GAP_UP / BONE_ZONE / PULLBACK / ORB / WAIT."""
    gap_pct = cfg["strategy"].get("gap_threshold_pct", 0.5)
    ema_bone = ta.ema(df_daily["Close"], length=cfg["strategy"]["ema_bone"])
    ema_fast = ta.ema(df_daily["Close"], length=cfg["strategy"]["ema_fast"])

    if ema_bone is not None and ema_fast is not None and len(df_daily) >= 2:
        close_now = float(df_daily["Close"].iloc[-1])
        open_now = float(df_daily["Open"].iloc[-1])
        low_now = float(df_daily["Low"].iloc[-1])
        close_prev = float(df_daily["Close"].iloc[-2])
        high_prev = float(df_daily["High"].iloc[-2])
        ema20_now = float(ema_fast.iloc[-1])
        ema9_now = float(ema_bone.iloc[-1])

        # GAP_UP
        gap = (open_now - close_prev) / close_prev * 100 if close_prev > 0 else 0
        if (open_now > ema20_now
                and open_now > high_prev
                and close_prev > ema9_now
                and gap >= gap_pct):
            return "GAP_UP"

        # BONE_ZONE
        if low_now < ema20_now and close_now > ema9_now and close_now > open_now:
            return "BONE_ZONE"

        # PULLBACK
        ema20_prev = float(ema_fast.iloc[-2])
        if close_prev < ema20_prev and close_now > ema20_now:
            return "PULLBACK"

    # ORB
    if not df_h1.empty and len(df_h1) >= 2:
        dates = df_h1.index.normalize().unique()
        if len(dates) >= 1:
            latest_day = dates[-1]
            day_bars = df_h1[df_h1.index.normalize() == latest_day]
            if len(day_bars) >= 2:
                orb_high = day_bars["High"].iloc[0]
                latest_close = day_bars["Close"].iloc[-1]
                latest_volume = day_bars["Volume"].iloc[-1]
                vol_sma = df_h1["Volume"].rolling(10).mean()
                vol_avg = vol_sma.iloc[-1] if len(vol_sma) >= 10 else df_h1["Volume"].mean()
                if latest_close > orb_high and latest_volume >= vol_avg * 1.5:
                    return "ORB"

    return "WAIT"
