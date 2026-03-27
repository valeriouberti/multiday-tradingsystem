#!/usr/bin/env python3
"""Backtest entry point for ITA CFD and ETF strategies.

Usage:
    python backtest.py --mode ita --ticker ENI.MI --start 2024-01-01
    python backtest.py --mode etf --start 2024-06-01 --end 2025-12-31
    python backtest.py --mode ita --config config_ita.yaml --start 2024-01-01 --save-plot
"""

import argparse
import logging
import os
from datetime import datetime

import yaml

from backtester.data import fetch_historical, fetch_weekly_historical, warmup_start
from backtester.engine import run_backtest
from backtester.metrics import compute_metrics, print_metrics, save_trades_csv
from backtester.plots import plot_equity_curve, plot_trades_on_price
from backtester.signals import compute_all_signals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest ITA/ETF swing trading strategy")
    parser.add_argument("--mode", choices=["ita", "etf"], default="ita", help="Strategy mode")
    parser.add_argument("--config", type=str, default=None, help="Path to YAML config")
    parser.add_argument("--ticker", type=str, default=None, help="Single ticker to backtest (overrides config)")
    parser.add_argument("--start", type=str, required=True, help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="Backtest end date (YYYY-MM-DD, default: today)")
    parser.add_argument("--capital", type=float, default=None, help="Override initial capital")
    parser.add_argument("--output-dir", type=str, default="output/backtest", help="Output directory")
    parser.add_argument("--no-plot", action="store_true", help="Skip plotting")
    parser.add_argument("--save-plot", action="store_true", help="Save plots to files instead of showing")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return parser.parse_args()


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Load config
    if args.config:
        config_path = args.config
    else:
        config_path = "config_ita.yaml" if args.mode == "ita" else "config_etf.yaml"
    cfg = load_config(config_path)

    # Override capital if specified
    if args.capital:
        cfg["position_sizing"]["capital"] = args.capital

    end_date = args.end or datetime.now().strftime("%Y-%m-%d")
    tickers = [args.ticker] if args.ticker else cfg["tickers"]
    benchmark = cfg.get("benchmark", "ETFMIB.MI" if args.mode == "ita" else "CSSPX.MI")

    # Warmup start: push back for indicator lookback
    ws = warmup_start(args.start, extra_bars=100)

    print(f"Backtesting {len(tickers)} ticker(s) | {args.mode.upper()} mode | {args.start} to {end_date}")
    print(f"Benchmark: {benchmark} | Capital: \u20ac{cfg['position_sizing']['capital']}")
    print("-" * 60)

    # Fetch benchmark and VIX data once (shared across tickers)
    bench_daily = fetch_historical(benchmark, ws, end_date)
    vix_daily = fetch_historical("^VIX", ws, end_date)

    all_results = []

    for ticker in tickers:
        print(f"\n{'='*60}")
        print(f"  {ticker}")
        print(f"{'='*60}")

        # Fetch ticker data
        df_daily = fetch_historical(ticker, ws, end_date)
        df_weekly = fetch_weekly_historical(ticker, ws, end_date)

        if df_daily.empty:
            print(f"  No data for {ticker}, skipping.")
            continue

        # Compute vectorized signals
        signals = compute_all_signals(df_daily, df_weekly, bench_daily, vix_daily, cfg, args.mode)

        # Trim to backtest window (exclude warmup period)
        bt_start = args.start
        signals_bt = signals.loc[bt_start:]
        df_bt = df_daily.loc[bt_start:]

        if df_bt.empty:
            print(f"  No data in backtest window for {ticker}, skipping.")
            continue

        # Count GO signals
        go_count = int(signals_bt["go"].sum())
        print(f"  GO signals in period: {go_count}")

        # Run simulation
        result = run_backtest(signals_bt, df_bt, cfg, ticker=ticker, mode=args.mode)
        all_results.append((ticker, result))

        # Metrics
        metrics = compute_metrics(result, cfg)
        print_metrics(metrics, ticker)

        # Save trade log
        csv_path = save_trades_csv(result.trades, args.output_dir, ticker)
        print(f"  Trades saved to: {csv_path}")

        # Plots
        if not args.no_plot:
            if args.save_plot:
                eq_path = os.path.join(args.output_dir, f"equity_{ticker.replace('.', '_')}.png")
                tr_path = os.path.join(args.output_dir, f"trades_{ticker.replace('.', '_')}.png")
                plot_equity_curve(result, ticker, output_path=eq_path)
                plot_trades_on_price(df_bt, result.trades, ticker, output_path=tr_path)
                print(f"  Plots saved to: {args.output_dir}/")
            else:
                plot_equity_curve(result, ticker)
                plot_trades_on_price(df_bt, result.trades, ticker)

    # Aggregate summary if multiple tickers
    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print("  AGGREGATE SUMMARY")
        print(f"{'='*60}")
        total_trades = sum(len(r.trades) for _, r in all_results)
        total_wins = sum(1 for _, r in all_results for t in r.trades if t.pnl > 0)
        total_pnl = sum(t.pnl for _, r in all_results for t in r.trades)
        print(f"  Total trades: {total_trades}")
        print(f"  Total wins: {total_wins} ({total_wins/total_trades*100:.1f}%)" if total_trades > 0 else "")
        print(f"  Total P&L: \u20ac{total_pnl:.2f}")


if __name__ == "__main__":
    main()
