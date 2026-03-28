#!/usr/bin/env python3
"""Optuna-based parameter optimization for ITA and US CFD strategies.

Bayesian optimization (TPE sampler) replaces brute-force grid search.
Converges in ~200-300 trials instead of 1,080+.

Performance: indicators are precomputed once per ticker; each trial only
applies threshold comparisons (~10x faster than recomputing pandas-ta).

Usage:
    python optimize_optuna.py --mode ita                    # ITA simple
    python optimize_optuna.py --mode us                     # US simple
    python optimize_optuna.py --mode ita --wfa              # ITA walk-forward
    python optimize_optuna.py --mode us --wfa               # US walk-forward
    python optimize_optuna.py --mode ita --trials 500       # more trials
"""

import argparse
import csv
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import optuna
import pandas as pd
import pandas_ta as ta
import yaml
from rich.console import Console
from rich.table import Table

from backtester.data import fetch_historical, fetch_weekly_historical, warmup_start
from backtester.engine import run_backtest
from backtester.metrics import compute_metrics

# --- Ticker universes ---

FTSEMIB_TICKERS = [
    "A2A.MI", "AMP.MI", "AZM.MI", "BC.MI", "BGN.MI", "BMED.MI", "BPE.MI",
    "BZU.MI", "CPR.MI", "DIA.MI", "ENEL.MI", "ENI.MI", "ERG.MI", "FBK.MI",
    "G.MI", "HER.MI", "IG.MI", "INW.MI", "IP.MI", "ISP.MI", "IVG.MI",
    "ITW.MI", "LDO.MI", "MB.MI", "MONC.MI", "NEXI.MI", "PIRC.MI", "PRY.MI",
    "PST.MI", "RACE.MI", "REC.MI", "SRG.MI", "STLAM.MI", "STMMI.MI",
    "TEN.MI", "TIT.MI", "TRN.MI", "UCG.MI", "UNI.MI",
]

# Sector-sampled S&P 500 (3 per GICS sector = 33 stocks)
SP500_SAMPLE = [
    # Tech
    "AAPL", "MSFT", "NVDA",
    # Financials
    "JPM", "GS", "BLK",
    # Health Care
    "UNH", "LLY", "JNJ",
    # Consumer Disc.
    "TSLA", "HD", "AMZN",
    # Industrials
    "GE", "CAT", "RTX",
    # Energy
    "XOM", "CVX", "COP",
    # Communication
    "NFLX", "GOOGL", "META",
    # Consumer Staples
    "PG", "KO", "COST",
    # Utilities
    "NEE", "SO", "DUK",
    # Materials
    "LIN", "FCX", "SHW",
    # Real Estate
    "PLD", "AMT", "EQIX",
]

# Walk-Forward windows (24m train / 6m test, rolling 6m)
WFA_WINDOWS = [
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

MODE_CONFIG = {
    "ita": {
        "config_path": "config_ita.yaml",
        "benchmark": "ETFMIB.MI",
        "tickers": FTSEMIB_TICKERS,
        "bt_mode": "ita",
    },
    "us": {
        "config_path": "config_us.yaml",
        "benchmark": "SPY",
        "tickers": SP500_SAMPLE,
        "bt_mode": "ita",  # same CFD engine mode (leverage)
    },
}

# All possible mfi_length values in the search space
MFI_LENGTHS = [10, 14, 20]


# =========================================================================
# Signal precomputation (compute pandas-ta indicators ONCE per ticker)
# =========================================================================

@dataclass
class PrecomputedTicker:
    """Raw indicator values computed once per ticker.

    Threshold-independent values are stored as-is.
    MFI is precomputed for all 3 possible lengths.
    """
    check_ema_d: pd.Series    # bool: EMA fast > EMA slow (daily)
    check_ema_w: pd.Series    # bool: EMA fast > EMA slow (weekly, ffilled)
    check_macd: pd.Series     # bool: MACD > Signal
    rsi_values: pd.Series     # float: raw RSI(14)
    mfi_by_length: dict       # {10: Series, 14: Series, 20: Series}
    check_rs: pd.Series       # bool: RS line rising
    vix_aligned: pd.Series    # float: VIX close, ffilled to ticker index
    adx_aligned: pd.Series    # float: ADX(14) on benchmark, ffilled
    atr: pd.Series            # float: ATR(14)
    close: pd.Series          # float: close prices
    df_daily: pd.DataFrame    # full OHLCV (needed by engine)


def _precompute_ticker(
    df_daily: pd.DataFrame,
    df_weekly: pd.DataFrame,
    bench_daily: pd.DataFrame,
    vix_daily: pd.DataFrame,
    cfg: dict,
) -> PrecomputedTicker:
    """Compute all parameter-independent indicators once per ticker."""
    strat = cfg["strategy"]
    idx = df_daily.index

    # Check 1: Daily EMA cross
    ema_fast = ta.ema(df_daily["Close"], length=strat["ema_fast"])
    ema_slow = ta.ema(df_daily["Close"], length=strat["ema_slow"])
    check_ema_d = (ema_fast > ema_slow).fillna(False)

    # Check 2: Weekly EMA cross (forward-filled to daily)
    w_fast = strat.get("weekly_ema_fast", 20)
    w_slow = strat.get("weekly_ema_slow", 50)
    ema_w_fast = ta.ema(df_weekly["Close"], length=w_fast)
    ema_w_slow = ta.ema(df_weekly["Close"], length=w_slow)
    weekly_signal = (ema_w_fast > ema_w_slow).fillna(False)
    weekly_signal.index = (
        weekly_signal.index.tz_localize(None)
        if weekly_signal.index.tz else weekly_signal.index
    )
    daily_idx = idx.tz_localize(None) if idx.tz else idx
    check_ema_w = pd.Series(
        weekly_signal.reindex(daily_idx, method="ffill").fillna(False).values,
        index=idx,
    )

    # Check 3: MACD > Signal
    macd_result = ta.macd(
        df_daily["Close"],
        fast=strat["macd_fast"], slow=strat["macd_slow"], signal=strat["macd_signal"],
    )
    if macd_result is not None and not macd_result.empty:
        macd_cols = [c for c in macd_result.columns if c.startswith("MACD_")]
        signal_cols = [c for c in macd_result.columns if c.startswith("MACDs_")]
        if macd_cols and signal_cols:
            check_macd = (
                macd_result[macd_cols[0]] > macd_result[signal_cols[0]]
            ).fillna(False)
        else:
            check_macd = pd.Series(False, index=idx)
    else:
        check_macd = pd.Series(False, index=idx)

    # Check 4: RSI raw values (threshold applied per trial)
    rsi_values = ta.rsi(df_daily["Close"], length=strat["rsi_length"])
    if rsi_values is None:
        rsi_values = pd.Series(0.0, index=idx)

    # Check 5: MFI raw values for each possible length
    mfi_by_length = {}
    for length in MFI_LENGTHS:
        mfi = ta.mfi(
            df_daily["High"], df_daily["Low"], df_daily["Close"], df_daily["Volume"],
            length=length,
        )
        mfi_by_length[length] = mfi if mfi is not None else pd.Series(0.0, index=idx)

    # Check 6: RS vs benchmark rising
    roc_days = strat.get("rs_roc_days", 5)
    common_idx = df_daily.index.intersection(bench_daily.index)
    if len(common_idx) > roc_days:
        rs = df_daily.loc[common_idx, "Close"] / bench_daily.loc[common_idx, "Close"]
        rs_rising = rs > rs.shift(roc_days)
        check_rs = rs_rising.reindex(idx).fillna(False)
    else:
        check_rs = pd.Series(False, index=idx)

    # VIX aligned to ticker index
    if not vix_daily.empty:
        vix_aligned = vix_daily["Close"].reindex(idx, method="ffill")
    else:
        vix_aligned = pd.Series(0.0, index=idx)

    # ADX on benchmark, aligned to ticker index
    adx_length = strat.get("adx_length", 14)
    if not bench_daily.empty:
        adx = ta.adx(
            bench_daily["High"], bench_daily["Low"], bench_daily["Close"],
            length=adx_length,
        )
        if adx is not None and not adx.empty:
            adx_col = [c for c in adx.columns if c.startswith("ADX_")]
            if adx_col:
                adx_aligned = adx[adx_col[0]].reindex(idx, method="ffill")
            else:
                adx_aligned = pd.Series(100.0, index=idx)
        else:
            adx_aligned = pd.Series(100.0, index=idx)
    else:
        adx_aligned = pd.Series(100.0, index=idx)

    # ATR
    atr = ta.atr(
        df_daily["High"], df_daily["Low"], df_daily["Close"],
        length=strat["atr_length"],
    )
    if atr is None:
        atr = pd.Series(0.0, index=idx)

    return PrecomputedTicker(
        check_ema_d=check_ema_d,
        check_ema_w=check_ema_w,
        check_macd=check_macd,
        rsi_values=rsi_values,
        mfi_by_length=mfi_by_length,
        check_rs=check_rs,
        vix_aligned=vix_aligned,
        adx_aligned=adx_aligned,
        atr=atr,
        close=df_daily["Close"],
        df_daily=df_daily,
    )


def _precompute_all(
    ticker_data: dict,
    bench_daily: pd.DataFrame,
    vix_daily: pd.DataFrame,
    cfg: dict,
    console: Console,
) -> dict[str, PrecomputedTicker]:
    """Precompute indicators for all tickers."""
    t0 = time.time()
    console.print("[bold]Precomputing signals (once)...[/bold]")
    result = {}
    for i, (ticker, (df_d, df_w)) in enumerate(ticker_data.items(), 1):
        console.print(f"  [{i}/{len(ticker_data)}] {ticker}", end="\r")
        try:
            result[ticker] = _precompute_ticker(df_d, df_w, bench_daily, vix_daily, cfg)
        except Exception:
            continue
    elapsed = time.time() - t0
    console.print(f"  Precomputed {len(result)} tickers in {elapsed:.1f}s    \n")
    return result


# =========================================================================
# Fast signal + backtest (per trial)
# =========================================================================

def _build_signals_fast(precomp: PrecomputedTicker, params: dict) -> pd.DataFrame:
    """Apply thresholds to precomputed indicators. ~20x faster than compute_all_signals."""
    idx = precomp.close.index
    signals = pd.DataFrame(index=idx)

    # Fixed checks (parameter-independent)
    signals["check_ema_d"] = precomp.check_ema_d
    signals["check_ema_w"] = precomp.check_ema_w
    signals["check_macd"] = precomp.check_macd
    signals["check_rs"] = precomp.check_rs

    # Threshold-dependent checks (cheap comparisons)
    signals["check_rsi"] = (precomp.rsi_values > params["rsi_threshold"]).fillna(False)
    mfi_values = precomp.mfi_by_length[params["mfi_length"]]
    signals["check_mfi"] = (mfi_values > params["mfi_threshold"]).fillna(False)

    # Score
    check_cols = [
        "check_ema_d", "check_ema_w", "check_macd",
        "check_rsi", "check_mfi", "check_rs",
    ]
    signals["score"] = signals[check_cols].sum(axis=1).astype(int)

    # Gates (threshold-dependent)
    signals["gate_vix"] = (precomp.vix_aligned < params["vix_threshold"]).fillna(True)
    signals["gate_adx"] = (precomp.adx_aligned >= params["adx_threshold"]).fillna(True)
    signals["gate_bench"] = True

    # GO signal
    signals["go"] = (
        (signals["score"] >= params["go_threshold"])
        & signals["gate_vix"]
        & signals["gate_adx"]
    )

    signals["atr"] = precomp.atr
    signals["close"] = precomp.close

    return signals


def _run_universe_fast(
    cfg: dict,
    ticker_precomputed: dict[str, PrecomputedTicker],
    params: dict,
    start: str,
    end: str,
    bt_mode: str,
    trial: Optional[optuna.Trial] = None,
) -> dict:
    """Run backtest across all tickers using precomputed signals.

    If trial is provided, reports intermediate results for pruning.
    """
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0
    ticker_returns = []
    ticker_dds = []

    for i, (ticker, precomp) in enumerate(ticker_precomputed.items()):
        try:
            signals = _build_signals_fast(precomp, params)
            signals_bt = signals.loc[start:end]
            df_bt = precomp.df_daily.loc[start:end]
            if df_bt.empty or len(df_bt) < 20:
                continue
            result = run_backtest(signals_bt, df_bt, cfg, ticker=ticker, mode=bt_mode)
            metrics = compute_metrics(result, cfg)
            total_trades += metrics["total_trades"]
            total_wins += metrics["winning_trades"]
            total_pnl += metrics["final_equity"] - cfg["position_sizing"]["capital"]
            ticker_returns.append(metrics["total_return_pct"])
            ticker_dds.append(metrics["max_drawdown_pct"])
        except Exception:
            continue

        # Optuna pruning: report running avg after each ticker
        if trial is not None and ticker_returns:
            trial.report(sum(ticker_returns) / len(ticker_returns), i)
            if trial.should_prune():
                raise optuna.TrialPruned()

    if not ticker_returns:
        return {"avg_return": -999, "total_trades": 0, "win_rate": 0,
                "profitable_pct": 0, "avg_dd": 0, "total_pnl": 0}

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
        "tickers_tested": len(ticker_returns),
    }


def _config_to_params(cfg: dict) -> dict:
    """Extract search-space params from a config dict (for baseline comparison)."""
    return {
        "vix_threshold": cfg["strategy"]["vix_threshold"],
        "mfi_threshold": cfg["strategy"].get("mfi_threshold", 45),
        "mfi_length": cfg["strategy"].get("mfi_length", 14),
        "rsi_threshold": cfg["strategy"]["rsi_threshold"],
        "adx_threshold": cfg["strategy"]["adx_threshold"],
        "go_threshold": cfg["alerts"]["go_threshold"],
    }


def _suggest_params(trial: optuna.Trial) -> dict:
    """Define Optuna search space."""
    return {
        "vix_threshold": trial.suggest_categorical("vix_threshold", [20, 25, 30, 35, 999]),
        "mfi_threshold": trial.suggest_int("mfi_threshold", 35, 60, step=5),
        "mfi_length": trial.suggest_categorical("mfi_length", [10, 14, 20]),
        "rsi_threshold": trial.suggest_int("rsi_threshold", 35, 60, step=5),
        "adx_threshold": trial.suggest_int("adx_threshold", 10, 30, step=5),
        "go_threshold": trial.suggest_int("go_threshold", 3, 5),
    }


# =========================================================================
# MODE 1: Simple optimization (single period)
# =========================================================================

def run_simple_optimization(
    mode: str, n_trials: int, console: Console,
) -> None:
    """Optuna optimization on a single training period."""
    mc = MODE_CONFIG[mode]

    with open(mc["config_path"]) as f:
        base_cfg = yaml.safe_load(f)

    start = "2020-01-01"
    end = "2024-12-31"
    ws = warmup_start(start, extra_bars=100)
    tickers = mc["tickers"]

    console.print(f"\n[bold]Optuna Optimization — {mode.upper()} CFD[/bold]")
    console.print(f"Period: {start} to {end}")
    console.print(f"Tickers: {len(tickers)}")
    console.print(f"Trials: {n_trials}")
    console.print(f"Benchmark: {mc['benchmark']}\n")

    # Fetch data
    console.print("[bold]Fetching data...[/bold]")
    bench_daily = fetch_historical(mc["benchmark"], ws, end)
    vix_daily = fetch_historical("^VIX", ws, end)

    ticker_data = {}
    for i, ticker in enumerate(tickers, 1):
        console.print(f"  [{i}/{len(tickers)}] {ticker}", end="\r")
        df_d = fetch_historical(ticker, ws, end)
        df_w = fetch_weekly_historical(ticker, ws, end)
        if not df_d.empty and len(df_d) >= 60:
            ticker_data[ticker] = (df_d, df_w)
    console.print(f"  Loaded {len(ticker_data)} tickers.    \n")

    # Precompute signals (once)
    ticker_precomputed = _precompute_all(
        ticker_data, bench_daily, vix_daily, base_cfg, console,
    )

    # Optuna study with pruning
    def objective(trial: optuna.Trial) -> float:
        params = _suggest_params(trial)
        agg = _run_universe_fast(
            base_cfg, ticker_precomputed, params, start, end, mc["bt_mode"],
            trial=trial,
        )

        trial.set_user_attr("win_rate", agg.get("win_rate", 0))
        trial.set_user_attr("total_trades", agg.get("total_trades", 0))
        trial.set_user_attr("profitable_pct", agg.get("profitable_pct", 0))
        trial.set_user_attr("avg_dd", agg.get("avg_dd", 0))
        trial.set_user_attr("total_pnl", agg.get("total_pnl", 0))

        return agg["avg_return"]

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=20, n_warmup_steps=5),
        study_name=f"{mode}_cfd_optimization",
    )

    console.print("[bold]Running Optuna optimization...[/bold]")
    t0 = time.time()
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    elapsed = time.time() - t0

    pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
    console.print(
        f"Completed in {elapsed:.1f}s "
        f"({len(study.trials)} trials, {pruned} pruned)\n"
    )

    # --- Results ---
    _print_simple_results(study, mode, start, end, console)
    _save_simple_csv(study, mode)


def _print_simple_results(
    study: optuna.Study, mode: str, start: str, end: str, console: Console,
) -> None:
    """Print top results from Optuna study."""
    completed = [
        t for t in study.trials
        if t.state == optuna.trial.TrialState.COMPLETE
    ]
    trials = sorted(completed, key=lambda t: t.value if t.value is not None else -999, reverse=True)

    table = Table(title=f"\nTop 20 — {mode.upper()} CFD ({start} to {end})", show_lines=False)
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
    table.add_column("Prof%", justify="right")
    table.add_column("Avg DD%", justify="right")
    table.add_column("PnL", justify="right")

    for i, t in enumerate(trials[:20], 1):
        p = t.params
        vix_str = "OFF" if p["vix_threshold"] >= 999 else str(p["vix_threshold"])
        ret = t.value if t.value is not None else 0
        ret_style = "green" if ret >= 0 else "red"
        currency = "\u20ac" if mode == "ita" else "$"
        table.add_row(
            str(i), vix_str, str(p["mfi_threshold"]), str(p["mfi_length"]),
            str(p["rsi_threshold"]), str(p["adx_threshold"]), str(p["go_threshold"]),
            str(t.user_attrs.get("total_trades", 0)),
            f"{t.user_attrs.get('win_rate', 0)}%",
            f"[{ret_style}]{ret:+.2f}%[/{ret_style}]",
            f"{t.user_attrs.get('profitable_pct', 0)}%",
            f"{t.user_attrs.get('avg_dd', 0):.1f}%",
            f"{currency}{t.user_attrs.get('total_pnl', 0):,.0f}",
        )

    console.print(table)

    # Best params
    best = study.best_trial
    console.print("\n[bold green]Best parameters:[/bold green]")
    for k, v in best.params.items():
        display = "OFF (disabled)" if k == "vix_threshold" and v >= 999 else str(v)
        console.print(f"  {k}: {display}")
    console.print(
        f"  => Avg return: {best.value:+.2f}% | "
        f"Win rate: {best.user_attrs.get('win_rate', 0)}% | "
        f"Trades: {best.user_attrs.get('total_trades', 0)}"
    )

    # Parameter importance
    try:
        importances = optuna.importance.get_param_importances(study)
        console.print("\n[bold]Parameter importance:[/bold]")
        for param, imp in importances.items():
            bar = "\u2588" * int(imp * 40)
            console.print(f"  {param:20s} {bar} {imp:.1%}")
    except Exception:
        pass


def _save_simple_csv(study: optuna.Study, mode: str) -> None:
    """Save all completed trials to CSV."""
    output_dir = f"output/optimization_{mode}"
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "optuna_results.csv")

    fieldnames = [
        "trial", "vix_threshold", "mfi_threshold", "mfi_length", "rsi_threshold",
        "adx_threshold", "go_threshold", "avg_return", "win_rate", "total_trades",
        "profitable_pct", "avg_dd", "total_pnl",
    ]

    completed = [
        t for t in study.trials
        if t.state == optuna.trial.TrialState.COMPLETE
    ]
    trials = sorted(completed, key=lambda t: t.value if t.value is not None else -999, reverse=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in trials:
            writer.writerow({
                "trial": t.number,
                **t.params,
                "avg_return": t.value,
                "win_rate": t.user_attrs.get("win_rate", 0),
                "total_trades": t.user_attrs.get("total_trades", 0),
                "profitable_pct": t.user_attrs.get("profitable_pct", 0),
                "avg_dd": t.user_attrs.get("avg_dd", 0),
                "total_pnl": t.user_attrs.get("total_pnl", 0),
            })

    Console().print(f"\n[bold]Results saved to:[/bold] {csv_path}")


# =========================================================================
# MODE 2: Walk-Forward Analysis with Optuna
# =========================================================================

@dataclass
class WFAWindowResult:
    """Result of one walk-forward window."""
    window_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: dict = field(default_factory=dict)
    is_avg_return: float = 0.0
    is_win_rate: float = 0.0
    is_total_trades: int = 0
    oos_avg_return: float = 0.0
    oos_win_rate: float = 0.0
    oos_total_trades: int = 0
    oos_total_pnl: float = 0.0
    oos_avg_dd: float = 0.0
    oos_tickers_tested: int = 0
    efficiency_ratio: float = 0.0


def run_wfa_optimization(
    mode: str, n_trials: int, console: Console,
) -> None:
    """Walk-Forward Analysis using Optuna per window."""
    mc = MODE_CONFIG[mode]

    with open(mc["config_path"]) as f:
        base_cfg = yaml.safe_load(f)

    data_start = "2018-01-01"
    data_end = "2024-12-31"
    ws = warmup_start(data_start, extra_bars=100)
    tickers = mc["tickers"]

    console.print(f"\n[bold]Walk-Forward Analysis (Optuna) — {mode.upper()} CFD[/bold]")
    console.print(f"Windows: {len(WFA_WINDOWS)} (24m train / 6m test)")
    console.print(f"Tickers: {len(tickers)}")
    console.print(f"Trials per window: {n_trials}")
    console.print(f"Benchmark: {mc['benchmark']}\n")

    # Fetch data
    console.print("[bold]Fetching data (full range)...[/bold]")
    bench_daily = fetch_historical(mc["benchmark"], ws, data_end)
    vix_daily = fetch_historical("^VIX", ws, data_end)

    ticker_data = {}
    for i, ticker in enumerate(tickers, 1):
        console.print(f"  [{i}/{len(tickers)}] {ticker}", end="\r")
        df_d = fetch_historical(ticker, ws, data_end)
        df_w = fetch_weekly_historical(ticker, ws, data_end)
        if not df_d.empty and len(df_d) >= 60:
            ticker_data[ticker] = (df_d, df_w)
    console.print(f"  Loaded {len(ticker_data)} tickers.    \n")

    # Precompute signals (once for all windows)
    ticker_precomputed = _precompute_all(
        ticker_data, bench_daily, vix_daily, base_cfg, console,
    )

    # WFA loop
    wfa_t0 = time.time()
    window_results: list[WFAWindowResult] = []

    for w_idx, window in enumerate(WFA_WINDOWS):
        train_start = window["train_start"]
        train_end = window["train_end"]
        test_start = window["test_start"]
        test_end = window["test_end"]

        console.print(f"[bold cyan]Window {w_idx + 1}/{len(WFA_WINDOWS)}[/bold cyan]")
        console.print(f"  Train: {train_start} \u2192 {train_end}")
        console.print(f"  Test:  {test_start} \u2192 {test_end}")

        # Optuna optimization on training window
        def make_objective(ts, te):
            def objective(trial: optuna.Trial) -> float:
                params = _suggest_params(trial)
                agg = _run_universe_fast(
                    base_cfg, ticker_precomputed, params, ts, te, mc["bt_mode"],
                    trial=trial,
                )
                trial.set_user_attr("win_rate", agg.get("win_rate", 0))
                trial.set_user_attr("total_trades", agg.get("total_trades", 0))
                return agg["avg_return"]
            return objective

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42 + w_idx),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=15, n_warmup_steps=5),
        )
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study.optimize(make_objective(train_start, train_end), n_trials=n_trials)

        best = study.best_trial
        best_params = best.params
        is_ret = best.value if best.value is not None else 0
        pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])

        console.print(f"  Best IS: {is_ret:+.2f}% | pruned: {pruned}/{n_trials}")

        # Test on OOS window (no pruning)
        oos = _run_universe_fast(
            base_cfg, ticker_precomputed, best_params,
            test_start, test_end, mc["bt_mode"],
        )
        oos_ret = oos["avg_return"]

        # Efficiency
        if is_ret > 0:
            eff = oos_ret / is_ret
        elif is_ret == 0:
            eff = 0.0
        else:
            eff = -1.0

        eff_style = "green" if eff >= 0.5 else "yellow" if eff >= 0 else "red"
        console.print(
            f"  OOS: {oos_ret:+.2f}% | trades {oos.get('total_trades', 0)} | "
            f"[{eff_style}]efficiency {eff:.2f}[/{eff_style}]\n"
        )

        window_results.append(WFAWindowResult(
            window_idx=w_idx + 1,
            train_start=train_start, train_end=train_end,
            test_start=test_start, test_end=test_end,
            best_params=best_params,
            is_avg_return=is_ret,
            is_win_rate=best.user_attrs.get("win_rate", 0),
            is_total_trades=best.user_attrs.get("total_trades", 0),
            oos_avg_return=oos_ret,
            oos_win_rate=oos.get("win_rate", 0),
            oos_total_trades=oos.get("total_trades", 0),
            oos_total_pnl=oos.get("total_pnl", 0),
            oos_avg_dd=oos.get("avg_dd", 0),
            oos_tickers_tested=oos.get("tickers_tested", 0),
            efficiency_ratio=round(eff, 3),
        ))

    wfa_elapsed = time.time() - wfa_t0
    console.print(f"[bold]WFA completed in {wfa_elapsed:.1f}s[/bold]\n")

    # --- Summary ---
    _print_wfa_summary(
        window_results, mode, base_cfg, ticker_precomputed, mc["bt_mode"], console,
    )
    _save_wfa_csv(window_results, mode)


def _print_wfa_summary(
    window_results: list[WFAWindowResult], mode: str, base_cfg: dict,
    ticker_precomputed: dict[str, PrecomputedTicker], bt_mode: str,
    console: Console,
) -> None:
    """Print WFA summary report."""
    console.print("\n" + "=" * 80)
    console.print(f"[bold]WALK-FORWARD ANALYSIS (Optuna) — {mode.upper()} CFD[/bold]")
    console.print("=" * 80)

    currency = "\u20ac" if mode == "ita" else "$"

    table = Table(title="Walk-Forward Results by Window", show_lines=True)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Train", no_wrap=True)
    table.add_column("Test", no_wrap=True)
    table.add_column("IS Ret%", justify="right")
    table.add_column("OOS Ret%", justify="right")
    table.add_column("OOS Win%", justify="right")
    table.add_column("OOS Trades", justify="right")
    table.add_column("OOS PnL", justify="right")
    table.add_column("Efficiency", justify="right")
    table.add_column("Best Params", no_wrap=False)

    for wr in window_results:
        is_s = "green" if wr.is_avg_return >= 0 else "red"
        oos_s = "green" if wr.oos_avg_return >= 0 else "red"
        eff_s = "green" if wr.efficiency_ratio >= 0.5 else "yellow" if wr.efficiency_ratio >= 0 else "red"

        p = wr.best_params
        params_short = (
            f"VIX={'OFF' if p.get('vix_threshold', 0) >= 999 else p.get('vix_threshold', '?')} "
            f"MFI={p.get('mfi_threshold', '?')}/{p.get('mfi_length', '?')} "
            f"RSI={p.get('rsi_threshold', '?')} "
            f"ADX={p.get('adx_threshold', '?')} "
            f"GO={p.get('go_threshold', '?')}"
        )

        table.add_row(
            str(wr.window_idx),
            f"{wr.train_start} \u2192 {wr.train_end}",
            f"{wr.test_start} \u2192 {wr.test_end}",
            f"[{is_s}]{wr.is_avg_return:+.2f}%[/{is_s}]",
            f"[{oos_s}]{wr.oos_avg_return:+.2f}%[/{oos_s}]",
            f"{wr.oos_win_rate:.0f}%",
            str(wr.oos_total_trades),
            f"{currency}{wr.oos_total_pnl:,.0f}",
            f"[{eff_s}]{wr.efficiency_ratio:.2f}[/{eff_s}]",
            params_short,
        )

    console.print(table)

    # Aggregate
    oos_returns = [wr.oos_avg_return for wr in window_results]
    efficiencies = [wr.efficiency_ratio for wr in window_results]
    avg_oos = np.mean(oos_returns) if oos_returns else 0
    avg_eff = np.mean(efficiencies) if efficiencies else 0
    positive = sum(1 for r in oos_returns if r > 0)

    console.print("\n[bold]Aggregate OOS:[/bold]")
    console.print(f"  Avg OOS return:       {avg_oos:+.2f}%")
    console.print(f"  Profitable windows:   {positive}/{len(window_results)}")
    console.print(f"  Avg efficiency ratio: {avg_eff:.2f}")

    # Parameter stability
    param_keys = ["vix_threshold", "mfi_threshold", "mfi_length",
                  "rsi_threshold", "adx_threshold", "go_threshold"]
    console.print("\n[bold]Parameter Stability:[/bold]")
    stable_params = {}
    for param in param_keys:
        values = [wr.best_params.get(param) for wr in window_results]
        counts = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
        stable_params[param] = sorted_counts[0][0]
        dist = ", ".join(
            f"{v}={'OFF' if param == 'vix_threshold' and v >= 999 else v} ({c}/{len(window_results)})"
            for v, c in sorted_counts
        )
        console.print(f"  {param}: {dist}")

    # Overfitting verdict
    console.print("\n[bold]Overfitting Assessment:[/bold]")
    if avg_eff >= 0.5:
        console.print("  [bold green]LOW RISK[/bold green] — Parameters generalize well.")
    elif avg_eff >= 0.25:
        console.print("  [bold yellow]MODERATE RISK[/bold yellow] — Some OOS degradation.")
    elif avg_eff >= 0:
        console.print("  [bold red]HIGH RISK[/bold red] — Significant OOS degradation.")
    else:
        console.print("  [bold red]OVERFIT[/bold red] — OOS inverts IS results.")

    # Most stable params
    console.print("\n[bold]Most Stable Parameters (mode across windows):[/bold]")
    for p, v in stable_params.items():
        display = "OFF" if p == "vix_threshold" and v >= 999 else str(v)
        console.print(f"  {p}: {display}")

    # Baseline comparison (uses fast path too)
    console.print("\n[bold]Baseline: current config params across all OOS windows:[/bold]")
    base_params = _config_to_params(base_cfg)
    baseline_oos = []
    for window in WFA_WINDOWS:
        agg = _run_universe_fast(
            base_cfg, ticker_precomputed, base_params,
            window["test_start"], window["test_end"], bt_mode,
        )
        baseline_oos.append(agg["avg_return"])
    baseline_avg = np.mean(baseline_oos) if baseline_oos else 0
    console.print(f"  Current config OOS avg: {baseline_avg:+.2f}%")
    console.print(f"  Optuna WFA OOS avg:     {avg_oos:+.2f}%")
    diff = avg_oos - baseline_avg
    if diff > 0:
        console.print(f"  [green]Optuna adds +{diff:.2f}% over fixed params[/green]")
    else:
        console.print(f"  [yellow]Fixed params perform {-diff:.2f}% better[/yellow]")
    console.print()


def _save_wfa_csv(window_results: list[WFAWindowResult], mode: str) -> None:
    """Save WFA results to CSV."""
    output_dir = f"output/optimization_{mode}"
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "optuna_wfa_results.csv")

    fieldnames = [
        "window", "train_start", "train_end", "test_start", "test_end",
        "vix_threshold", "mfi_threshold", "mfi_length", "rsi_threshold",
        "adx_threshold", "go_threshold",
        "is_avg_return", "is_win_rate", "is_total_trades",
        "oos_avg_return", "oos_win_rate", "oos_total_trades",
        "oos_total_pnl", "oos_avg_dd", "efficiency_ratio",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for wr in window_results:
            writer.writerow({
                "window": wr.window_idx,
                "train_start": wr.train_start, "train_end": wr.train_end,
                "test_start": wr.test_start, "test_end": wr.test_end,
                **wr.best_params,
                "is_avg_return": wr.is_avg_return,
                "is_win_rate": wr.is_win_rate,
                "is_total_trades": wr.is_total_trades,
                "oos_avg_return": wr.oos_avg_return,
                "oos_win_rate": wr.oos_win_rate,
                "oos_total_trades": wr.oos_total_trades,
                "oos_total_pnl": wr.oos_total_pnl,
                "oos_avg_dd": wr.oos_avg_dd,
                "efficiency_ratio": wr.efficiency_ratio,
            })

    Console().print(f"[bold]WFA results saved to:[/bold] {csv_path}")


# =========================================================================
# CLI
# =========================================================================

def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(
        description="Optuna parameter optimization for ITA/US CFD strategies"
    )
    parser.add_argument(
        "--mode", choices=["ita", "us"], required=True,
        help="Strategy mode: ita (FTSE MIB) or us (S&P 500)",
    )
    parser.add_argument(
        "--wfa", action="store_true",
        help="Run Walk-Forward Analysis instead of single-period optimization",
    )
    parser.add_argument(
        "--trials", type=int, default=300,
        help="Number of Optuna trials (default: 300)",
    )
    args = parser.parse_args()
    console = Console()

    if args.wfa:
        run_wfa_optimization(args.mode, args.trials, console)
    else:
        run_simple_optimization(args.mode, args.trials, console)


if __name__ == "__main__":
    main()
