# Multiday Trading System — ITA CFD + US CFD + ETF Settoriali

Three swing trading strategies on **Fineco**, validated with Python technical screening
and AI-driven fundamental analysis (Perplexity Pro). Holding period: 3-7 sessions.

| Strategy | Instrument | Leverage | Capital | Benchmark |
| :-- | :-- | :-- | :-- | :-- |
| **ITA CFD** | CFD on FTSE MIB stocks | 5:1 ESMA | €1,000 | ETFMIB.MI |
| **US CFD** | CFD on S&P 500 stocks | 5:1 ESMA | $1,000 | SPY |
| **ETF Settoriali** | Cash ETF on Borsa Italiana | 1:1 | €4,000 | CSSPX.MI |

---

## Quick Start

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Optional: Telegram notifications
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."

# Daily validation
python main_ita.py                                    # ITA — all 39 FTSE MIB stocks
python main_ita.py --tickers "ISP.MI,UCG.MI,LDO.MI"  # ITA — specific tickers
python main_us.py                                     # US — top 100 S&P 500 stocks
python main_us.py --tickers "AAPL,MSFT,NVDA"          # US — specific tickers
python main_etf.py                                    # ETF — sector ETFs
```

---

## How It Works

### 6 Technical Checks (scored)

| # | Check | Timeframe | Logic |
| :-- | :-- | :-- | :-- |
| 1 | EMA 20 > EMA 50 | Daily | Uptrend direction |
| 2 | EMA 20 > EMA 50 | Weekly | Structural trend filter |
| 3 | MACD > Signal | Daily | Momentum confirmation |
| 4 | RSI > threshold | Daily | Momentum filter |
| 5 | MFI > threshold | Daily | Money Flow Index |
| 6 | RS vs Benchmark | Daily | Relative strength (20d lookback, 5d ROC) |

### Gates (non-scored, downgrade GO → WATCH)

| Gate | ITA | US | ETF |
| :-- | :-- | :-- | :-- |
| VIX < threshold | < 35 | < 30 | < 25 |
| ADX >= threshold on benchmark | >= 15 | >= 10 | >= 20 |
| Benchmark EMA health | — | — | yes |
| Pairwise correlation < 0.7 | — | — | yes |

### Scoring

| Strategy | GO | WATCH | SKIP |
| :-- | :-- | :-- | :-- |
| ITA CFD | >= 3/6 + gates OK | >= 2/6 or gate fail | <= 1/6 |
| US CFD | >= 4/6 + gates OK | >= 3/6 or gate fail | <= 2/6 |
| ETF | >= 5/6 + gates OK | >= 4/6 or gate fail | <= 3/6 |

### Position Management

| Level | Calculation | Action |
| :-- | :-- | :-- |
| Stop Loss | Close - ATR(14) × 1.5 | Set immediately after entry |
| TP1 | Close + ATR(14) × 1.5 | Close 50%, move stop to breakeven |
| Chandelier Exit | Highest(H,22) - ATR(14) × 3 | Trailing stop, update nightly |

---

## Backtesting & Optimization

```bash
# Single ticker backtest
python backtest.py --ticker ISP.MI --start 2023-01-01 --end 2024-12-31

# Optuna Bayesian optimization
python optimize_optuna.py --mode ita --trials 300          # ITA single-period
python optimize_optuna.py --mode us --trials 300           # US single-period
python optimize_optuna.py --mode ita --wfa --trials 200    # ITA Walk-Forward Analysis
python optimize_optuna.py --mode us --wfa --trials 200     # US Walk-Forward Analysis
```

**Optuna** uses TPE (Tree-structured Parzen Estimator) with precomputed indicators
(~10x faster than grid search). Walk-Forward Analysis validates parameter robustness
across 8 rolling windows (24-month train / 6-month test).

### Tuned Parameters

| Parameter | ITA | US | Source |
| :-- | :-- | :-- | :-- |
| RSI threshold | 45 | 40 | Optuna WFA |
| MFI threshold | 40 | 45 | Optuna WFA |
| VIX gate | 35 | 30 | Optuna WFA |
| ADX gate | 15 | 10 | Optuna WFA |
| GO threshold | 3 | 4 | Optuna WFA |

---

## Entry Methods (CFD only)

| Method | Window | Condition |
| :-- | :-- | :-- |
| GAP_UP | First 15 min | Gap >= 0.5% above EMA20 + prev day high |
| PULLBACK | After 15 min | Bounce on EMA20 Daily |
| ORB | After 15 min | Opening Range Breakout H1, volume >= 1.5x |
| BONE_ZONE | After 15 min | Dip into EMA 9-20 zone, green candle above EMA9 |

ETFs: buy at market in the afternoon (14:30-16:30 CET) if GO.

---

## TradingView (PineScript)

Two indicators for visual validation on H1 charts:

| Indicator | File | Params |
| :-- | :-- | :-- |
| ITA CFD v1.2 | `pinescript/ita_cfd_validator.pine` | RSI 45, MFI 40, VIX 35, ADX 15, GO >= 3 |
| US CFD v1.0 | `pinescript/us_cfd_validator.pine` | RSI 40, MFI 45, VIX 30, ADX 10, GO >= 4 |

Features: 6 checks + gates dashboard, SL/TP1/Chandelier levels on chart,
entry signal labels, configurable alerts.

---

## Telegram

Reports are sent automatically via Telegram after each execution (local or CI).
Zero extra dependencies (uses `urllib`).

**Setup:** Create bot via `@BotFather`, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
as env vars (local) or GitHub secrets (CI).

---

## Automation (GitHub Actions)

| Workflow | Schedule (CEST) | Trigger |
| :-- | :-- | :-- |
| ITA Validator | 08:30 Mon-Fri | Schedule + workflow_dispatch |
| US Validator | 13:15 Mon-Fri | Schedule + workflow_dispatch |
| ETF Validator | 14:00 Mon-Fri | Schedule + workflow_dispatch |

All workflows accept `--tickers` input for manual runs. Reports are saved as artifacts
and sent via Telegram.

---

## Project Structure

```
project/
├── main_ita.py             ← ITA CFD entry point (39 FTSE MIB stocks)
├── main_us.py              ← US CFD entry point (100 S&P 500 stocks)
├── main_etf.py             ← ETF entry point (sector ETFs)
├── config_ita.yaml         ← ITA config (tickers + tuned params)
├── config_us.yaml          ← US config (tickers + optimization sample)
├── config_etf.yaml         ← ETF config (tickers + params)
├── shared/
│   ├── data.py             ← yfinance data fetching with cache
│   ├── indicators.py       ← Common indicators (EMA, MACD, RSI, MFI, RS, gates)
│   ├── position_sizing.py  ← CFD + ETF position sizing
│   ├── report_utils.py     ← Shared Rich formatting helpers
│   └── telegram.py         ← Telegram notifications
├── validator_ita/
│   ├── scorer.py           ← 6 checks + 2 gates scorer
│   └── report.py           ← Rich table + CSV (EUR, Fineco CFD)
├── validator_us/
│   ├── scorer.py           ← 6 checks + 2 gates scorer
│   └── report.py           ← Rich table + CSV (USD, Fineco CFD)
├── validator_etf/
│   ├── indicators.py       ← ETF-specific: bench health + correlations
│   ├── scorer.py           ← 6 checks + 4 gates scorer
│   └── report.py           ← Rich table + CSV (EUR, Fineco cash)
├── backtester/
│   ├── data.py             ← Historical data fetching with warmup
│   ├── signals.py          ← Vectorized signal generation
│   ├── engine.py           ← Bar-by-bar simulation (SL/TP1/Chandelier)
│   ├── metrics.py          ← Performance analytics (Sharpe, Sortino, Calmar)
│   └── plots.py            ← Equity curve + trade markers
├── backtest.py             ← CLI: single-ticker backtest
├── optimize_optuna.py      ← Optuna Bayesian optimization (ITA + US)
├── scripts/
│   └── update_tickers.py   ← CI helper: update tickers in YAML
├── .github/workflows/
│   ├── ita-validator.yml   ← 08:30 CEST Mon-Fri
│   ├── us-validator.yml    ← 13:15 CEST Mon-Fri
│   └── etf-validator.yml   ← 14:00 CEST Mon-Fri
├── docs/
│   ├── STRATEGY.md         ← Strategy overview + shared rules
│   ├── STRATEGY_ITA.md     ← ITA prompts, params, tickers
│   ├── STRATEGY_US.md      ← US prompts, params, universe
│   ├── STRATEGY_ETF.md     ← ETF prompts, gates, ETF list
│   └── BACKTEST_US_ROADMAP.md
├── pinescript/
│   ├── ita_cfd_validator.pine  ← TradingView ITA (v1.2)
│   └── us_cfd_validator.pine   ← TradingView US (v1.0)
└── output/
    ├── reports_ita/        ← Daily CSV reports (ITA)
    ├── reports_us/         ← Daily CSV reports (US)
    ├── reports_etf/        ← Daily CSV reports (ETF)
    ├── optimization_ita/   ← Optuna results (ITA)
    └── optimization_us/    ← Optuna results (US)
```

---

## Dependencies

```
yfinance>=0.2.40
pandas-ta>=0.3.14b
pandas>=2.0
pyyaml>=6.0
rich>=13.0
matplotlib>=3.7
python-dotenv==1.0.1
optuna>=3.0
```

---

## Documentation

- [Strategy Overview](docs/STRATEGY.md) — Daily workflow, technical details, operative rules
- [ITA CFD Strategy](docs/STRATEGY_ITA.md) — Perplexity prompts, tuned params, ticker reference
- [US CFD Strategy](docs/STRATEGY_US.md) — US prompts, tuned params, S&P 500 universe
- [ETF Strategy](docs/STRATEGY_ETF.md) — Sector rotation prompts, ETF list
- [US Backtest Roadmap](docs/BACKTEST_US_ROADMAP.md) — US backtesting phases
