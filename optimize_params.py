#!/usr/bin/env python3
"""Parameter optimization for ITA CFD strategy on FTSE MIB.

Grid-searches key parameters on 2020-2024 data and reports the best combinations.
"""

import copy
import csv
import itertools
import logging
import os

import yaml
from rich.console import Console
from rich.table import Table

from backtester.data import fetch_historical, fetch_weekly_historical, warmup_start, clear_cache
from backtester.engine import run_backtest
from backtester.metrics import compute_metrics
from backtester.signals import compute_all_signals

FTSEMIB_TICKERS = [
    "A2A.MI", "AMP.MI", "AZM.MI", "BC.MI", "BGN.MI", "BMED.MI", "BPE.MI",
    "BZU.MI", "CPR.MI", "DIA.MI", "ENEL.MI", "ENI.MI", "ERG.MI", "FBK.MI",
    "G.MI", "HER.MI", "IG.MI", "INW.MI", "IP.MI", "ISP.MI", "IVG.MI",
    "ITW.MI", "LDO.MI", "MB.MI", "MONC.MI", "NEXI.MI", "PIRC.MI", "PRY.MI",
    "PST.MI", "RACE.MI", "REC.MI", "SRG.MI", "STLAM.MI", "STMMI.MI",
    "TEN.MI", "TIT.MI", "TRN.MI", "UCG.MI", "UNI.MI",
]

START = "2020-01-01"
END = "2024-12-31"
CONFIG_PATH = "config_ita.yaml"
OUTPUT_DIR = "output/optimization"

# --- Parameter grid ---
PARAM_GRID = {
    "vix_threshold": [20, 25, 30, 35, 999],       # 999 = disabled
    "mfi_threshold": [40, 45, 50, 55],
    "mfi_length":    [10, 14, 20],
    "rsi_threshold": [45, 50, 55],
    "adx_threshold": [15, 20, 25],
    "go_threshold":  [4, 5],
}


def run_one_config(
    cfg: dict,
    ticker_data: dict,
    bench_daily, vix_daily,
) -> dict:
    """Run backtest across all tickers with a given config. Return aggregate metrics."""
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0
    ticker_returns = []
    ticker_dds = []

    for ticker, (df_daily, df_weekly) in ticker_data.items():
        try:
            signals = compute_all_signals(
                df_daily, df_weekly, bench_daily, vix_daily, cfg, mode="ita"
            )
            signals_bt = signals.loc[START:]
            df_bt = df_daily.loc[START:]

            if df_bt.empty:
                continue

            result = run_backtest(signals_bt, df_bt, cfg, ticker=ticker, mode="ita")
            metrics = compute_metrics(result, cfg)

            total_trades += metrics["total_trades"]
            total_wins += metrics["winning_trades"]
            total_pnl += metrics["final_equity"] - cfg["position_sizing"]["capital"]
            ticker_returns.append(metrics["total_return_pct"])
            ticker_dds.append(metrics["max_drawdown_pct"])
        except Exception:
            continue

    if not ticker_returns:
        return {"avg_return": -999, "median_return": -999}

    ticker_returns.sort()
    profitable = sum(1 for r in ticker_returns if r > 0)

    return {
        "total_trades": total_trades,
        "total_wins": total_wins,
        "win_rate": round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_return": round(sum(ticker_returns) / len(ticker_returns), 2),
        "median_return": round(ticker_returns[len(ticker_returns) // 2], 2),
        "profitable_pct": round(profitable / len(ticker_returns) * 100, 1),
        "avg_dd": round(sum(ticker_dds) / len(ticker_dds), 2),
        "worst_dd": round(min(ticker_dds), 2),
        "tickers_tested": len(ticker_returns),
    }


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console = Console()

    with open(CONFIG_PATH) as f:
        base_cfg = yaml.safe_load(f)

    ws = warmup_start(START, extra_bars=100)

    console.print("\n[bold]Parameter Optimization — FTSE MIB[/bold]")
    console.print(f"Period: {START} to {END}")
    console.print(f"Tickers: {len(FTSEMIB_TICKERS)}")

    # Count total combos
    keys = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    combos = list(itertools.product(*values))
    console.print(f"Parameter combinations: {len(combos)}")
    console.print(f"Grid: {', '.join(f'{k}={v}' for k, v in PARAM_GRID.items())}\n")

    # --- Pre-fetch all data once ---
    console.print("[bold]Fetching data...[/bold]")
    bench_daily = fetch_historical("ETFMIB.MI", ws, END)
    vix_daily = fetch_historical("^VIX", ws, END)

    ticker_data = {}
    for i, ticker in enumerate(FTSEMIB_TICKERS, 1):
        console.print(f"  [{i}/{len(FTSEMIB_TICKERS)}] {ticker}", end="\r")
        df_daily = fetch_historical(ticker, ws, END)
        df_weekly = fetch_weekly_historical(ticker, ws, END)
        if not df_daily.empty and len(df_daily) >= 60:
            ticker_data[ticker] = (df_daily, df_weekly)
    console.print(f"  Loaded {len(ticker_data)} tickers with valid data.    \n")

    # --- Grid search ---
    all_results = []

    for idx, combo in enumerate(combos, 1):
        params = dict(zip(keys, combo))

        # Build config variant
        cfg = copy.deepcopy(base_cfg)
        cfg["strategy"]["vix_threshold"] = params["vix_threshold"]
        cfg["strategy"]["mfi_threshold"] = params["mfi_threshold"]
        cfg["strategy"]["mfi_length"] = params["mfi_length"]
        cfg["strategy"]["rsi_threshold"] = params["rsi_threshold"]
        cfg["strategy"]["adx_threshold"] = params["adx_threshold"]
        cfg["alerts"]["go_threshold"] = params["go_threshold"]

        agg = run_one_config(cfg, ticker_data, bench_daily, vix_daily)
        agg.update(params)
        all_results.append(agg)

        # Progress
        if idx % 10 == 0 or idx == len(combos):
            console.print(
                f"  [{idx}/{len(combos)}] "
                f"VIX={params['vix_threshold']:>3} MFI={params['mfi_threshold']}/{params['mfi_length']} "
                f"RSI={params['rsi_threshold']} ADX={params['adx_threshold']} GO={params['go_threshold']} "
                f"=> avg {agg['avg_return']:+.1f}% | win {agg.get('win_rate',0):.0f}% | "
                f"trades {agg.get('total_trades',0)}"
            )

    # --- Sort by avg return ---
    all_results.sort(key=lambda r: r["avg_return"], reverse=True)

    # --- Top 20 report ---
    table = Table(title=f"\nTop 20 Parameter Combinations ({START} to {END})", show_lines=False)
    table.add_column("#", style="dim", justify="right")
    table.add_column("VIX", justify="right")
    table.add_column("MFI thr", justify="right")
    table.add_column("MFI len", justify="right")
    table.add_column("RSI", justify="right")
    table.add_column("ADX", justify="right")
    table.add_column("GO thr", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Win%", justify="right")
    table.add_column("Avg Ret%", justify="right")
    table.add_column("Med Ret%", justify="right")
    table.add_column("Prof%", justify="right")
    table.add_column("Avg DD%", justify="right")
    table.add_column("PnL EUR", justify="right")

    for i, r in enumerate(all_results[:20], 1):
        vix_str = "OFF" if r["vix_threshold"] >= 999 else str(r["vix_threshold"])
        table.add_row(
            str(i),
            vix_str,
            str(r["mfi_threshold"]),
            str(r["mfi_length"]),
            str(r["rsi_threshold"]),
            str(r["adx_threshold"]),
            str(r["go_threshold"]),
            str(r.get("total_trades", 0)),
            f"{r.get('win_rate', 0)}%",
            f"[green]{r['avg_return']:+.2f}%[/green]" if r["avg_return"] >= 0 else f"[red]{r['avg_return']:+.2f}%[/red]",
            f"{r['median_return']:+.2f}%",
            f"{r.get('profitable_pct', 0)}%",
            f"{r.get('avg_dd', 0):.1f}%",
            f"\u20ac{r.get('total_pnl', 0):,.0f}",
        )

    console.print(table)

    # --- Current params baseline ---
    console.print("\n[bold]Current parameters (baseline):[/bold]")
    baseline = next(
        (r for r in all_results
         if r["vix_threshold"] == 25 and r["mfi_threshold"] == 50
         and r["mfi_length"] == 14 and r["rsi_threshold"] == 50
         and r["adx_threshold"] == 20 and r["go_threshold"] == 5),
        None,
    )
    if baseline:
        console.print(
            f"  Avg return: {baseline['avg_return']:+.2f}% | "
            f"Win rate: {baseline.get('win_rate', 0)}% | "
            f"Trades: {baseline.get('total_trades', 0)} | "
            f"Profitable: {baseline.get('profitable_pct', 0)}% | "
            f"Avg DD: {baseline.get('avg_dd', 0):.1f}%"
        )
        # Find rank
        rank = next(i for i, r in enumerate(all_results, 1) if r is baseline)
        console.print(f"  Rank: #{rank} out of {len(all_results)}")

    # --- Best params ---
    best = all_results[0]
    console.print(f"\n[bold green]Best parameters:[/bold green]")
    console.print(f"  vix_threshold: {best['vix_threshold']} {'(disabled)' if best['vix_threshold'] >= 999 else ''}")
    console.print(f"  mfi_threshold: {best['mfi_threshold']}")
    console.print(f"  mfi_length:    {best['mfi_length']}")
    console.print(f"  rsi_threshold: {best['rsi_threshold']}")
    console.print(f"  adx_threshold: {best['adx_threshold']}")
    console.print(f"  go_threshold:  {best['go_threshold']}")
    console.print(
        f"  => Avg return: {best['avg_return']:+.2f}% | "
        f"Win rate: {best.get('win_rate', 0)}% | "
        f"Trades: {best.get('total_trades', 0)} | "
        f"Profitable: {best.get('profitable_pct', 0)}%"
    )

    # --- Save full CSV ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, "param_optimization.csv")
    fieldnames = [
        "vix_threshold", "mfi_threshold", "mfi_length", "rsi_threshold",
        "adx_threshold", "go_threshold", "total_trades", "total_wins",
        "win_rate", "total_pnl", "avg_return", "median_return",
        "profitable_pct", "avg_dd", "worst_dd", "tickers_tested",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_results)
    console.print(f"\n[bold]Full results saved to:[/bold] {csv_path}")


if __name__ == "__main__":
    main()
