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
├── config_ita.yaml         ← Italian stocks config (edit daily)
├── config_etf.yaml         ← Sector ETFs config (edit daily)
├── main_ita.py             ← Entry point: ITA CFD strategy
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
├── scripts/
│   └── update_tickers.py   ← CI helper to update tickers in YAML
├── .github/workflows/
│   ├── ita-validator.yml   ← GitHub Actions: runs at 8:30 CET + workflow_dispatch
│   └── etf-validator.yml   ← GitHub Actions: runs at 14:00 CET + workflow_dispatch
├── output/
│   ├── reports_ita/        ← Daily CSV reports (ITA)
│   └── reports_etf/        ← Daily CSV reports (ETF)
├── docs/
├── pinescript/
└── requirements.txt
```

## Config Files
Edit daily before market open:
- `config_ita.yaml`: 3 Italian stocks (.MI suffix), benchmark ETFMIB.MI, leverage 5:1
- `config_etf.yaml`: 3 sector ETFs (.MI suffix), benchmark CSSPX.MI, no leverage

## Technical Indicators Used
All computed via pandas-ta library on DAILY timeframe:
1. EMA 20 > EMA 50 Daily     → Trend direction
2. EMA 20 > EMA 50 Weekly    → Structural trend filter
3. MACD > Signal Line        → Momentum confirmation (12/26/9)
4. RSI > 50                  → Momentum filter (length 14)
5. MFI > 50                  → Money Flow Index (replaces OBV)
6. RS Line vs Benchmark      → Relative strength (20d lookback, 5d ROC)

Entry timing helpers:
- ATR(14) Daily              → Stop loss + TP1 + Chandelier Exit
- EMA 9 Daily                → Bone Zone entry detection
- Opening Range              → ORB breakout via H1 data (ITA only)

## Gates (not scored, downgrade GO to WATCH)
**ITA (2 gates):** VIX < 25, ADX on ETFMIB.MI >= 20
**ETF (4 gates):** VIX < 25, Benchmark EMA health, ADX >= 20, Correlation < 0.7

## Scoring Logic
6 checks, max score 6/6:
- Score >= 5/6 → GO
- Score == 4/6 → WATCH
- Score <= 3/6 → SKIP

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

## Running
```bash
python main_ita.py                          # ITA stocks (default: config_ita.yaml)
python main_etf.py                          # Sector ETFs (default: config_etf.yaml)
python main_ita.py --config custom.yaml     # custom config
```

## Automation (GitHub Actions)
- ITA: triggered at 8:30 CET or via GitHub mobile app with tickers input
- ETF: triggered at 14:00 CET or via GitHub mobile app with tickers input
- Optional Telegram notifications (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID secrets)
