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
├── optimize_optuna.py      ← Optuna Bayesian optimization (ITA + US, simple + WFA)
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
5. MFI > 40                  → Money Flow Index (length 14, tuned from 50→45→40)
6. RS Line vs Benchmark      → Relative strength (20d lookback, 5d ROC)

Entry timing helpers:
- ATR(14) Daily              → Stop loss + TP1 + Chandelier Exit
- EMA 9 Daily                → Bone Zone entry detection
- Opening Range              → ORB breakout via H1 data (ITA only)

## Gates (not scored, downgrade GO to WATCH)
**ITA (2 gates):** VIX < 35 (tuned from 25), ADX on ETFMIB.MI >= 15 (tuned from 20)
**ETF (4 gates):** VIX < 25, Benchmark EMA health, ADX >= 20, Correlation < 0.7

## Scoring Logic
6 checks, max score 6/6:
- Score >= 3/6 → GO (tuned from 5→4→3 via Optuna WFA)
- Score == 2/6 → WATCH
- Score <= 1/6 → SKIP

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
- optuna >= 3.0

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

# Optuna Bayesian optimization (faster, works for both ITA and US)
python optimize_optuna.py --mode ita --trials 300          # ITA single-period
python optimize_optuna.py --mode us --trials 300           # US single-period
python optimize_optuna.py --mode ita --wfa --trials 200    # ITA Walk-Forward
python optimize_optuna.py --mode us --wfa --trials 200     # US Walk-Forward (33 sector-sample stocks)
```

## Tuned Parameters (ITA, optimized on 2020-2024)

| Parameter | Original | Tuned | Rationale |
| :-- | :-- | :-- | :-- |
| rsi_threshold | 50 | **45** | Catches early-trend entries |
| mfi_threshold | 50 | **40** | Less restrictive money flow filter (45→40 via Optuna WFA) |
| vix_threshold | 25 | **35** | Old gate too strict, blocked good trades in moderate fear |
| adx_threshold | 20 | **15** | Mild loosening, still filters flat markets (Optuna WFA) |
| go_threshold | 5 | **3** | Perfectly stable across all 8 WFA windows (5→4→3) |

These params are applied in: `config_ita.yaml`, `pinescript/ita_cfd_validator.pine` (v1.2).

## Backtester Architecture

The backtester uses vectorized signals + bar-by-bar simulation:
1. `backtester/signals.py` computes all 6 checks + gates as full time-series (not point-in-time)
2. `backtester/engine.py` simulates trade lifecycle: Entry at Close on GO → SL → TP1 (close 50%, move stop to BE) → Chandelier trailing on remaining 50%
3. CFD margin accounting: entry cost = notional / leverage (not full notional)

### Optimization Pipeline
1. **Grid Search** (`optimize_params.py`): tests 1080 parameter combos on 2020-2024 in-sample
2. **Walk-Forward Analysis** (`walk_forward.py`): 8 rolling windows (24m train / 6m test), optimizes per window, reports only OOS performance. Key output: efficiency ratio (OOS/IS return) and parameter stability across windows
3. **Optuna Bayesian** (`optimize_optuna.py`): TPE sampler replaces brute-force grid. Works for both ITA (39 tickers) and US (33 sector-sample stocks). Two modes: single-period optimization and Walk-Forward Analysis. Wider search space (MFI 35-60, RSI 35-60, ADX 10-30, GO 3-5). Converges in ~300 trials vs 1,080 combos. Includes parameter importance analysis

## Automation (GitHub Actions)
- ITA: triggered at 8:30 CET or via GitHub mobile app with `--tickers` override
- ETF: triggered at 14:00 CET or via GitHub mobile app with tickers input
- Optional Telegram notifications (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID secrets)
