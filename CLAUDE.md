# Multiday Trading Validator — Project Guide

## Project Purpose
Python tool that validates stocks and sector ETFs against technical indicators before entry.
Three strategies: ITA CFD (FTSE MIB via broker CFD), US CFD (S&P 500 via broker CFD),
and ETF (sector ETFs on Borsa Italiana, cash). Designed for multiday swing trading (3-7 sessions).

## Architecture
```
project/
├── CLAUDE.md               ← This file
├── main.py                 ← Unified entry point (--mode ita/us/etf)
├── config/
│   ├── ita.yaml            ← ITA config (39 FTSE MIB stocks, Optuna WFA tuned params)
│   ├── us.yaml             ← US config (100 S&P 500 stocks + 33-stock optimization sample)
│   └── etf.yaml            ← ETF config (sector ETFs, edit daily)
├── core/
│   ├── __init__.py
│   ├── data.py             ← yfinance data fetching with cache
│   ├── indicators.py       ← Common indicators (EMA, MACD, RSI, MFI, RS, gates, entry helpers)
│   └── position_sizing.py  ← CFD + ETF position sizing (shared)
├── strategies/
│   ├── __init__.py
│   ├── ita.py              ← ITA: 6 checks + 2 gates scorer
│   ├── us.py               ← US: 6 checks + 2 gates scorer + ranking
│   └── etf.py              ← ETF: 6 checks + 4 gates scorer + bench health + correlations
├── reporting/
│   ├── __init__.py
│   ├── ita_report.py       ← ITA Rich table + CSV (EUR, broker CFD format)
│   ├── us_report.py        ← US Rich table + CSV (USD, broker CFD format)
│   ├── etf_report.py       ← ETF Rich table + CSV (EUR, broker cash format)
│   ├── pdf_report.py       ← PDF report generation (ITA, US, ETF)
│   ├── report_utils.py     ← Shared Rich formatting (check_cell, status_text)
│   └── telegram.py         ← Telegram PDF delivery + top-5 captions
├── backtester/
│   ├── __init__.py
│   ├── data.py             ← Historical data fetching with warmup buffer
│   ├── signals.py          ← Vectorized signal generation (full time-series)
│   ├── engine.py           ← Bar-by-bar simulation (SL/TP1/Chandelier lifecycle)
│   ├── metrics.py          ← Performance analytics (Sharpe, Sortino, Calmar, drawdown)
│   └── plots.py            ← Equity curve + trade markers (matplotlib)
├── tools/
│   ├── backtest.py         ← CLI: single-ticker backtest (--mode, --ticker, --start, --end)
│   ├── montecarlo.py       ← Monte Carlo simulation (ITA + US + ETF, trade-order shuffling)
│   └── optimize.py         ← Optuna Bayesian optimization (ITA + US + ETF, simple + WFA)
├── scripts/
│   └── update_tickers.py   ← CI helper to update tickers in YAML
├── .github/workflows/
│   ├── ita-validator.yml   ← 08:30 CEST Mon-Fri + workflow_dispatch
│   ├── us-validator.yml    ← 13:15 CEST Mon-Fri + workflow_dispatch
│   └── etf-validator.yml   ← 14:00 CEST Mon-Fri + workflow_dispatch
├── output/
│   ├── reports_ita/        ← Daily CSV + PDF reports (ITA)
│   ├── reports_us/         ← Daily CSV + PDF reports (US)
│   ├── reports_etf/        ← Daily CSV + PDF reports (ETF)
│   ├── optimization_ita/   ← Optuna results (ITA)
│   ├── optimization_us/    ← Optuna results (US)
│   └── optimization_etf/   ← Optuna results (ETF)
├── docs/
│   ├── STRATEGY.md         ← Strategy overview + shared rules
│   ├── STRATEGY_ITA.md     ← ITA prompts, params, tickers
│   ├── STRATEGY_US.md      ← US prompts, params, universe
│   └── STRATEGY_ETF.md     ← ETF prompts, gates, ETF list
├── pinescript/
│   ├── ita_cfd_validator.pine  ← TradingView ITA v1.2 (Optuna WFA tuned)
│   └── us_cfd_validator.pine   ← TradingView US v1.0 (Optuna WFA tuned)
└── requirements.txt
```

## Config Files
- `config/ita.yaml`: 39 FTSE MIB stocks (.MI suffix), benchmark ETFMIB.MI, leverage 5:1, Optuna WFA tuned params
- `config/us.yaml`: 100 S&P 500 stocks, 33-stock optimization sample, benchmark SPY, leverage 5:1, Optuna WFA tuned
- `config/etf.yaml`: 3 sector ETFs (.MI suffix), benchmark CSSPX.MI, no leverage
- Tickers override via `--tickers` CLI flag (ITA + US)

## Technical Indicators Used
All computed via pandas-ta library on DAILY timeframe:
1. EMA 20 > EMA 50 Daily     → Trend direction
2. EMA 20 > EMA 50 Weekly    → Structural trend filter
3. MACD > Signal Line        → Momentum confirmation (12/26/9)
4. RSI > 45 (ITA) / > 40 (US) / > 35 (ETF) → Momentum filter (length 14)
5. MFI > 40 (ITA) / > 45 (US) / > 40 (ETF) → Money Flow Index (length 20 ETF / 14 CFD)
6. RS Line vs Benchmark      → Relative strength (20d lookback, 5d ROC)

Entry timing helpers:
- ATR(14) Daily              → Stop loss + TP1 + Chandelier Exit
- EMA 9 Daily                → Bone Zone entry detection
- Opening Range              → ORB breakout via H1 data

## Gates (not scored, downgrade GO to WATCH)
**ITA (2 gates):** VIX < 35, ADX on ETFMIB.MI >= 15
**US (2 gates):** VIX < 30, ADX on SPY >= 10
**ETF (4 gates):** VIX < 35, Benchmark EMA health, ADX >= 10, Correlation < 0.7

## Scoring Logic
6 checks, max score 6/6:
- **ITA:** Score >= 3/6 → GO, 2/6 → WATCH, <= 1/6 → SKIP
- **US:** Score >= 4/6 → GO, 3/6 → WATCH, <= 2/6 → SKIP
- **ETF:** Score >= 3/6 → GO, 2/6 → WATCH, <= 1/6 → SKIP

## Key Rules (never change these in code)
- All trend/momentum checks use DAILY timeframe
- H1 data used ONLY for ORB detection
- RS Line compares ticker vs its benchmark
- MFI used instead of OBV (more reliable on Borsa Italiana)
- prepost=True always (premarket data included)
- auto_adjust=True always (split/dividend adjusted)
- Never hardcode tickers or parameters in .py files — read from YAML configs

## Dependencies
- yfinance >= 0.2.40
- pandas-ta >= 0.3.14b
- pandas >= 2.0
- pyyaml >= 6.0
- rich >= 13.0
- matplotlib >= 3.7
- python-dotenv == 1.0.1
- optuna >= 3.0
- fpdf2 >= 2.7

## Running

### Daily Validation
```bash
python main.py --mode ita                                    # All 39 FTSE MIB stocks
python main.py --mode ita --tickers "ISP.MI,UCG.MI,LDO.MI"  # Override with specific tickers
python main.py --mode us                                     # Top 100 S&P 500 stocks
python main.py --mode us --tickers "AAPL,MSFT,NVDA"         # Override with specific tickers
python main.py --mode etf                                    # Sector ETFs
```

### Backtesting
```bash
python tools/backtest.py --ticker ISP.MI --start 2023-01-01 --end 2024-12-31   # Single ticker
python tools/montecarlo.py --mode ita --simulations 10000                       # Monte Carlo ITA
python tools/montecarlo.py --mode us --simulations 10000 --save-plot            # Monte Carlo US + plots
```

### Parameter Optimization (Optuna)
```bash
python tools/optimize.py --mode ita --trials 300          # ITA single-period
python tools/optimize.py --mode us --trials 300           # US single-period (33 sector-sample)
python tools/optimize.py --mode ita --wfa --trials 200    # ITA Walk-Forward Analysis
python tools/optimize.py --mode us --wfa --trials 200     # US Walk-Forward Analysis
```

## Tuned Parameters

### ITA (Optuna WFA, 2020-2024)

| Parameter | Original | Tuned | Rationale |
| :-- | :-- | :-- | :-- |
| rsi_threshold | 50 | **45** | Catches early-trend entries |
| mfi_threshold | 50 | **40** | Less restrictive money flow filter |
| vix_threshold | 25 | **35** | Old gate too strict, blocked good trades in moderate fear |
| adx_threshold | 20 | **15** | Mild loosening, still filters flat markets |
| go_threshold | 5 | **3** | Perfectly stable across all 8 WFA windows |

### US (Optuna WFA, 2019-2024)

| Parameter | Default | Tuned | Rationale |
| :-- | :-- | :-- | :-- |
| rsi_threshold | 45 | **40** | RSI 35-45 dominant across WFA windows |
| mfi_threshold | 45 | **45** | Stable, middle of WFA range |
| vix_threshold | 30 | **30** | VIX gate confirmed necessary (2022-H1) |
| adx_threshold | 20 | **10** | Consistently selected across all windows |
| go_threshold | 4 | **4** | WFA mode (5/8 windows use GO=4 or 5) |

Applied in: config YAML files + PineScript indicators.

## Backtester Architecture

The backtester uses vectorized signals + bar-by-bar simulation:
1. `backtester/signals.py` computes all 6 checks + gates as full time-series
2. `backtester/engine.py` simulates trade lifecycle: Entry at Close on GO → SL → TP1 (close 50%, move stop to BE) → Chandelier trailing on remaining 50%
3. CFD margin accounting: entry cost = notional / leverage (not full notional)

### Optimization
**Optuna Bayesian** (`tools/optimize.py`): TPE sampler with precomputed indicators (~10x faster). Works for both ITA (39 tickers) and US (33 sector-sample stocks). Two modes: single-period and Walk-Forward Analysis (8 rolling windows). Search space: MFI 35-60, RSI 35-60, ADX 10-30, GO 3-5. Converges in ~300 trials.

### Monte Carlo
**Monte Carlo** (`tools/montecarlo.py`): Shuffles trade order 10,000+ times to produce confidence intervals on equity, drawdown, and probability of ruin. Output: P5/P25/P50/P75/P95 percentiles, histogram plots.

## Automation (GitHub Actions)
- ITA: triggered at 8:30 CET Mon-Fri or via workflow_dispatch with `--tickers` override
- US: triggered at 13:15 CET Mon-Fri or via workflow_dispatch with `--tickers` override
- ETF: triggered at 14:00 CET Mon-Fri or via workflow_dispatch with tickers input
- Telegram notifications via TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID secrets
