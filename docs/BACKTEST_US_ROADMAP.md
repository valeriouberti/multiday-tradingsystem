# US S&P 500 CFD — Backtest Roadmap

> This document defines the backtesting plan for the US CFD strategy.
> Use it as a prompt for future implementation sessions.

---

## Strategy Summary

Same 6-check + 2-gate system as ITA CFD, applied to top 100 S&P 500 stocks by liquidity.

| Parameter | Value |
| :-- | :-- |
| Universe | ~100 S&P 500 stocks (config_us.yaml) |
| Benchmark | SPY |
| Capital | $1,000 |
| Leverage | 5:1 (Fineco ESMA CFD) |
| Hold period | 3-7 sessions |
| Checks | EMA D, EMA W, MACD, RSI > 40, MFI > 45, RS vs SPY |
| Gates | VIX < 30, ADX on SPY >= 10 |
| GO threshold | >= 4/6 |
| SL | Close - ATR(14) × 1.5 |
| TP1 | Close + ATR(14) × 1.5 (close 50%, move SL to BE) |
| Trailing | Chandelier: Highest(H,22) - ATR(14) × 3.0 |

---

## Phase 1: Single-Ticker Backtest

**Goal:** Verify the backtester engine works correctly on US stocks.

**Implementation:**
- Extend `backtest.py` to accept `--mode us` flag
- Reuse existing `backtester/` engine (signals, engine, metrics, plots)
- Test on 3-5 liquid tickers: AAPL, MSFT, JPM, XOM, UNH
- Period: 2020-01-01 to 2024-12-31
- Validate: trade count, win rate, equity curve shape, CFD margin accounting

**Command:**
```bash
python backtest.py --mode us --ticker AAPL --start 2020-01-01 --end 2024-12-31 --config config_us.yaml
```

---

## Phase 2: Sector-Sampled Backtest (33 stocks)

**Goal:** Validate strategy across US market without running all 100 tickers.

**Approach:** Pick 3 representative stocks per GICS sector (11 sectors × 3 = 33):

| Sector | Tickers |
| :-- | :-- |
| Technology | AAPL, MSFT, NVDA |
| Financials | JPM, GS, BLK |
| Health Care | UNH, LLY, JNJ |
| Consumer Disc. | TSLA, HD, AMZN |
| Industrials | GE, CAT, RTX |
| Energy | XOM, CVX, COP |
| Communication | NFLX, GOOGL, META |
| Consumer Staples | PG, KO, COST |
| Utilities | NEE, SO, DUK |
| Materials | LIN, FCX, SHW |
| Real Estate | PLD, AMT, EQIX |

**Implementation:**
- Use `optimize_optuna.py --mode us` for universe-level validation
- Aggregate metrics: avg return, win rate, profit factor, max DD, Sharpe
- Per-sector breakdown
- Output: `output/reports_us/backtest_sp500.csv`

**Command:**
```bash
python backtest_sp500.py
```

---

## Phase 3: Parameter Optimization (Grid Search)

**Goal:** Find optimal parameters for US market.

**Grid (same structure as ITA):**
```python
PARAM_GRID = {
    "vix_threshold": [20, 25, 30, 35, 999],    # 999 = disabled
    "mfi_threshold": [40, 45, 50, 55],
    "mfi_length":    [10, 14, 20],
    "rsi_threshold": [40, 45, 50, 55],
    "adx_threshold": [15, 20, 25],
    "go_threshold":  [4, 5],
}
```

**Key difference from ITA:** Add RSI=40 to the grid (US momentum may start earlier than Borsa Italiana).

**Status:** Superseded by Phase 5 (Optuna). Grid search replaced by Bayesian optimization.

**Implementation:** Use `optimize_optuna.py --mode us --trials 300`

---

## Phase 4: Walk-Forward Analysis

**Goal:** Validate parameter robustness out-of-sample.

**Windows (same structure as ITA):**
```
Window 1: Train 2019-01→2020-12 | Test 2021-H1
Window 2: Train 2019-07→2021-06 | Test 2021-H2
Window 3: Train 2020-01→2021-12 | Test 2022-H1
Window 4: Train 2020-07→2022-06 | Test 2022-H2
Window 5: Train 2021-01→2022-12 | Test 2023-H1
Window 6: Train 2021-07→2023-06 | Test 2023-H2
Window 7: Train 2022-01→2023-12 | Test 2024-H1
Window 8: Train 2022-07→2024-06 | Test 2024-H2
```

**Status:** Superseded by Phase 5 (Optuna WFA). Grid-based WFA replaced by Bayesian WFA.

**Implementation:** Use `optimize_optuna.py --mode us --wfa --trials 200`

---

## Phase 5: Optuna Optimization (**IMPLEMENTED** — `optimize_optuna.py`)

**Goal:** Replace brute-force grid search with Bayesian optimization.

**Status:** Implemented in `optimize_optuna.py` (unified script for both ITA and US).

**Commands:**
```bash
# Simple optimization (single-period 2020-2024)
python optimize_optuna.py --mode us --trials 300

# Walk-Forward Analysis with Optuna
python optimize_optuna.py --mode us --wfa --trials 200
```

**Features:**
- TPE sampler (Tree-structured Parzen Estimator)
- Wider search space than grid: MFI 35-60, RSI 35-60, ADX 10-30, GO 3-5
- Uses 33 sector-sample stocks for US (not all 100)
- Built-in pruning: skips unpromising combos early
- Parameter importance analysis
- WFA mode: 8 rolling windows with efficiency ratio and overfitting detection

**Output:** `output/optimization_us/optuna_results.csv` and `optuna_wfa_results.csv`

**Estimated runtime:** 33 × 300 trials × 8 windows = ~79,200 backtests (~45 min)

---

## Phase 6: Full Universe Validation

**Goal:** After tuning params on 33 stocks, validate on all 100.

**Implementation:**
- Run `backtest_sp500.py` with final tuned params on full 100-ticker universe
- Compare results vs sector sample to detect sector bias
- If results diverge significantly, re-tune on a larger sample

---

## Phase 7: Transaction Cost Sensitivity

**Goal:** Test strategy profitability with realistic Fineco CFD costs.

**Costs to model:**
- Spread: 0.05-0.15% on liquid US stocks (tighter than .MI)
- Overnight financing: ~5-6% annualized (depends on Fineco rate)
  - Per night: ~0.016% of notional
  - For 5-day avg hold: ~0.08% total
- Commission: check Fineco US CFD pricing

**Implementation:**
- Add `commission` and `overnight_rate` params to config_us.yaml
- Modify `backtester/engine.py` to deduct costs per trade
- Re-run Phase 6 with costs enabled

---

## Phase 8: Monte Carlo Simulation

**Goal:** Confidence intervals on strategy performance.

**Implementation:**
- Shuffle trade order 10,000 times
- Record final equity, max drawdown, win rate for each shuffle
- Output: 5th/50th/95th percentile for key metrics
- Probability of ruin (equity < 50% of initial)

---

## Comparison: ITA vs US

After completing all phases, produce a comparison table:

| Metric | ITA CFD (39 tickers) | US CFD (100 tickers) |
| :-- | :-- | :-- |
| Avg OOS return | ? | ? |
| Win rate | ? | ? |
| Profit factor | ? | ? |
| Sharpe ratio | ? | ? |
| Max drawdown | ? | ? |
| Best params | RSI=45,MFI=40,VIX=35,ADX=15,GO=3 | ? |
| WFA efficiency | ? | ? |

---

## Notes

- US stocks have higher liquidity → tighter spreads, less slippage
- US market hours (09:30-16:00 ET = 15:30-22:00 CET) → longer monitoring window
- Earnings season affects ~25% of S&P 500 per quarter → earnings gate is critical
- VIX threshold may need to be different (US vol regime differs from Italian)
- Consider adding a sector rotation layer: only trade sectors with positive RS vs SPY
