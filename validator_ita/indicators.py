import pandas_ta as ta

from shared.data import get_daily


def get_position_size(df, cfg: dict) -> int:
    """Risk-based position sizing for CFDs with leverage.

    position_size = min(
        (capital * risk_pct) / (ATR * multiplier),             # risk-based
        (capital * max_capital_pct * leverage) / price          # margin cap
    )
    """
    ps_cfg = cfg.get("position_sizing", {})
    capital = ps_cfg.get("capital", 1000)
    risk_pct = ps_cfg.get("risk_per_trade", 0.02)
    leverage = ps_cfg.get("leverage", 5)
    max_cap_pct = ps_cfg.get("max_capital_pct", 0.40)
    atr = ta.atr(
        df["High"], df["Low"], df["Close"], length=cfg["strategy"]["atr_length"]
    )
    if atr is None:
        return 0
    atr_val = float(atr.iloc[-1])
    if atr_val <= 0:
        return 0
    stop_distance = atr_val * cfg["strategy"]["atr_multiplier"]
    if stop_distance <= 0:
        return 0
    risk_amount = capital * risk_pct
    risk_shares = int(risk_amount / stop_distance)
    price = float(df["Close"].iloc[-1])
    if price <= 0:
        return 0
    max_notional = capital * max_cap_pct * leverage
    max_shares = int(max_notional / price)
    return min(risk_shares, max_shares)
