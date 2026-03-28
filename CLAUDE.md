# Multiday Trading Validator — Project Guide

## Project Purpose
Python tool that validates Italian stock tickers and sector ETFs (selected via AI
sector catalyst prompt on Perplexity) against technical indicators before entry.
Two strategies: ITA CFD (Borsa Italiana stocks via Fineco CFD) and ETF (sector ETFs
on Borsa Italiana, cash). Designed for multiday swing trading (3-7 sessions).

## Architecture
```
project/
├── CLAUDE.md               ← This file
├── config_ita.yaml         ← Italian stocks config (all 40 FTSE MIB, tuned params)
├── config_etf.yaml         ← Sector ETFs config (edit daily)
├── main_ita.py             ← Entry point: ITA CFD strategy (--tickers override)
├── main_etf.py             ← Entry point: ETF strategy
├── shared/
│   ├── __init__.py
│   ├── data.py             ← yfinance data fetching (shared)
│   └── indicators.py       ← Common indicators (EMA, MACD, RSI, MFI, RS, gates, entry helpers)
├── validator_ita/
│   ├── __init__.py
│   ├── indicators.py       ← ITA-specific: position sizing with leverage
│   ├── scorer.py           ← 6 checks + 2 gates scorer
│   └── report.py           ← Rich table + CSV (EUR, Fineco CFD format)
├── validator_etf/
│   ├── __init__.py
│   ├── indicators.py       ← ETF-specific: position sizing (no leverage), bench health, correlations
│   ├── scorer.py           ← 6 checks + 4 gates scorer
│   └── report.py           ← Rich table + CSV (EUR, Fineco cash format)
├── backtester/             ← Backtesting engine
│   ├── __init__.py
│   ├── data.py             ← Historical data fetching with warmup buffer
│   ├── signals.py          ← Vectorized signal generation (full time-series)
│   ├── engine.py           ← Bar-by-bar simulation (SL/TP1/Chandelier lifecycle)
│   ├── metrics.py          ← Performance analytics (Sharpe, Sortino, Calmar, drawdown)
│   └── plots.py            ← Equity curve + trade markers (matplotlib)
├── main_us.py              ← Entry point: US S&P 500 CFD strategy (--tickers override)
├── config_us.yaml          ← US stocks config (top 100 S&P 500 by liquidity)
├── validator_us/
│   ├── __init__.py
│   ├── indicators.py       ← US-specific: position sizing with leverage (USD)
│   ├── scorer.py           ← 6 checks + 2 gates scorer (benchmark: SPY)
│   └── report.py           ← Rich table + CSV (USD, Fineco CFD format)
├── backtest.py             ← CLI: single-ticker backtest (--mode, --ticker, --start, --end)
├── backtest_ftsemib.py     ← Full FTSE MIB universe backtest with aggregate report
├── optimize_params.py      ← In-sample grid search (1080 combos on 2020-2024)
├── walk_forward.py         ← Walk-Forward Analysis (8 windows, OOS validation)
├── scripts/
│   └── update_tickers.py   ← CI helper to update tickers in YAML
├── .github/workflows/
│   ├── ita-validator.yml   ← GitHub Actions: runs at 8:30 CET + workflow_dispatch
│   └── etf-validator.yml   ← GitHub Actions: runs at 14:00 CET + workflow_dispatch
├── output/
│   ├── reports_ita/        ← Daily CSV reports (ITA)
│   ├── reports_etf/        ← Daily CSV reports (ETF)
│   ├── optimization/       ← Grid search results CSV
│   └── walk_forward/       ← Walk-forward analysis results CSV
├── docs/
├── pinescript/             ← TradingView indicator (v1.1, tuned params)
└── requirements.txt
```

## Config Files
- `config_ita.yaml`: All 40 FTSE MIB stocks (.MI suffix), benchmark ETFMIB.MI, leverage 5:1, tuned params
- `config_etf.yaml`: 3 sector ETFs (.MI suffix), benchmark CSSPX.MI, no leverage
- ITA tickers override via `--tickers` CLI flag (no need to edit YAML for daily use)

## Technical Indicators Used
All computed via pandas-ta library on DAILY timeframe:
1. EMA 20 > EMA 50 Daily     → Trend direction
2. EMA 20 > EMA 50 Weekly    → Structural trend filter
3. MACD > Signal Line        → Momentum confirmation (12/26/9)
4. RSI > 45                  → Momentum filter (length 14, tuned from 50)
5. MFI > 45                  → Money Flow Index (length 14, tuned from 50)
6. RS Line vs Benchmark      → Relative strength (20d lookback, 5d ROC)

Entry timing helpers:
- ATR(14) Daily              → Stop loss + TP1 + Chandelier Exit
- EMA 9 Daily                → Bone Zone entry detection
- Opening Range              → ORB breakout via H1 data (ITA only)

## Gates (not scored, downgrade GO to WATCH)
**ITA (2 gates):** VIX < 35 (tuned from 25), ADX on ETFMIB.MI >= 20
**ETF (4 gates):** VIX < 25, Benchmark EMA health, ADX >= 20, Correlation < 0.7

## Scoring Logic
6 checks, max score 6/6:
- Score >= 4/6 → GO (tuned from 5)
- Score == 3/6 → WATCH (tuned from 4)
- Score <= 2/6 → SKIP

## Key Rules (never change these in code)
- All trend/momentum checks use DAILY timeframe
- H1 data used ONLY for ORB detection (ITA)
- RS Line compares ticker vs its benchmark (ETFMIB.MI or CSSPX.MI)
- MFI used instead of OBV (more reliable on Borsa Italiana)
- prepost=True always (premarket data included)
- auto_adjust=True always (split/dividend adjusted)
- Never hardcode tickers or parameters in .py files

## Dependencies
- yfinance >= 0.2.40
- pandas-ta >= 0.3.14b
- pandas >= 2.0
- pyyaml >= 6.0
- rich >= 13.0
- matplotlib >= 3.7
- python-dotenv == 1.0.1

## Running

### Daily Validation
```bash
python main_ita.py                                    # All 40 FTSE MIB stocks
python main_ita.py --tickers "ISP.MI,UCG.MI,LDO.MI"  # Override with specific tickers
python main_us.py                                     # Top 100 S&P 500 stocks
python main_us.py --tickers "AAPL,MSFT,NVDA"         # Override with specific tickers
python main_etf.py                                    # Sector ETFs
```

### Backtesting
```bash
python backtest.py --ticker ISP.MI --start 2023-01-01 --end 2024-12-31   # Single ticker
python backtest_ftsemib.py                                                # Full FTSE MIB universe
```

### Parameter Optimization
```bash
python optimize_params.py     # In-sample grid search (1080 combos, 2020-2024)
python walk_forward.py        # Walk-Forward Analysis (8 windows, OOS validation)
```

## Tuned Parameters (ITA, optimized on 2020-2024)

| Parameter | Original | Tuned | Rationale |
| :-- | :-- | :-- | :-- |
| rsi_threshold | 50 | **45** | Catches early-trend entries |
| mfi_threshold | 50 | **45** | Less restrictive money flow filter |
| vix_threshold | 25 | **35** | Old gate too strict, blocked good trades in moderate fear |
| go_threshold | 5 | **4** | 5th check often lagged 1-2 days, causing missed entries |

These params are applied in: `config_ita.yaml`, `pinescript/ita_cfd_validator.pine` (v1.1).

## Backtester Architecture

The backtester uses vectorized signals + bar-by-bar simulation:
1. `backtester/signals.py` computes all 6 checks + gates as full time-series (not point-in-time)
2. `backtester/engine.py` simulates trade lifecycle: Entry at Close on GO → SL → TP1 (close 50%, move stop to BE) → Chandelier trailing on remaining 50%
3. CFD margin accounting: entry cost = notional / leverage (not full notional)

### Optimization Pipeline
1. **Grid Search** (`optimize_params.py`): tests 1080 parameter combos on 2020-2024 in-sample
2. **Walk-Forward Analysis** (`walk_forward.py`): 8 rolling windows (24m train / 6m test), optimizes per window, reports only OOS performance. Key output: efficiency ratio (OOS/IS return) and parameter stability across windows

## Automation (GitHub Actions)
- ITA: triggered at 8:30 CET or via GitHub mobile app with `--tickers` override
- ETF: triggered at 14:00 CET or via GitHub mobile app with tickers input
- Optional Telegram notifications (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID secrets)
