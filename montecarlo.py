#!/usr/bin/env python3
"""Monte Carlo simulation for trade-order sensitivity analysis.

Runs the strategy across the full ticker universe, collects all trades,
then shuffles trade order N times to produce confidence intervals on
equity, drawdown, and probability of ruin.

Usage:
    python montecarlo.py --mode ita                          # ITA, 10k sims
    python montecarlo.py --mode us                           # US, 10k sims
    python montecarlo.py --mode ita --simulations 50000      # more sims
    python montecarlo.py --mode us --save-plot               # save histogram
    python montecarlo.py --mode ita --start 2022-01-01       # custom period
"""

import argparse
import csv
import logging
import os
import time

import numpy as np
import yaml
from rich.console import Console
from rich.table import Table

from backtester.data import fetch_historical, fetch_weekly_historical, warmup_start
from backtester.engine import run_backtest
from backtester.signals import compute_all_signals

console = Console()

MODE_CONFIG = {
    "ita": {
        "config_path": "config_ita.yaml",
        "benchmark": "ETFMIB.MI",
        "bt_mode": "ita",
    },
    "us": {
        "config_path": "config_us.yaml",
        "benchmark": "SPY",
        "bt_mode": "ita",
        "use_sample": True,
    },
}


def _load_tickers(config_path: str, use_sample: bool = False) -> list[str]:
    """Load tickers from config YAML."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    if use_sample and "optimization_sample" in cfg:
        return cfg["optimization_sample"]
    return cfg["tickers"]


def collect_trades(
    cfg: dict, tickers: list[str], benchmark: str,
    start: str, end: str, bt_mode: str,
) -> list[float]:
    """Run backtest across universe and collect all trade PnLs."""
    ws = warmup_start(start, extra_bars=100)

    bench_daily = fetch_historical(benchmark, ws, end)
    vix_daily = fetch_historical("^VIX", ws, end)

    all_pnl = []
    loaded = 0

    for i, ticker in enumerate(tickers, 1):
        console.print(f"  [{i}/{len(tickers)}] {ticker}", end="\r")

        df_daily = fetch_historical(ticker, ws, end)
        df_weekly = fetch_weekly_historical(ticker, ws, end)

        if df_daily.empty or len(df_daily) < 60:
            continue

        signals = compute_all_signals(
            df_daily, df_weekly, bench_daily, vix_daily, cfg, mode=bt_mode
        )
        signals_bt = signals.loc[start:]
        df_bt = df_daily.loc[start:]

        if df_bt.empty:
            continue

        result = run_backtest(signals_bt, df_bt, cfg, ticker=ticker, mode=bt_mode)
        for trade in result.trades:
            all_pnl.append(trade.pnl)
        loaded += 1

    console.print(f"  Loaded {loaded} tickers, collected {len(all_pnl)} trades.    ")
    return all_pnl


def run_montecarlo(
    trades_pnl: list[float],
    initial_capital: float,
    n_simulations: int = 10_000,
    ruin_threshold: float = 0.5,
) -> dict:
    """Shuffle trade PnL order and compute equity distribution.

    For each simulation:
      1. Start with initial_capital
      2. Apply each trade PnL in shuffled order
      3. Track running equity, peak, drawdown

    Returns dict with percentile statistics and ruin probability.
    """
    pnl_array = np.array(trades_pnl)
    n_trades = len(pnl_array)

    final_equities = np.empty(n_simulations)
    max_drawdowns = np.empty(n_simulations)
    total_returns = np.empty(n_simulations)

    ruin_level = initial_capital * ruin_threshold

    for sim in range(n_simulations):
        shuffled = np.random.permutation(pnl_array)
        equity = np.empty(n_trades + 1)
        equity[0] = initial_capital

        for j in range(n_trades):
            equity[j + 1] = equity[j] + shuffled[j]

        peak = np.maximum.accumulate(equity)
        drawdown_pct = np.where(peak > 0, (equity - peak) / peak * 100, 0.0)

        final_equities[sim] = equity[-1]
        max_drawdowns[sim] = drawdown_pct.min()
        total_returns[sim] = (equity[-1] - initial_capital) / initial_capital * 100

    percentiles = [5, 25, 50, 75, 95]

    return {
        "n_simulations": n_simulations,
        "n_trades": n_trades,
        "initial_capital": initial_capital,
        # Final equity stats
        "equity_mean": float(np.mean(final_equities)),
        "equity_std": float(np.std(final_equities)),
        "equity_percentiles": {
            p: float(np.percentile(final_equities, p)) for p in percentiles
        },
        # Total return stats
        "return_mean": float(np.mean(total_returns)),
        "return_std": float(np.std(total_returns)),
        "return_percentiles": {
            p: float(np.percentile(total_returns, p)) for p in percentiles
        },
        # Max drawdown stats
        "dd_mean": float(np.mean(max_drawdowns)),
        "dd_std": float(np.std(max_drawdowns)),
        "dd_percentiles": {
            p: float(np.percentile(max_drawdowns, p)) for p in percentiles
        },
        # Risk metrics
        "prob_ruin": float(np.mean(final_equities < ruin_level)),
        "prob_profit": float(np.mean(total_returns > 0)),
        "prob_loss": float(np.mean(total_returns <= 0)),
        "worst_equity": float(np.min(final_equities)),
        "best_equity": float(np.max(final_equities)),
        "worst_dd": float(np.min(max_drawdowns)),
        # Raw arrays for plotting
        "_final_equities": final_equities,
        "_max_drawdowns": max_drawdowns,
        "_total_returns": total_returns,
    }


def print_results(results: dict, mode: str) -> None:
    """Print Monte Carlo results as Rich tables."""
    currency = "$" if mode == "us" else "\u20ac"
    cap = results["initial_capital"]

    console.print(f"\n[bold]Monte Carlo Results — {mode.upper()} CFD[/bold]")
    console.print(
        f"Simulations: {results['n_simulations']:,} | "
        f"Trades shuffled: {results['n_trades']:,} | "
        f"Initial capital: {currency}{cap:,.0f}"
    )
    console.print()

    # --- Equity distribution ---
    eq_table = Table(title="Final Equity Distribution", show_lines=True)
    eq_table.add_column("Percentile", style="cyan", justify="center")
    eq_table.add_column("Equity", justify="right")
    eq_table.add_column("Return", justify="right")
    eq_table.add_column("Max Drawdown", justify="right")

    for p in [5, 25, 50, 75, 95]:
        eq = results["equity_percentiles"][p]
        ret = results["return_percentiles"][p]
        dd = results["dd_percentiles"][p]
        ret_style = "green" if ret >= 0 else "red"
        eq_table.add_row(
            f"P{p}",
            f"{currency}{eq:,.0f}",
            f"[{ret_style}]{ret:+.1f}%[/{ret_style}]",
            f"[red]{dd:.1f}%[/red]",
        )

    console.print(eq_table)

    # --- Summary stats ---
    stats = Table(title="Summary Statistics", show_lines=True)
    stats.add_column("Metric", style="cyan")
    stats.add_column("Value", justify="right", style="bold")

    stats.add_row("Mean return", f"{results['return_mean']:+.2f}%")
    stats.add_row("Std dev return", f"{results['return_std']:.2f}%")
    stats.add_row("Mean max drawdown", f"{results['dd_mean']:.1f}%")
    stats.add_row("Worst drawdown (any sim)", f"{results['worst_dd']:.1f}%")
    stats.add_row("", "")
    stats.add_row(
        "Probability of profit",
        f"[green]{results['prob_profit']*100:.1f}%[/green]",
    )
    stats.add_row(
        "Probability of loss",
        f"[red]{results['prob_loss']*100:.1f}%[/red]",
    )
    stats.add_row(
        "Probability of ruin (<50% capital)",
        f"[{'red' if results['prob_ruin'] > 0.05 else 'green'}]"
        f"{results['prob_ruin']*100:.2f}%[/]",
    )
    stats.add_row("", "")
    stats.add_row("Best final equity", f"{currency}{results['best_equity']:,.0f}")
    stats.add_row("Worst final equity", f"{currency}{results['worst_equity']:,.0f}")
    stats.add_row(
        "Median final equity",
        f"{currency}{results['equity_percentiles'][50]:,.0f}",
    )

    console.print(stats)


def save_plot(results: dict, output_dir: str, mode: str) -> None:
    """Save equity distribution histogram and drawdown histogram."""
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)
    currency = "$" if mode == "us" else "\u20ac"

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Equity distribution
    ax = axes[0]
    ax.hist(results["_final_equities"], bins=80, color="steelblue", edgecolor="none", alpha=0.8)
    for p in [5, 50, 95]:
        val = results["equity_percentiles"][p]
        ax.axvline(val, color="red" if p == 5 else "orange" if p == 50 else "green",
                    linestyle="--", linewidth=1.5, label=f"P{p}: {currency}{val:,.0f}")
    ax.axvline(results["initial_capital"], color="black", linestyle="-", linewidth=1, label="Initial")
    ax.set_xlabel(f"Final Equity ({currency})")
    ax.set_ylabel("Frequency")
    ax.set_title("Final Equity Distribution")
    ax.legend(fontsize=8)

    # Return distribution
    ax = axes[1]
    returns = results["_total_returns"]
    ax.hist(returns, bins=80, color="seagreen", edgecolor="none", alpha=0.8)
    ax.axvline(0, color="black", linestyle="-", linewidth=1)
    ax.axvline(results["return_percentiles"][50], color="orange", linestyle="--",
               linewidth=1.5, label=f"Median: {results['return_percentiles'][50]:+.1f}%")
    ax.set_xlabel("Total Return (%)")
    ax.set_ylabel("Frequency")
    ax.set_title("Return Distribution")
    ax.legend(fontsize=8)

    # Max drawdown distribution
    ax = axes[2]
    ax.hist(results["_max_drawdowns"], bins=80, color="indianred", edgecolor="none", alpha=0.8)
    ax.axvline(results["dd_percentiles"][50], color="orange", linestyle="--",
               linewidth=1.5, label=f"Median: {results['dd_percentiles'][50]:.1f}%")
    ax.axvline(results["dd_percentiles"][5], color="red", linestyle="--",
               linewidth=1.5, label=f"P5: {results['dd_percentiles'][5]:.1f}%")
    ax.set_xlabel("Max Drawdown (%)")
    ax.set_ylabel("Frequency")
    ax.set_title("Max Drawdown Distribution")
    ax.legend(fontsize=8)

    fig.suptitle(
        f"Monte Carlo Simulation — {mode.upper()} CFD "
        f"({results['n_simulations']:,} sims, {results['n_trades']} trades)",
        fontsize=13, fontweight="bold",
    )
    fig.tight_layout()

    path = os.path.join(output_dir, f"montecarlo_{mode}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"\n[dim]Plot saved to {path}[/dim]")


def save_csv_report(results: dict, output_dir: str, mode: str) -> None:
    """Save Monte Carlo results to CSV."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"montecarlo_{mode}.csv")

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["mode", mode])
        writer.writerow(["simulations", results["n_simulations"]])
        writer.writerow(["trades", results["n_trades"]])
        writer.writerow(["initial_capital", results["initial_capital"]])
        writer.writerow(["return_mean", f"{results['return_mean']:.4f}"])
        writer.writerow(["return_std", f"{results['return_std']:.4f}"])
        writer.writerow(["dd_mean", f"{results['dd_mean']:.4f}"])
        writer.writerow(["dd_worst", f"{results['worst_dd']:.4f}"])
        writer.writerow(["prob_profit", f"{results['prob_profit']:.6f}"])
        writer.writerow(["prob_ruin", f"{results['prob_ruin']:.6f}"])
        for p in [5, 25, 50, 75, 95]:
            writer.writerow([f"equity_p{p}", f"{results['equity_percentiles'][p]:.2f}"])
            writer.writerow([f"return_p{p}", f"{results['return_percentiles'][p]:.4f}"])
            writer.writerow([f"dd_p{p}", f"{results['dd_percentiles'][p]:.4f}"])

    console.print(f"[dim]CSV saved to {path}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monte Carlo simulation for trade-order sensitivity analysis"
    )
    parser.add_argument(
        "--mode", choices=["ita", "us"], required=True,
        help="Strategy mode (ita or us)",
    )
    parser.add_argument(
        "--simulations", type=int, default=10_000,
        help="Number of Monte Carlo simulations (default: 10,000)",
    )
    parser.add_argument("--start", type=str, default="2020-01-01", help="Backtest start date")
    parser.add_argument("--end", type=str, default="2024-12-31", help="Backtest end date")
    parser.add_argument("--save-plot", action="store_true", help="Save distribution plots")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    mc = MODE_CONFIG[args.mode]
    with open(mc["config_path"]) as f:
        cfg = yaml.safe_load(f)

    tickers = _load_tickers(mc["config_path"], mc.get("use_sample", False))
    output_dir = args.output_dir or f"output/montecarlo_{args.mode}"
    initial_capital = cfg["position_sizing"]["capital"]

    console.print(f"\n[bold]Monte Carlo Simulation — {args.mode.upper()} CFD[/bold]")
    console.print(f"Period: {args.start} to {args.end}")
    console.print(f"Tickers: {len(tickers)}")
    console.print(f"Simulations: {args.simulations:,}")
    console.print(f"Benchmark: {mc['benchmark']}\n")

    # Phase 1: Collect trades from backtest
    console.print("[bold]Phase 1: Running backtest to collect trades...[/bold]")
    t0 = time.time()

    trades_pnl = collect_trades(
        cfg=cfg,
        tickers=tickers,
        benchmark=mc["benchmark"],
        start=args.start,
        end=args.end,
        bt_mode=mc["bt_mode"],
    )

    t1 = time.time()
    console.print(f"  Backtest completed in {t1 - t0:.1f}s\n")

    if len(trades_pnl) < 10:
        console.print("[red]Too few trades for meaningful Monte Carlo analysis.[/red]")
        return

    # Trade summary
    pnl_arr = np.array(trades_pnl)
    wins = np.sum(pnl_arr > 0)
    console.print(f"  Total trades: {len(pnl_arr)}")
    console.print(f"  Winning: {wins} ({wins/len(pnl_arr)*100:.1f}%)")
    console.print(f"  Total PnL: {np.sum(pnl_arr):+.2f}")
    console.print(f"  Avg PnL/trade: {np.mean(pnl_arr):+.2f}")
    console.print()

    # Phase 2: Monte Carlo simulation
    console.print(f"[bold]Phase 2: Running {args.simulations:,} simulations...[/bold]")
    t2 = time.time()

    results = run_montecarlo(
        trades_pnl=trades_pnl,
        initial_capital=initial_capital,
        n_simulations=args.simulations,
    )

    t3 = time.time()
    console.print(f"  Completed in {t3 - t2:.1f}s\n")

    # Output
    print_results(results, args.mode)
    save_csv_report(results, output_dir, args.mode)

    if args.save_plot:
        save_plot(results, output_dir, args.mode)

    console.print(f"\n[bold]Done in {t3 - t0:.1f}s total.[/bold]\n")


if __name__ == "__main__":
    main()
