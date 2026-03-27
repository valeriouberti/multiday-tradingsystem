"""Visualization: equity curve, drawdown, and price chart with trade markers."""

import os

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from backtester.engine import BacktestResult, Trade


def plot_equity_curve(
    result: BacktestResult, ticker: str, output_path: str | None = None
) -> None:
    """Two-panel plot: equity curve (top) and drawdown (bottom)."""
    equity = result.equity_curve
    if equity.empty:
        return

    peak = equity.expanding().max()
    drawdown = (equity - peak) / peak * 100

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(f"Backtest: {ticker}", fontsize=14, fontweight="bold")

    # Equity
    ax1.plot(equity.index, equity.values, color="#2196F3", linewidth=1.2)
    ax1.fill_between(equity.index, equity.values, alpha=0.1, color="#2196F3")
    ax1.set_ylabel("Equity (\u20ac)")
    ax1.grid(True, alpha=0.3)

    # Drawdown
    ax2.fill_between(drawdown.index, drawdown.values, 0, color="#F44336", alpha=0.4)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    fig.autofmt_xdate()

    plt.tight_layout()
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


def plot_trades_on_price(
    df_daily: pd.DataFrame,
    trades: list[Trade],
    ticker: str,
    output_path: str | None = None,
) -> None:
    """Price chart with entry/exit markers and stop levels."""
    if df_daily.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(df_daily.index, df_daily["Close"], color="#666", linewidth=0.8, label="Close")

    for t in trades:
        # Entry marker (green up arrow)
        ax.scatter(t.entry_date, t.entry_price, marker="^", color="#4CAF50",
                   s=100, zorder=5, edgecolors="black", linewidths=0.5)

        # TP1 marker (orange diamond)
        if t.tp1_hit and t.tp1_date is not None:
            ax.scatter(t.tp1_date, t.tp1_price, marker="D", color="#FF9800",
                       s=60, zorder=5, edgecolors="black", linewidths=0.5)

        # Exit marker
        if t.exit_date is not None:
            color = "#F44336" if t.exit_reason in ("stop_loss", "chandelier") else "#9E9E9E"
            ax.scatter(t.exit_date, t.exit_price, marker="v", color=color,
                       s=100, zorder=5, edgecolors="black", linewidths=0.5)

            # Line from entry to exit
            line_color = "#4CAF50" if t.pnl > 0 else "#F44336"
            ax.plot([t.entry_date, t.exit_date], [t.entry_price, t.exit_price],
                    linestyle="--", color=line_color, alpha=0.4, linewidth=0.8)

    ax.set_title(f"{ticker} - Trades", fontsize=12, fontweight="bold")
    ax.set_ylabel("Price (\u20ac)")
    ax.set_xlabel("Date")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    fig.autofmt_xdate()

    # Legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#4CAF50", markersize=10, label="Entry"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor="#FF9800", markersize=8, label="TP1 (50%)"),
        Line2D([0], [0], marker="v", color="w", markerfacecolor="#F44336", markersize=10, label="Stop Exit"),
    ]
    ax.legend(handles=legend_elements, loc="upper left")

    plt.tight_layout()
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
