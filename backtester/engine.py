"""Core backtest simulation engine.

Walks bar-by-bar through historical data, enters on GO signals,
manages SL / TP1 (50% close + breakeven) / Chandelier trailing stop.

Cash accounting:
- CFD mode (ITA): margin = notional / leverage is locked. P&L is cash-settled.
- Cash mode (ETF): full notional is spent to buy shares.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    position_size: int
    initial_stop: float
    tp1_price: float

    # mutable state
    tp1_hit: bool = False
    tp1_date: Optional[pd.Timestamp] = None
    shares_remaining: int = 0
    current_stop: float = 0.0
    exit_date: Optional[pd.Timestamp] = None
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0

    def __post_init__(self):
        self.shares_remaining = self.position_size
        self.current_stop = self.initial_stop


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


def compute_position_size(
    price: float, atr_val: float, cfg: dict, mode: str = "ita"
) -> int:
    """Risk-based position sizing matching validator_ita/etf logic."""
    ps_cfg = cfg.get("position_sizing", {})
    capital = ps_cfg.get("capital", 1000)
    risk_pct = ps_cfg.get("risk_per_trade", 0.02)
    max_cap_pct = ps_cfg.get("max_capital_pct", 0.40)
    atr_mult = cfg["strategy"]["atr_multiplier"]

    stop_distance = atr_val * atr_mult
    if stop_distance <= 0 or price <= 0:
        return 0

    risk_amount = capital * risk_pct
    risk_shares = int(risk_amount / stop_distance)

    if mode == "ita":
        leverage = ps_cfg.get("leverage", 5)
        max_notional = capital * max_cap_pct * leverage
    else:
        max_notional = capital * max_cap_pct

    max_shares = int(max_notional / price)
    return min(risk_shares, max_shares)


def _entry_cost(shares: int, price: float, commission: float, mode: str, leverage: int) -> float:
    """Cash outflow to open a position."""
    if mode == "ita":
        return shares * price / leverage + commission
    return shares * price + commission


def _close_proceeds(shares: int, entry_price: float, exit_price: float,
                    commission: float, mode: str, leverage: int) -> tuple[float, float]:
    """Returns (cash_inflow, realized_pnl) when closing shares."""
    pnl = (exit_price - entry_price) * shares - commission
    if mode == "ita":
        # CFD: get margin back + P&L
        margin_back = shares * entry_price / leverage
        cash_in = margin_back + pnl
    else:
        # Cash: sell shares at exit_price
        cash_in = shares * exit_price - commission
    return cash_in, pnl


def _mark_to_market(cash: float, trade: Optional["Trade"], current_price: float,
                    mode: str, leverage: int) -> float:
    """Equity = cash + value of open position."""
    if trade is None:
        return cash
    unrealized_pnl = (current_price - trade.entry_price) * trade.shares_remaining
    if mode == "ita":
        # Margin is already deducted from cash; position value = margin + unrealized P&L
        margin_locked = trade.shares_remaining * trade.entry_price / leverage
        return cash + margin_locked + unrealized_pnl
    else:
        # Shares are worth current_price each
        return cash + trade.shares_remaining * current_price


def run_backtest(
    signals_df: pd.DataFrame,
    df_daily: pd.DataFrame,
    cfg: dict,
    ticker: str = "",
    mode: str = "ita",
) -> BacktestResult:
    """Run bar-by-bar backtest simulation.

    Trade lifecycle:
    1. Enter on GO signal at Close
    2. Check stop loss (Low <= current_stop) -> exit full remaining position
    3. Check TP1 (High >= tp1_price) -> close 50%, move stop to breakeven
    4. After TP1 hit, trail with Chandelier stop (ratchets up only)
    """
    capital = cfg["position_sizing"]["capital"]
    leverage = cfg["position_sizing"].get("leverage", 1) if mode == "ita" else 1
    atr_mult = cfg["strategy"]["atr_multiplier"]
    chandelier_lookback = cfg["strategy"].get("chandelier_lookback", 22)
    chandelier_atr_mult = cfg["strategy"].get("chandelier_atr_mult", 3.0)
    commission = cfg["position_sizing"].get("commission", 0.0)

    trades: list[Trade] = []
    open_trade: Optional[Trade] = None
    cash = float(capital)
    equity_values = []
    equity_dates = []

    for date, row in df_daily.iterrows():
        if date not in signals_df.index:
            eq = _mark_to_market(cash, open_trade, float(row["Close"]), mode, leverage)
            equity_values.append(eq)
            equity_dates.append(date)
            continue

        sig = signals_df.loc[date]
        atr_val = sig["atr"]

        # --- Process exits on open trade ---
        if open_trade is not None:
            # Stop loss check: did intraday Low breach the stop?
            if row["Low"] <= open_trade.current_stop:
                exit_price = open_trade.current_stop
                reason = "chandelier" if open_trade.tp1_hit else "stop_loss"
                cash_in, pnl = _close_proceeds(
                    open_trade.shares_remaining, open_trade.entry_price,
                    exit_price, commission, mode, leverage
                )
                cash += cash_in
                open_trade.pnl += pnl
                open_trade.exit_date = date
                open_trade.exit_price = exit_price
                open_trade.exit_reason = reason
                open_trade.shares_remaining = 0
                trades.append(open_trade)
                open_trade = None

            # TP1 check (only if not yet hit and trade still open)
            elif not open_trade.tp1_hit and row["High"] >= open_trade.tp1_price:
                half = open_trade.position_size // 2
                if half < 1:
                    half = open_trade.position_size
                cash_in, pnl = _close_proceeds(
                    half, open_trade.entry_price, open_trade.tp1_price,
                    commission, mode, leverage
                )
                cash += cash_in
                open_trade.pnl += pnl
                open_trade.tp1_hit = True
                open_trade.tp1_date = date
                open_trade.shares_remaining -= half

                if open_trade.shares_remaining <= 0:
                    open_trade.exit_date = date
                    open_trade.exit_price = open_trade.tp1_price
                    open_trade.exit_reason = "tp1_full"
                    trades.append(open_trade)
                    open_trade = None
                else:
                    open_trade.current_stop = open_trade.entry_price

            # Update Chandelier trailing stop (only after TP1 hit)
            elif open_trade.tp1_hit and not pd.isna(atr_val) and atr_val > 0:
                hist = df_daily.loc[:date]
                if len(hist) >= chandelier_lookback:
                    highest_high = float(hist["High"].iloc[-chandelier_lookback:].max())
                    new_chandelier = highest_high - atr_val * chandelier_atr_mult
                    open_trade.current_stop = max(open_trade.current_stop, new_chandelier)

                # Check if close breaches chandelier stop
                if row["Close"] < open_trade.current_stop:
                    exit_price = row["Close"]
                    cash_in, pnl = _close_proceeds(
                        open_trade.shares_remaining, open_trade.entry_price,
                        exit_price, commission, mode, leverage
                    )
                    cash += cash_in
                    open_trade.pnl += pnl
                    open_trade.exit_date = date
                    open_trade.exit_price = exit_price
                    open_trade.exit_reason = "chandelier"
                    open_trade.shares_remaining = 0
                    trades.append(open_trade)
                    open_trade = None

        # --- Check entry (only if no open trade) ---
        if open_trade is None and sig["go"] and not pd.isna(atr_val) and atr_val > 0:
            entry_price = float(row["Close"])
            pos_size = compute_position_size(entry_price, atr_val, cfg, mode)
            if pos_size > 0:
                stop = entry_price - atr_val * atr_mult
                tp1 = entry_price + atr_val * atr_mult
                cost = _entry_cost(pos_size, entry_price, commission, mode, leverage)
                if cost <= cash:
                    cash -= cost
                    open_trade = Trade(
                        ticker=ticker,
                        entry_date=date,
                        entry_price=entry_price,
                        position_size=pos_size,
                        initial_stop=stop,
                        tp1_price=tp1,
                    )

        # --- Mark-to-market equity ---
        eq = _mark_to_market(cash, open_trade, float(row["Close"]), mode, leverage)
        equity_values.append(eq)
        equity_dates.append(date)

    # Close any open trade at end of data
    if open_trade is not None:
        last_close = float(df_daily["Close"].iloc[-1])
        cash_in, pnl = _close_proceeds(
            open_trade.shares_remaining, open_trade.entry_price,
            last_close, commission, mode, leverage
        )
        cash += cash_in
        open_trade.pnl += pnl
        open_trade.exit_date = df_daily.index[-1]
        open_trade.exit_price = last_close
        open_trade.exit_reason = "end_of_data"
        open_trade.shares_remaining = 0
        trades.append(open_trade)
        # Update last equity point
        if equity_values:
            equity_values[-1] = cash

    equity = pd.Series(equity_values, index=equity_dates, name="equity")
    daily_returns = equity.pct_change().fillna(0.0)

    return BacktestResult(trades=trades, equity_curve=equity, daily_returns=daily_returns)
