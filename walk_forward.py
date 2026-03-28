#!/usr/bin/env python3
"""Walk-Forward Analysis for ITA CFD strategy on FTSE MIB.

Trains on rolling windows, tests on unseen out-of-sample periods.
Reports only OOS performance to detect overfitting.
"""

import copy
import csv
import itertools
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import yaml
from rich.console import Console
from rich.table import Table
from rich.text import Text

from backtester.data import fetch_historical, fetch_weekly_historical, warmup_start
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

CONFIG_PATH = "config_ita.yaml"
OUTPUT_DIR = "output/walk_forward"

# --- Parameter grid (same as optimize_params.py) ---
PARAM_GRID = {
    "vix_threshold": [20, 25, 30, 35, 999],
    "mfi_threshold": [40, 45, 50, 55],
    "mfi_length":    [10, 14, 20],
    "rsi_threshold": [45, 50, 55],
    "adx_threshold": [15, 20, 25],
    "go_threshold":  [4, 5],
}

# --- Walk-Forward Windows ---
# Train 24 months, Test 6 months, rolling forward 6 months
# Full data range: 2019-01-01 to 2025-06-30 (fetched with warmup)
WINDOWS = [
    {"train_start": "2019-01-01", "train_end": "2020-12-31",
     "test_start":  "2021-01-01", "test_end":  "2021-06-30"},
    {"train_start": "2019-07-01", "train_end": "2021-06-30",
     "test_start":  "2021-07-01", "test_end":  "2021-12-31"},
    {"train_start": "2020-01-01", "train_end": "2021-12-31",
     "test_start":  "2022-01-01", "test_end":  "2022-06-30"},
    {"train_start": "2020-07-01", "train_end": "2022-06-30",
     "test_start":  "2022-07-01", "test_end":  "2022-12-31"},
    {"train_start": "2021-01-01", "train_end": "2022-12-31",
     "test_start":  "2023-01-01", "test_end":  "2023-06-30"},
    {"train_start": "2021-07-01", "train_end": "2023-06-30",
     "test_start":  "2023-07-01", "test_end":  "2023-12-31"},
    {"train_start": "2022-01-01", "train_end": "2023-12-31",
     "test_start":  "2024-01-01", "test_end":  "2024-06-30"},
    {"train_start": "2022-07-01", "train_end": "2024-06-30",
     "test_start":  "2024-07-01", "test_end":  "2024-12-31"},
]


@dataclass
class WindowResult:
    """Result of one walk-forward window."""
    window_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    # Best in-sample params
    best_params: dict = field(default_factory=dict)
    # In-sample metrics (training period, best params)
    is_avg_return: float = 0.0
    is_win_rate: float = 0.0
    is_total_trades: int = 0
    is_profitable_pct: float = 0.0
    # Out-of-sample metrics (test period, best params from training)
    oos_avg_return: float = 0.0
    oos_win_rate: float = 0.0
    oos_total_trades: int = 0
    oos_profitable_pct: float = 0.0
    oos_total_pnl: float = 0.0
    oos_avg_dd: float = 0.0
    oos_tickers_tested: int = 0
    # Efficiency ratio: OOS / IS (>0.5 = robust, <0.3 = likely overfit)
    efficiency_ratio: float = 0.0


def _apply_params(base_cfg: dict, params: dict) -> dict:
    """Apply parameter combo to config."""
    cfg = copy.deepcopy(base_cfg)
    cfg["strategy"]["vix_threshold"] = params["vix_threshold"]
    cfg["strategy"]["mfi_threshold"] = params["mfi_threshold"]
    cfg["strategy"]["mfi_length"] = params["mfi_length"]
    cfg["strategy"]["rsi_threshold"] = params["rsi_threshold"]
    cfg["strategy"]["adx_threshold"] = params["adx_threshold"]
    cfg["alerts"]["go_threshold"] = params["go_threshold"]
    return cfg


def _run_universe(
    cfg: dict,
    ticker_data: dict,
    bench_daily,
    vix_daily,
    start: str,
    end: str,
) -> dict:
    """Run backtest across all tickers for a given period. Return aggregate metrics."""
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0
    ticker_returns = []
    ticker_dds = []

    for ticker, (df_daily_full, df_weekly_full) in ticker_data.items():
        try:
            signals = compute_all_signals(
                df_daily_full, df_weekly_full, bench_daily, vix_daily, cfg, mode="ita"
            )
            signals_bt = signals.loc[start:end]
            df_bt = df_daily_full.loc[start:end]

            if df_bt.empty or len(df_bt) < 20:
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
        return {"avg_return": -999, "median_return": -999, "total_trades": 0}

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
        "avg_dd": round(sum(ticker_dds) / len(ticker_dds), 2) if ticker_dds else 0,
        "worst_dd": round(min(ticker_dds), 2) if ticker_dds else 0,
        "tickers_tested": len(ticker_returns),
    }


def _optimize_on_window(
    base_cfg: dict,
    ticker_data: dict,
    bench_daily,
    vix_daily,
    train_start: str,
    train_end: str,
    console: Console,
) -> tuple[dict, dict]:
    """Grid search on training window. Returns (best_params, best_metrics)."""
    keys = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    combos = list(itertools.product(*values))

    best_params = None
    best_metrics = None
    best_avg_return = -9999

    for idx, combo in enumerate(combos, 1):
        params = dict(zip(keys, combo))
        cfg = _apply_params(base_cfg, params)
        agg = _run_universe(cfg, ticker_data, bench_daily, vix_daily, train_start, train_end)

        if agg["avg_return"] > best_avg_return:
            best_avg_return = agg["avg_return"]
            best_params = params
            best_metrics = agg

        if idx % 100 == 0:
            console.print(f"    [{idx}/{len(combos)}] best so far: {best_avg_return:+.2f}%", end="\r")

    console.print(f"    [{len(combos)}/{len(combos)}] done — best IS avg return: {best_avg_return:+.2f}%    ")
    return best_params, best_metrics


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    console = Console()

    with open(CONFIG_PATH) as f:
        base_cfg = yaml.safe_load(f)

    # We need data from 2018-07 through 2024-12 (warmup for earliest window)
    data_start = "2018-01-01"
    data_end = "2024-12-31"
    ws = warmup_start(data_start, extra_bars=100)

    console.print("\n[bold]Walk-Forward Analysis — FTSE MIB[/bold]")
    console.print(f"Windows: {len(WINDOWS)} (24m train / 6m test, rolling 6m)")
    console.print(f"Tickers: {len(FTSEMIB_TICKERS)}")

    keys = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    combos_count = 1
    for v in values:
        combos_count *= len(v)
    console.print(f"Parameter combinations per window: {combos_count}")
    console.print(f"Total optimizations: {combos_count * len(WINDOWS):,}\n")

    # --- Pre-fetch all data once (full range) ---
    console.print("[bold]Fetching data (full range)...[/bold]")
    bench_daily = fetch_historical("ETFMIB.MI", ws, data_end)
    vix_daily = fetch_historical("^VIX", ws, data_end)

    ticker_data = {}
    for i, ticker in enumerate(FTSEMIB_TICKERS, 1):
        console.print(f"  [{i}/{len(FTSEMIB_TICKERS)}] {ticker}", end="\r")
        df_daily = fetch_historical(ticker, ws, data_end)
        df_weekly = fetch_weekly_historical(ticker, ws, data_end)
        if not df_daily.empty and len(df_daily) >= 60:
            ticker_data[ticker] = (df_daily, df_weekly)
    console.print(f"  Loaded {len(ticker_data)} tickers with valid data.    \n")

    # --- Walk-Forward Loop ---
    window_results: list[WindowResult] = []

    for w_idx, window in enumerate(WINDOWS):
        train_start = window["train_start"]
        train_end = window["train_end"]
        test_start = window["test_start"]
        test_end = window["test_end"]

        console.print(f"[bold cyan]Window {w_idx + 1}/{len(WINDOWS)}[/bold cyan]")
        console.print(f"  Train: {train_start} → {train_end}")
        console.print(f"  Test:  {test_start} → {test_end}")

        # Step 1: Optimize on training window
        console.print("  [dim]Optimizing on training data...[/dim]")
        best_params, is_metrics = _optimize_on_window(
            base_cfg, ticker_data, bench_daily, vix_daily,
            train_start, train_end, console,
        )

        console.print(f"  Best params: {best_params}")
        console.print(
            f"  IS: avg {is_metrics['avg_return']:+.2f}% | "
            f"win {is_metrics.get('win_rate', 0):.0f}% | "
            f"trades {is_metrics.get('total_trades', 0)}"
        )

        # Step 2: Test best params on OOS window
        console.print("  [dim]Testing on out-of-sample data...[/dim]")
        cfg_best = _apply_params(base_cfg, best_params)
        oos_metrics = _run_universe(
            cfg_best, ticker_data, bench_daily, vix_daily, test_start, test_end,
        )

        # Efficiency ratio
        is_ret = is_metrics["avg_return"]
        oos_ret = oos_metrics["avg_return"]
        if is_ret > 0:
            eff = oos_ret / is_ret
        elif is_ret == 0:
            eff = 0.0
        else:
            eff = -1.0  # both negative = unusual

        console.print(
            f"  OOS: avg {oos_ret:+.2f}% | "
            f"win {oos_metrics.get('win_rate', 0):.0f}% | "
            f"trades {oos_metrics.get('total_trades', 0)} | "
            f"efficiency {eff:.2f}"
        )

        eff_style = "green" if eff >= 0.5 else "yellow" if eff >= 0.0 else "red"
        console.print(f"  [{eff_style}]Efficiency ratio: {eff:.2f}[/{eff_style}]\n")

        wr = WindowResult(
            window_idx=w_idx + 1,
            train_start=train_start, train_end=train_end,
            test_start=test_start, test_end=test_end,
            best_params=best_params,
            is_avg_return=is_ret,
            is_win_rate=is_metrics.get("win_rate", 0),
            is_total_trades=is_metrics.get("total_trades", 0),
            is_profitable_pct=is_metrics.get("profitable_pct", 0),
            oos_avg_return=oos_ret,
            oos_win_rate=oos_metrics.get("win_rate", 0),
            oos_total_trades=oos_metrics.get("total_trades", 0),
            oos_profitable_pct=oos_metrics.get("profitable_pct", 0),
            oos_total_pnl=oos_metrics.get("total_pnl", 0),
            oos_avg_dd=oos_metrics.get("avg_dd", 0),
            oos_tickers_tested=oos_metrics.get("tickers_tested", 0),
            efficiency_ratio=round(eff, 3),
        )
        window_results.append(wr)

    # ==========================================================================
    # SUMMARY REPORT
    # ==========================================================================
    console.print("\n" + "=" * 80)
    console.print("[bold]WALK-FORWARD ANALYSIS — SUMMARY[/bold]")
    console.print("=" * 80)

    # --- Window-by-window table ---
    table = Table(title="Walk-Forward Results by Window", show_lines=True)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Train Period", no_wrap=True)
    table.add_column("Test Period", no_wrap=True)
    table.add_column("IS Ret%", justify="right")
    table.add_column("OOS Ret%", justify="right")
    table.add_column("OOS Win%", justify="right")
    table.add_column("OOS Trades", justify="right")
    table.add_column("OOS PnL", justify="right")
    table.add_column("OOS DD%", justify="right")
    table.add_column("Efficiency", justify="right")
    table.add_column("Best Params", no_wrap=False)

    for wr in window_results:
        is_style = "green" if wr.is_avg_return >= 0 else "red"
        oos_style = "green" if wr.oos_avg_return >= 0 else "red"
        eff_style = "green" if wr.efficiency_ratio >= 0.5 else "yellow" if wr.efficiency_ratio >= 0 else "red"

        params_short = (
            f"VIX={'OFF' if wr.best_params.get('vix_threshold', 0) >= 999 else wr.best_params.get('vix_threshold', '?')} "
            f"MFI={wr.best_params.get('mfi_threshold', '?')}/{wr.best_params.get('mfi_length', '?')} "
            f"RSI={wr.best_params.get('rsi_threshold', '?')} "
            f"ADX={wr.best_params.get('adx_threshold', '?')} "
            f"GO={wr.best_params.get('go_threshold', '?')}"
        )

        table.add_row(
            str(wr.window_idx),
            f"{wr.train_start} → {wr.train_end}",
            f"{wr.test_start} → {wr.test_end}",
            f"[{is_style}]{wr.is_avg_return:+.2f}%[/{is_style}]",
            f"[{oos_style}]{wr.oos_avg_return:+.2f}%[/{oos_style}]",
            f"{wr.oos_win_rate:.0f}%",
            str(wr.oos_total_trades),
            f"\u20ac{wr.oos_total_pnl:,.0f}",
            f"{wr.oos_avg_dd:.1f}%",
            f"[{eff_style}]{wr.efficiency_ratio:.2f}[/{eff_style}]",
            params_short,
        )

    console.print(table)

    # --- Aggregate OOS stats ---
    oos_returns = [wr.oos_avg_return for wr in window_results]
    oos_pnls = [wr.oos_total_pnl for wr in window_results]
    efficiencies = [wr.efficiency_ratio for wr in window_results]

    avg_oos = np.mean(oos_returns) if oos_returns else 0
    med_oos = float(np.median(oos_returns)) if oos_returns else 0
    total_oos_pnl = sum(oos_pnls)
    avg_eff = np.mean(efficiencies) if efficiencies else 0
    positive_windows = sum(1 for r in oos_returns if r > 0)

    console.print(f"\n[bold]Aggregate Out-of-Sample Performance:[/bold]")
    console.print(f"  Avg OOS return:       {avg_oos:+.2f}%")
    console.print(f"  Median OOS return:    {med_oos:+.2f}%")
    console.print(f"  Total OOS P&L:        \u20ac{total_oos_pnl:,.0f}")
    console.print(f"  Profitable windows:   {positive_windows}/{len(window_results)}")
    console.print(f"  Avg efficiency ratio: {avg_eff:.2f}")
    console.print()

    # --- Parameter stability analysis ---
    console.print("[bold]Parameter Stability (how often each value was selected):[/bold]")
    for param in PARAM_GRID:
        values_selected = [wr.best_params.get(param) for wr in window_results]
        counts = {}
        for v in values_selected:
            counts[v] = counts.get(v, 0) + 1
        sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
        dist = ", ".join(
            f"{v}={'OFF' if param == 'vix_threshold' and v >= 999 else v} ({c}/{len(window_results)})"
            for v, c in sorted_counts
        )
        console.print(f"  {param}: {dist}")

    console.print()

    # --- Overfitting verdict ---
    console.print("[bold]Overfitting Assessment:[/bold]")
    if avg_eff >= 0.5:
        console.print(
            "  [bold green]LOW RISK[/bold green] — Avg efficiency >= 0.5. "
            "Parameters generalize well to unseen data."
        )
    elif avg_eff >= 0.25:
        console.print(
            "  [bold yellow]MODERATE RISK[/bold yellow] — Avg efficiency 0.25-0.5. "
            "Some parameter decay; consider using less aggressive optimization."
        )
    elif avg_eff >= 0:
        console.print(
            "  [bold red]HIGH RISK[/bold red] — Avg efficiency 0-0.25. "
            "Significant OOS degradation; in-sample results are unreliable."
        )
    else:
        console.print(
            "  [bold red]OVERFIT[/bold red] — Negative efficiency. "
            "OOS performance inverts IS results. Do not trust optimized params."
        )

    # --- Recommendation: most stable params ---
    # Pick params that appear most frequently across windows
    stable_params = {}
    for param in PARAM_GRID:
        values_selected = [wr.best_params.get(param) for wr in window_results]
        counts = {}
        for v in values_selected:
            counts[v] = counts.get(v, 0) + 1
        stable_params[param] = max(counts, key=counts.get)

    console.print(f"\n[bold]Most Stable Parameters (mode across all windows):[/bold]")
    for p, v in stable_params.items():
        display = "OFF" if p == "vix_threshold" and v >= 999 else str(v)
        current = base_cfg["strategy"].get(p, base_cfg["alerts"].get(p, "?"))
        match = " ✓" if str(v) == str(current) else f" (config has {current})"
        console.print(f"  {p}: {display}{match}")

    # --- Save CSV ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, "walk_forward_results.csv")
    fieldnames = [
        "window", "train_start", "train_end", "test_start", "test_end",
        "vix_threshold", "mfi_threshold", "mfi_length", "rsi_threshold",
        "adx_threshold", "go_threshold",
        "is_avg_return", "is_win_rate", "is_total_trades",
        "oos_avg_return", "oos_win_rate", "oos_total_trades",
        "oos_total_pnl", "oos_avg_dd", "oos_tickers_tested",
        "efficiency_ratio",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for wr in window_results:
            writer.writerow({
                "window": wr.window_idx,
                "train_start": wr.train_start,
                "train_end": wr.train_end,
                "test_start": wr.test_start,
                "test_end": wr.test_end,
                **wr.best_params,
                "is_avg_return": wr.is_avg_return,
                "is_win_rate": wr.is_win_rate,
                "is_total_trades": wr.is_total_trades,
                "oos_avg_return": wr.oos_avg_return,
                "oos_win_rate": wr.oos_win_rate,
                "oos_total_trades": wr.oos_total_trades,
                "oos_total_pnl": wr.oos_total_pnl,
                "oos_avg_dd": wr.oos_avg_dd,
                "oos_tickers_tested": wr.oos_tickers_tested,
                "efficiency_ratio": wr.efficiency_ratio,
            })
    console.print(f"\n[bold]Results saved to:[/bold] {csv_path}")

    # --- Also test current config params OOS for comparison ---
    console.print("\n[bold]Baseline comparison: current config_ita.yaml params across all OOS windows:[/bold]")
    baseline_oos_returns = []
    for window in WINDOWS:
        test_start = window["test_start"]
        test_end = window["test_end"]
        baseline_agg = _run_universe(
            base_cfg, ticker_data, bench_daily, vix_daily, test_start, test_end,
        )
        baseline_oos_returns.append(baseline_agg["avg_return"])

    baseline_avg = np.mean(baseline_oos_returns) if baseline_oos_returns else 0
    console.print(f"  Current config OOS avg return: {baseline_avg:+.2f}%")
    console.print(f"  WFA optimized OOS avg return:  {avg_oos:+.2f}%")
    diff = avg_oos - baseline_avg
    if diff > 0:
        console.print(f"  [green]WFA adds +{diff:.2f}% over fixed params[/green]")
    else:
        console.print(f"  [yellow]Fixed params perform {-diff:.2f}% better — optimization may be overfitting[/yellow]")

    console.print()


if __name__ == "__main__":
    main()
