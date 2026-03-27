"""Performance metrics and reporting for backtest results."""

import csv
import os

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from backtester.engine import BacktestResult, Trade

TRADING_DAYS_PER_YEAR = 252


def compute_metrics(
    result: BacktestResult, cfg: dict, risk_free_rate: float = 0.03
) -> dict:
    """Compute standard backtest performance metrics."""
    trades = result.trades
    equity = result.equity_curve
    daily_ret = result.daily_returns

    initial_capital = cfg["position_sizing"]["capital"]

    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "avg_rr": 0.0,
            "profit_factor": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "avg_holding_days": 0,
            "max_holding_days": 0,
            "expectancy": 0.0,
            "final_equity": initial_capital,
        }

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]

    total = len(trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total if total > 0 else 0.0

    avg_win = np.mean([t.pnl for t in wins]) if wins else 0.0
    avg_loss = np.mean([abs(t.pnl) for t in losses]) if losses else 0.0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else float("inf")

    total_wins = sum(t.pnl for t in wins)
    total_losses = sum(abs(t.pnl) for t in losses)
    profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

    final_equity = float(equity.iloc[-1]) if len(equity) > 0 else initial_capital
    total_return_pct = (final_equity - initial_capital) / initial_capital * 100

    # Max drawdown
    peak = equity.expanding().max()
    drawdown = (equity - peak) / peak
    max_drawdown_pct = float(drawdown.min()) * 100 if len(drawdown) > 0 else 0.0

    # Sharpe ratio (annualized)
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        excess_return = daily_ret.mean() - risk_free_rate / TRADING_DAYS_PER_YEAR
        sharpe = excess_return / daily_ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        sharpe = 0.0

    # Sortino ratio
    downside = daily_ret[daily_ret < 0]
    if len(downside) > 0 and downside.std() > 0:
        excess_return = daily_ret.mean() - risk_free_rate / TRADING_DAYS_PER_YEAR
        sortino = excess_return / downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        sortino = 0.0

    # Calmar ratio
    ann_return = daily_ret.mean() * TRADING_DAYS_PER_YEAR
    calmar = ann_return / abs(max_drawdown_pct / 100) if max_drawdown_pct != 0 else 0.0

    # Holding days
    holding_days = []
    for t in trades:
        if t.exit_date is not None:
            delta = (t.exit_date - t.entry_date).days
            holding_days.append(delta)
    avg_holding = int(np.mean(holding_days)) if holding_days else 0
    max_holding = int(max(holding_days)) if holding_days else 0

    # Expectancy
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    return {
        "total_trades": total,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "win_rate": round(win_rate * 100, 1),
        "avg_win": round(float(avg_win), 2),
        "avg_loss": round(float(avg_loss), 2),
        "avg_rr": round(float(avg_rr), 2),
        "profit_factor": round(float(profit_factor), 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe_ratio": round(float(sharpe), 2),
        "sortino_ratio": round(float(sortino), 2),
        "calmar_ratio": round(float(calmar), 2),
        "avg_holding_days": avg_holding,
        "max_holding_days": max_holding,
        "expectancy": round(float(expectancy), 2),
        "final_equity": round(final_equity, 2),
    }


def print_metrics(metrics: dict, ticker: str) -> None:
    """Print metrics using rich table."""
    console = Console()

    table = Table(title=f"Backtest Results: {ticker}", show_lines=True)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="bold", justify="right")

    rows = [
        ("Total Trades", str(metrics["total_trades"])),
        ("Winning", str(metrics["winning_trades"])),
        ("Losing", str(metrics["losing_trades"])),
        ("Win Rate", f"{metrics['win_rate']}%"),
        ("Avg Win", f"\u20ac{metrics['avg_win']}"),
        ("Avg Loss", f"\u20ac{metrics['avg_loss']}"),
        ("Avg R:R", f"{metrics['avg_rr']}"),
        ("Profit Factor", f"{metrics['profit_factor']}"),
        ("Expectancy", f"\u20ac{metrics['expectancy']}"),
        ("Total Return", f"{metrics['total_return_pct']}%"),
        ("Max Drawdown", f"{metrics['max_drawdown_pct']}%"),
        ("Sharpe Ratio", f"{metrics['sharpe_ratio']}"),
        ("Sortino Ratio", f"{metrics['sortino_ratio']}"),
        ("Calmar Ratio", f"{metrics['calmar_ratio']}"),
        ("Avg Holding Days", f"{metrics['avg_holding_days']}"),
        ("Max Holding Days", f"{metrics['max_holding_days']}"),
        ("Final Equity", f"\u20ac{metrics['final_equity']}"),
    ]

    for label, value in rows:
        table.add_row(label, value)

    console.print(table)


def save_trades_csv(trades: list[Trade], output_dir: str, ticker: str) -> str:
    """Save trade log to CSV. Returns the file path."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"trades_{ticker.replace('.', '_')}.csv")

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ticker", "entry_date", "entry_price", "position_size",
            "initial_stop", "tp1_price", "tp1_hit", "tp1_date",
            "exit_date", "exit_price", "exit_reason", "pnl",
        ])
        for t in trades:
            writer.writerow([
                t.ticker,
                t.entry_date.strftime("%Y-%m-%d") if t.entry_date else "",
                round(t.entry_price, 4),
                t.position_size,
                round(t.initial_stop, 4),
                round(t.tp1_price, 4),
                t.tp1_hit,
                t.tp1_date.strftime("%Y-%m-%d") if t.tp1_date else "",
                t.exit_date.strftime("%Y-%m-%d") if t.exit_date else "",
                round(t.exit_price, 4),
                t.exit_reason,
                round(t.pnl, 2),
            ])

    return path
