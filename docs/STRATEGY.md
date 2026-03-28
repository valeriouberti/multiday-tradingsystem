# Multiday Trading System — Overview

> Tre strategie via **broker**. Selezione titoli automatica (screening tecnico Python)
> + validazione fondamentale via AI (Perplexity Pro).
> Holding period: 3-7 sessioni.
>
> | Strategia | Strumento | Leva | Capitale | Benchmark |
> | :-- | :-- | :-- | :-- | :-- |
> | **ITA CFD** | CFD su azioni FTSE MIB | 5:1 ESMA | €1.000 | ETFMIB.MI |
> | **US CFD** | CFD su azioni S&P 500 | 5:1 ESMA | $1.000 | SPY |
> | **ETF Settoriali** | Cash ETF Borsa Italiana | 1:1 | €4.000 | CSSPX.MI |
> | **Totale** | | | **~€6.000** | |

**Dettaglio per strategia:**
- [ITA CFD — Prompts & Parameters](STRATEGY_ITA.md)
- [US S&P 500 CFD — Prompts & Parameters](STRATEGY_US.md)
- [ETF Settoriali — Prompts & Parameters](STRATEGY_ETF.md)

---

## Workflow Giornaliero

| Ora CET | Strategia | Azione | Durata |
| :-- | :-- | :-- | :-- |
| **07:30** | Tutte | Macro veto (EU + US) | 2 min |
| **07:30** | ETF | Prompt 0 — overnight check | 3 min |
| **08:00** | ITA CFD | Prompt 1 — market context ITA (Perplexity) | 3 min |
| **08:30** | ITA CFD | `python main_ita.py` → report + Prompt 2 auto | 2 min |
| **08:35** | ITA CFD | Copia Prompt 2 da Telegram su Perplexity → deep dive | 3 min |
| **09:00** | ITA CFD | Entry su broker (GAP_UP/PB/ORB/BZ) | 5 min |
| **13:00** | US CFD | Prompt 1 — market context US (Perplexity) | 3 min |
| **13:15** | US CFD | `python main_us.py` → report + Prompt 2 auto | 3 min |
| **13:20** | US CFD | Copia Prompt 2 da Telegram su Perplexity → deep dive | 3 min |
| **13:30** | ETF | Prompt 1 + 2 (schedulati, pausa pranzo) | 8 min |
| **13:45** | ETF | `python main_etf.py` + aggiorna config | 2 min |
| **14:30-16:30** | ETF | Entry su broker (buy a mercato) | 5 min |
| **15:30** | US CFD | Entry su broker (GAP_UP/PB/ORB/BZ) | 5 min |
| **17:00** | ITA CFD | Deadline ITA — no entry dopo | 0 min |
| **20:00** | US CFD | Deadline US — no new entry | 0 min |
| **22:00** | Tutte | Prompt 3 — exit review + aggiorna Trail | 10 min |

**Tempo totale: ~50 minuti/giorno** (3 strategie)

### 07:30 — Macro Veto (2 min)

Controlla [Investing.com](https://investing.com/economic-calendar).

**STOP se presente:**

| Macro EU | Macro USA |
| :-- | :-- |
| ECB (tassi o conferenza) | FOMC (decisione o minutes) |
| EU CPI / HICP | CPI USA |
| PMI Eurozona | NFP (1° venerdi mese) |
| Asta BTP / rating Italia | PPI |

### 22:00 — Prompt 3: Exit Review (tutte le strategie)

```
Ho posizioni aperte su Borsa Italiana:

AZIONI ITA (CFD broker):
[lista ticker.MI attivi con data entry e P&L %]

US S&P 500 (CFD broker):
[lista ticker attivi con data entry e P&L %]

ETF SETTORIALI (cash broker):
[lista ticker.MI attivi con data entry e P&L %]

Cerca notizie nelle ultime 8 ore che possano invalidare i catalyst.

Per OGNI posizione rispondi:
1. Catalyst originale ancora valido? SI / NO / IN INDEBOLIMENTO
2. RS vs benchmark: migliorata o peggiorata?
3. Nuovi rischi nelle prossime 48 ore?
4. Raccomandazione: MANTENERE / RIDURRE / CHIUDERE

Per le azioni ITA: Spread BTP-Bund in allargamento o restringimento?
Per US: 10Y yield direction?
Per gli ETF: EUR/USD ha aiutato o danneggiato il rendimento?

Sii conciso. Un paragrafo per posizione.
```

---

## Dettaglio Tecnico (comune a tutte)

### 6 Check scored

| # | Check | Timeframe | Logica |
| :-- | :-- | :-- | :-- |
| 1 | EMA 20 > EMA 50 | Daily | Trend rialzista |
| 2 | EMA 20 > EMA 50 | Weekly | Trend strutturale |
| 3 | MACD > Signal | Daily | Momentum in accelerazione |
| 4 | RSI > threshold | Daily | Forza relativa positiva |
| 5 | MFI > threshold | Daily | Money Flow Index — flusso istituzionale |
| 6 | RS vs Benchmark | Daily | Batte il benchmark (20d, 5d ROC) |

### Gates

| Gate | ITA CFD | US CFD | ETF | Effetto |
| :-- | :-- | :-- | :-- | :-- |
| VIX < threshold | < 35 | < 30 | < 25 | GO → WATCH |
| ADX >= threshold su benchmark | >= 15 | >= 10 | >= 20 | GO → WATCH |
| Benchmark Health (EMA20 > EMA50) | — | — | yes | GO → WATCH |
| Correlazione pairwise < 0.7 | — | — | yes | Dimezza size |

### Gestione Posizione

| Livello | Calcolo | Azione |
| :-- | :-- | :-- |
| Stop Loss | Close - ATR(14) × 1.5 | Inserire subito dopo entry |
| TP1 | Close + ATR(14) × 1.5 | Chiudi 50%, sposta stop a breakeven |
| Chandelier | Highest(H,22) - ATR(14) × 3 | Trailing stop, aggiornare ogni sera |

### Position Sizing (ITA / US CFD, con leva 5:1)

```
shares = min(
    (capital × 2%) / (ATR × 1.5),             # risk-based
    (capital × 40% × 5) / prezzo              # margin cap
)
```

---

## Regole Operative Fisse

1. **Macro Veto**: FOMC / CPI / NFP / ECB / EU CPI → nessun trade
2. **Gates**: gate fallito degrada GO → WATCH (lo script lo fa automaticamente)
3. **No entry dopo deadline**: ITA 17:00, US 20:00, ETF 16:30 CET
4. **Stop Loss immediato**: inserire nel broker appena si entra
5. **Chandelier Exit**: se close < Chandelier stop → EXIT
6. **Weekend**: chiudere o ridurre 50% — CFD ha costo overnight (~0.05%/giorno)
7. **Earnings**: mai tenere CFD aperto la notte prima degli earnings
8. **Score minimo**: ITA >= 3/6, US >= 4/6, ETF >= 5/6
9. **Position sizing**: usare il numero di shares dello script, mai superare
10. **BTP-Bund spread** (ITA): widening >10bp in un giorno → chiudere bancari
11. **EUR/USD** (ETF): EUR in rafforzamento erode rendimenti ETF con sottostante USD
12. **Max posizioni**: ITA max 3 CFD, US max 3 CFD, ETF max 3 posizioni
13. **Correlazione** (ETF): se pairwise > 0.7, dimezzare il size combinato
14. **US overnight**: CFD US ha costo overnight simile a ITA (~0.05%/giorno)
15. **US earnings season**: ~25% S&P 500 riporta per trimestre — earnings gate critico
16. **10Y yield** (US): move >5bp impatta bancari, REIT, utilities

---

## Telegram

Il report viene inviato automaticamente su Telegram dopo ogni esecuzione.
Nessuna dipendenza aggiuntiva (usa urllib).

### Setup (2 min)

1. Telegram → `@BotFather` → `/newbot` → copia il **token**
2. Invia un messaggio qualsiasi al tuo bot
3. Apri: `https://api.telegram.org/bot<TOKEN>/getUpdates` → copia `chat_id`

**Locale:**
```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_CHAT_ID="987654321"
```

**GitHub Actions:** aggiungi come secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

---

## Backtester

### Componenti

| Script | Descrizione |
| :-- | :-- |
| `backtest.py` | Backtest singolo ticker (`--ticker ISP.MI --start 2023-01-01`) |
| `optimize_optuna.py` | Optuna Bayesian optimization (ITA + US, simple + WFA) |
| `montecarlo.py` | Monte Carlo simulation (trade-order shuffling, confidence intervals) |

### Trade Lifecycle

```
GO signal → Entry at Close
  → Stop Loss: Close - ATR(14) × 1.5
  → TP1: Close + ATR(14) × 1.5
     Se TP1 raggiunto: chiudi 50%, sposta stop a breakeven
  → Chandelier Trailing: Highest(H,22) - ATR(14) × 3.0
     Ratchet up only (non scende mai)
  → Exit: stop hit, oppure fine dati
```

### Optuna Optimization

Usa il **TPE sampler** (Tree-structured Parzen Estimator) per convergere in ~300 trial.
Indicatori precomputati una volta sola per ticker (~10x piu veloce del grid search).

**Due modalita:**

```bash
python optimize_optuna.py --mode ita --trials 300          # ITA single-period
python optimize_optuna.py --mode us --trials 300           # US single-period
python optimize_optuna.py --mode ita --wfa --trials 200    # ITA Walk-Forward
python optimize_optuna.py --mode us --wfa --trials 200     # US Walk-Forward
```

**Spazio di ricerca:**
```
vix_threshold: [20, 25, 30, 35, 999]
mfi_threshold: 35-60 (step 5)
mfi_length:    [10, 14, 20]
rsi_threshold: 35-60 (step 5)
adx_threshold: 10-30 (step 5)
go_threshold:  3-5
```

---

### Monte Carlo Simulation (`montecarlo.py`)

Shuffla l'ordine dei trade N volte per produrre intervalli di confidenza su equity,
drawdown, e probabilita di ruin. Output: percentili (P5/P25/P50/P75/P95), probabilita
di profitto/ruin, istogrammi.

```bash
python montecarlo.py --mode ita --simulations 10000              # ITA
python montecarlo.py --mode us --simulations 10000 --save-plot   # US + grafici
```

---

## Prossimi Step

1. **Parameter Sensitivity Heatmap** — Validazione robustezza dei parametri
2. **Regime-Aware Testing** — Test per regime di mercato (bull/bear/range)
3. **Transaction Cost Sensitivity** — Spread bid-ask, overnight, slippage
4. **ETF Parameter Tuning** — Optuna WFA per strategia ETF
