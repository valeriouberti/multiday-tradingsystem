#!/usr/bin/env python3
"""Monte Carlo simulation for trade-order sensitivity analysis.

Runs the strategy across the full ticker universe, collects all trades,
then shuffles trade order N times to produce confidence intervals on
equity, drawdown, and probability of ruin.

Usage:
    python tools/montecarlo.py --mode ita                          # ITA, 10k sims
    python tools/montecarlo.py --mode us                           # US, 10k sims
    python tools/montecarlo.py --mode etf                          # ETF, 10k sims
    python tools/montecarlo.py --mode ita --simulations 50000      # more sims
    python tools/montecarlo.py --mode us --save-plot               # save histogram
    python tools/montecarlo.py --mode ita --start 2022-01-01       # custom period
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

from backtester.data import (
    fetch_historical,
    fetch_weekly_historical,
    prefetch_historical,
    warmup_start,
)
from backtester.engine import run_backtest
from backtester.signals import compute_all_signals

console = Console()

MODE_CONFIG = {
    "ita": {
        "config_path": "config/ita.yaml",
        "benchmark": "ETFMIB.MI",
        "bt_mode": "ita",
    },
    "us": {
        "config_path": "config/us.yaml",
        "benchmark": "SPY",
        "bt_mode": "ita",
        "use_sample": True,
    },
    "etf": {
        "config_path": "config/etf.yaml",
        "benchmark": "CSSPX.MI",
        "bt_mode": "etf",
    },
    "indexcfd": {
        "config_path": "config/indexcfd.yaml",
        "benchmark": "SPY",
        "bt_mode": "ita",  # CFD engine mode (leverage 20:1)
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

    # Batch-prefetch all tickers + benchmark + VIX in 2 HTTP calls (daily + weekly)
    # with disk cache so repeated runs skip downloads entirely
    all_symbols = list(dict.fromkeys(list(tickers) + [benchmark, "^VIX"]))
    prefetch_historical(all_symbols, ws, end)

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
    """Shuffle trade PnL order and compute path-dependent risk metrics.

    Note: Final equity is always identical across simulations (addition is
    commutative). The value of shuffling is in PATH-DEPENDENT metrics:
    max drawdown, min equity reached, and probability of ruin (equity
    dropping below threshold at any point during the path).
    """
    pnl_array = np.array(trades_pnl)
    n_trades = len(pnl_array)

    max_drawdowns = np.empty(n_simulations)
    min_equities = np.empty(n_simulations)
    ruin_hits = np.empty(n_simulations, dtype=bool)

    ruin_level = initial_capital * ruin_threshold
    final_equity = initial_capital + float(np.sum(pnl_array))
    total_return = (final_equity - initial_capital) / initial_capital * 100

    for sim in range(n_simulations):
        shuffled = np.random.permutation(pnl_array)
        equity = initial_capital + np.cumsum(shuffled)
        equity = np.insert(equity, 0, initial_capital)

        peak = np.maximum.accumulate(equity)
        drawdown_pct = np.where(peak > 0, (equity - peak) / peak * 100, 0.0)

        max_drawdowns[sim] = drawdown_pct.min()
        min_equities[sim] = equity.min()
        ruin_hits[sim] = equity.min() < ruin_level

    percentiles = [5, 25, 50, 75, 95]

    return {
        "n_simulations": n_simulations,
        "n_trades": n_trades,
        "initial_capital": initial_capital,
        # Deterministic (order-independent)
        "final_equity": final_equity,
        "total_return": total_return,
        # Max drawdown distribution (path-dependent)
        "dd_mean": float(np.mean(max_drawdowns)),
        "dd_std": float(np.std(max_drawdowns)),
        "dd_percentiles": {
            p: float(np.percentile(max_drawdowns, p)) for p in percentiles
        },
        # Min equity distribution (path-dependent)
        "min_eq_mean": float(np.mean(min_equities)),
        "min_eq_std": float(np.std(min_equities)),
        "min_eq_percentiles": {
            p: float(np.percentile(min_equities, p)) for p in percentiles
        },
        # Risk metrics
        "prob_ruin": float(np.mean(ruin_hits)),
        "worst_min_equity": float(np.min(min_equities)),
        "best_min_equity": float(np.max(min_equities)),
        "worst_dd": float(np.min(max_drawdowns)),
        # Raw arrays for plotting
        "_max_drawdowns": max_drawdowns,
        "_min_equities": min_equities,
    }


def print_results(results: dict, mode: str) -> None:
    """Print Monte Carlo results as Rich tables."""
    currency = "$" if mode in ("us", "indexcfd") else "\u20ac"
    cap = results["initial_capital"]

    console.print(f"\n[bold]Monte Carlo Results — {mode.upper()} CFD[/bold]")
    console.print(
        f"Simulations: {results['n_simulations']:,} | "
        f"Trades shuffled: {results['n_trades']:,} | "
        f"Initial capital: {currency}{cap:,.0f}"
    )
    ret = results["total_return"]
    ret_style = "green" if ret >= 0 else "red"
    console.print(
        f"Final equity: {currency}{results['final_equity']:,.0f} "
        f"([{ret_style}]{ret:+.1f}%[/{ret_style}]) — "
        f"[dim]deterministic, same for all simulations[/dim]"
    )
    console.print()

    # --- Path risk distribution ---
    risk_table = Table(
        title="Path Risk Distribution (order-dependent)", show_lines=True,
    )
    risk_table.add_column("Percentile", style="cyan", justify="center")
    risk_table.add_column("Max Drawdown", justify="right")
    risk_table.add_column("Min Equity Reached", justify="right")

    for p in [5, 25, 50, 75, 95]:
        dd = results["dd_percentiles"][p]
        meq = results["min_eq_percentiles"][p]
        risk_table.add_row(
            f"P{p}",
            f"[red]{dd:.1f}%[/red]",
            f"{currency}{meq:,.0f}",
        )

    console.print(risk_table)

    # --- Summary stats ---
    stats = Table(title="Summary Statistics", show_lines=True)
    stats.add_column("Metric", style="cyan")
    stats.add_column("Value", justify="right", style="bold")

    stats.add_row("Mean max drawdown", f"{results['dd_mean']:.1f}%")
    stats.add_row("Std dev max drawdown", f"{results['dd_std']:.1f}%")
    stats.add_row("Worst drawdown (any sim)", f"[red]{results['worst_dd']:.1f}%[/red]")
    stats.add_row("", "")
    stats.add_row("Mean min equity", f"{currency}{results['min_eq_mean']:,.0f}")
    stats.add_row("Worst min equity (any sim)", f"{currency}{results['worst_min_equity']:,.0f}")
    stats.add_row("Best min equity (any sim)", f"{currency}{results['best_min_equity']:,.0f}")
    stats.add_row("", "")
    stats.add_row(
        "Prob ruin (equity < 50% at any point)",
        f"[{'red' if results['prob_ruin'] > 0.05 else 'green'}]"
        f"{results['prob_ruin']*100:.2f}%[/]",
    )

    console.print(stats)


def save_plot(results: dict, output_dir: str, mode: str) -> None:
    """Save max drawdown and min equity histograms."""
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)
    currency = "$" if mode in ("us", "indexcfd") else "\u20ac"

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Max drawdown distribution
    ax = axes[0]
    ax.hist(results["_max_drawdowns"], bins=80, color="indianred", edgecolor="none", alpha=0.8)
    ax.axvline(results["dd_percentiles"][50], color="orange", linestyle="--",
               linewidth=1.5, label=f"Median: {results['dd_percentiles'][50]:.1f}%")
    ax.axvline(results["dd_percentiles"][5], color="red", linestyle="--",
               linewidth=1.5, label=f"P5 (worst): {results['dd_percentiles'][5]:.1f}%")
    ax.set_xlabel("Max Drawdown (%)")
    ax.set_ylabel("Frequency")
    ax.set_title("Max Drawdown Distribution")
    ax.legend(fontsize=8)

    # Min equity distribution
    ax = axes[1]
    ax.hist(results["_min_equities"], bins=80, color="steelblue", edgecolor="none", alpha=0.8)
    ax.axvline(results["min_eq_percentiles"][50], color="orange", linestyle="--",
               linewidth=1.5, label=f"Median: {currency}{results['min_eq_percentiles'][50]:,.0f}")
    ax.axvline(results["min_eq_percentiles"][5], color="red", linestyle="--",
               linewidth=1.5, label=f"P5 (worst): {currency}{results['min_eq_percentiles'][5]:,.0f}")
    ax.axvline(results["initial_capital"], color="black", linestyle="-",
               linewidth=1, label=f"Initial: {currency}{results['initial_capital']:,.0f}")
    ruin_level = results["initial_capital"] * 0.5
    ax.axvline(ruin_level, color="darkred", linestyle=":", linewidth=1.5,
               label=f"Ruin: {currency}{ruin_level:,.0f}")
    ax.set_xlabel(f"Min Equity Reached ({currency})")
    ax.set_ylabel("Frequency")
    ax.set_title("Min Equity During Path")
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
        writer.writerow(["final_equity", f"{results['final_equity']:.2f}"])
        writer.writerow(["total_return", f"{results['total_return']:.4f}"])
        writer.writerow(["dd_mean", f"{results['dd_mean']:.4f}"])
        writer.writerow(["dd_worst", f"{results['worst_dd']:.4f}"])
        writer.writerow(["min_eq_mean", f"{results['min_eq_mean']:.2f}"])
        writer.writerow(["worst_min_equity", f"{results['worst_min_equity']:.2f}"])
        writer.writerow(["prob_ruin", f"{results['prob_ruin']:.6f}"])
        for p in [5, 25, 50, 75, 95]:
            writer.writerow([f"dd_p{p}", f"{results['dd_percentiles'][p]:.4f}"])
            writer.writerow([f"min_eq_p{p}", f"{results['min_eq_percentiles'][p]:.2f}"])

    console.print(f"[dim]CSV saved to {path}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monte Carlo simulation for trade-order sensitivity analysis"
    )
    parser.add_argument(
        "--mode", choices=list(MODE_CONFIG.keys()), required=True,
        help="Strategy mode (ita, us, etf, or indexcfd)",
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
