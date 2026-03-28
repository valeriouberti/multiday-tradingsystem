#!/usr/bin/env python3
"""Full FTSE MIB backtest: run ITA strategy across all index constituents.

Generates a comprehensive CSV + rich console report.
"""

import csv
import logging
import os

import yaml
from rich.console import Console
from rich.table import Table

from backtester.data import fetch_historical, fetch_weekly_historical, warmup_start
from backtester.engine import run_backtest
from backtester.metrics import compute_metrics, save_trades_csv
from backtester.signals import compute_all_signals

START = "2020-01-01"
END = "2024-12-31"
CONFIG_PATH = "config_ita.yaml"
OUTPUT_DIR = "output/backtest_ftsemib"


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console = Console()

    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    benchmark = cfg.get("benchmark", "ETFMIB.MI")
    ws = warmup_start(START, extra_bars=100)

    console.print("\n[bold]FTSE MIB Full Backtest[/bold]")
    console.print(f"Period: {START} to {END} | Benchmark: {benchmark}")
    console.print(
        f"Capital: EUR {cfg['position_sizing']['capital']} | Leverage: {cfg['position_sizing'].get('leverage', 1)}x"
    )
    tickers = cfg["tickers"]
    console.print(f"Tickers: {len(tickers)}\n")

    # Fetch shared data once
    bench_daily = fetch_historical(benchmark, ws, END)
    vix_daily = fetch_historical("^VIX", ws, END)

    results = []

    for i, ticker in enumerate(tickers, 1):
        console.print(f"  [{i}/{len(tickers)}] {ticker}...", end=" ")

        try:
            df_daily = fetch_historical(ticker, ws, END)
            df_weekly = fetch_weekly_historical(ticker, ws, END)

            if df_daily.empty or len(df_daily) < 60:
                console.print("[yellow]skipped (no data)[/yellow]")
                continue

            signals = compute_all_signals(
                df_daily, df_weekly, bench_daily, vix_daily, cfg, mode="ita"
            )
            signals_bt = signals.loc[START:]
            df_bt = df_daily.loc[START:]

            if df_bt.empty:
                console.print("[yellow]skipped (no data in window)[/yellow]")
                continue

            result = run_backtest(signals_bt, df_bt, cfg, ticker=ticker, mode="ita")
            metrics = compute_metrics(result, cfg)
            metrics["ticker"] = ticker
            metrics["go_signals"] = int(signals_bt["go"].sum())
            results.append(metrics)

            # Save individual trade logs
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            save_trades_csv(result.trades, OUTPUT_DIR, ticker)

            status = (
                "[green]OK[/green]"
                if metrics["total_return_pct"] >= 0
                else "[red]OK[/red]"
            )
            console.print(
                f"{status} | {metrics['total_trades']} trades | {metrics['total_return_pct']:+.1f}%"
            )

        except Exception as e:
            console.print(f"[red]error: {e}[/red]")
            continue

    if not results:
        console.print("[red]No results to report.[/red]")
        return

    # Sort by total return
    results.sort(key=lambda r: r["total_return_pct"], reverse=True)

    # --- Console report ---
    table = Table(
        title=f"\nFTSE MIB Backtest Report ({START} to {END})", show_lines=False
    )
    table.add_column("#", style="dim", justify="right")
    table.add_column("Ticker", style="cyan bold")
    table.add_column("Trades", justify="right")
    table.add_column("Wins", justify="right")
    table.add_column("Win%", justify="right")
    table.add_column("Avg R:R", justify="right")
    table.add_column("PF", justify="right")
    table.add_column("Return%", justify="right")
    table.add_column("MaxDD%", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("Expect.", justify="right")
    table.add_column("Final EUR", justify="right")

    for i, r in enumerate(results, 1):
        ret_style = "green" if r["total_return_pct"] >= 0 else "red"
        dd_style = "red" if r["max_drawdown_pct"] < -10 else "dim"
        pf = r["profit_factor"] if r["profit_factor"] < 999 else 999.0
        table.add_row(
            str(i),
            r["ticker"],
            str(r["total_trades"]),
            str(r["winning_trades"]),
            f"{r['win_rate']}%",
            f"{r['avg_rr']:.2f}",
            f"{pf:.2f}",
            f"[{ret_style}]{r['total_return_pct']:+.2f}%[/{ret_style}]",
            f"[{dd_style}]{r['max_drawdown_pct']:.2f}%[/{dd_style}]",
            f"{r['sharpe_ratio']:.2f}",
            f"\u20ac{r['expectancy']:.0f}",
            f"\u20ac{r['final_equity']:.0f}",
        )

    console.print(table)

    # --- Aggregate stats ---
    profitable = [r for r in results if r["total_return_pct"] > 0]
    losing = [r for r in results if r["total_return_pct"] <= 0]
    total_trades = sum(r["total_trades"] for r in results)
    total_wins = sum(r["winning_trades"] for r in results)
    avg_return = sum(r["total_return_pct"] for r in results) / len(results)
    avg_dd = sum(r["max_drawdown_pct"] for r in results) / len(results)
    avg_sharpe = sum(r["sharpe_ratio"] for r in results) / len(results)
    median_return = sorted(r["total_return_pct"] for r in results)[len(results) // 2]

    agg = Table(title="Aggregate Statistics", show_lines=True)
    agg.add_column("Metric", style="cyan")
    agg.add_column("Value", style="bold", justify="right")

    agg.add_row("Tickers tested", str(len(results)))
    agg.add_row(
        "Profitable tickers",
        f"{len(profitable)} ({len(profitable) / len(results) * 100:.0f}%)",
    )
    agg.add_row(
        "Losing tickers", f"{len(losing)} ({len(losing) / len(results) * 100:.0f}%)"
    )
    agg.add_row("Total trades", str(total_trades))
    agg.add_row(
        "Total wins",
        f"{total_wins} ({total_wins / total_trades * 100:.1f}%)"
        if total_trades > 0
        else "0",
    )
    agg.add_row("Avg return per ticker", f"{avg_return:+.2f}%")
    agg.add_row("Median return", f"{median_return:+.2f}%")
    agg.add_row(
        "Best ticker",
        f"{results[0]['ticker']} ({results[0]['total_return_pct']:+.2f}%)",
    )
    agg.add_row(
        "Worst ticker",
        f"{results[-1]['ticker']} ({results[-1]['total_return_pct']:+.2f}%)",
    )
    agg.add_row("Avg max drawdown", f"{avg_dd:.2f}%")
    agg.add_row("Avg Sharpe ratio", f"{avg_sharpe:.2f}")

    console.print(agg)

    # --- Save CSV report ---
    csv_path = os.path.join(OUTPUT_DIR, "ftsemib_report.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker",
                "total_trades",
                "winning_trades",
                "losing_trades",
                "win_rate",
                "avg_win",
                "avg_loss",
                "avg_rr",
                "profit_factor",
                "expectancy",
                "total_return_pct",
                "max_drawdown_pct",
                "sharpe_ratio",
                "sortino_ratio",
                "calmar_ratio",
                "avg_holding_days",
                "max_holding_days",
                "final_equity",
                "go_signals",
            ],
        )
        writer.writeheader()
        writer.writerows(results)
    console.print(f"\n[bold]Report saved to:[/bold] {csv_path}")


if __name__ == "__main__":
    main()
