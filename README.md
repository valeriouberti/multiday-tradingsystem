# Multiday Trading System — ITA CFD + ETF Settoriali

Due strategie su **Borsa Italiana** via **Fineco**. Selezione titoli via AI
(Perplexity Pro, prompt schedulati). Validazione tecnica con Python.
Holding period: 3-7 sessioni.

| Strategia | Strumento | Leva | Capitale | Benchmark |
| :-- | :-- | :-- | :-- | :-- |
| **ITA CFD** | CFD azioni FTSE MIB | 5:1 ESMA | €1.000 | ETFMIB.MI |
| **ETF Settoriali** | Cash ETF Borsa Italiana | 1:1 | €4.000 | CSSPX.MI |

---

## Struttura del Repo

```
project/
├── main_ita.py             ← Entry point: ITA CFD
├── main_etf.py             ← Entry point: ETF settoriali
├── config_ita.yaml         ← Ticker italiani + parametri (edit giornaliero)
├── config_etf.yaml         ← ETF settoriali + parametri (edit giornaliero)
├── shared/
│   ├── data.py             ← yfinance data fetching
│   ├── indicators.py       ← Indicatori comuni (EMA, MACD, RSI, MFI, RS, gates)
│   └── telegram.py         ← Notifiche Telegram
├── validator_ita/
│   ├── indicators.py       ← Position sizing con leva
│   ├── scorer.py           ← 6 check + 2 gates
│   └── report.py           ← Report Fineco CFD (EUR)
├── validator_etf/
│   ├── indicators.py       ← Position sizing cash + bench health + correlazione
│   ├── scorer.py           ← 6 check + 4 gates
│   └── report.py           ← Report Fineco ETF (EUR)
├── scripts/
│   └── update_tickers.py   ← Helper CI per aggiornare config YAML
├── .github/workflows/
│   ├── ita-validator.yml   ← GitHub Actions: 8:30 CET + workflow_dispatch
│   └── etf-validator.yml   ← GitHub Actions: 14:00 CET + workflow_dispatch
├── docs/
│   └── STRATEGY.md         ← Strategia completa + prompt Perplexity
├── pinescript/
│   └── ita_cfd_validator.pine  ← Indicatore TradingView (H1)
└── output/
    ├── reports_ita/        ← CSV giornalieri ITA
    └── reports_etf/        ← CSV giornalieri ETF
```

---

## Workflow Giornaliero

| Ora CET | Strategia | Azione |
| :-- | :-- | :-- |
| **07:30** | Entrambe | Macro veto (Investing.com) |
| **07:30** | ETF | Prompt 0 — overnight check settori di ieri |
| **08:00** | ITA CFD | Prompt 1 + 2 (schedulati Perplexity) |
| **08:30** | ITA CFD | `python main_ita.py` → scorecard + livelli Fineco |
| **09:00** | ITA CFD | Entry su Fineco (GAP_UP / PULLBACK / ORB / BONE_ZONE) |
| **13:00** | ETF | Prompt 1 + 2 (schedulati, pausa pranzo) |
| **13:20** | ETF | `python main_etf.py` → scorecard + livelli Fineco |
| **14:30-16:30** | ETF | Entry su Fineco (buy a mercato) |
| **17:00** | Entrambe | Deadline — no entry dopo |
| **22:00** | Entrambe | Prompt 3 — exit review + aggiorna Chandelier Stop |

Tempo totale: ~40 minuti/giorno. Dettaglio prompt in [docs/STRATEGY.md](docs/STRATEGY.md).

---

## Indicatori Tecnici

**6 check scored (comuni a entrambe):**

| # | Check | Timeframe | Logica |
| :-- | :-- | :-- | :-- |
| 1 | EMA 20 > EMA 50 | Daily | Trend rialzista |
| 2 | EMA 20 > EMA 50 | Weekly | Trend strutturale |
| 3 | MACD > Signal | Daily | Momentum in accelerazione |
| 4 | RSI > 50 | Daily | Forza relativa positiva |
| 5 | MFI > 50 | Daily | Money Flow Index |
| 6 | RS vs Benchmark | Daily | Batte il benchmark (20d, 5d ROC) |

**Gates (non scored, degradano GO → WATCH):**

| Gate | ITA | ETF |
| :-- | :-- | :-- |
| VIX < 25 | ✅ | ✅ |
| ADX >= 20 su benchmark | ✅ | ✅ |
| Benchmark EMA20 > EMA50 | — | ✅ |
| Correlazione pairwise < 0.7 | — | ✅ |

**Score:**
- 5-6/6 + gates OK → **GO**
- 5-6/6 + gate fallito → **WATCH**
- 4/6 → **WATCH**
- ≤ 3/6 → **SKIP**

---

## Gestione Posizione

| Livello | Calcolo | Azione |
| :-- | :-- | :-- |
| Stop Loss | Close - ATR(14) × 1.5 | Inserire subito dopo entry |
| TP1 | Close + ATR(14) × 1.5 | Chiudi 50%, sposta stop a breakeven |
| Chandelier Exit | Highest(H,22) - ATR(14) × 3 | Trailing stop, aggiornare ogni sera |

---

## Entry Methods (ITA CFD)

| Metodo | Finestra | Condizione |
| :-- | :-- | :-- |
| GAP_UP | 09:00-09:15 | Gap >= 0.5% sopra EMA20 + max giorno precedente |
| PULLBACK | 09:15+ | Rimbalzo su EMA20 Daily |
| ORB | 09:15+ | Breakout Opening Range H1, volume >= 1.5x |
| BONE_ZONE | 09:15+ | Dip in zona EMA 9-20, candela verde sopra EMA9 |

Per gli ETF: senza dati real-time, si compra **a mercato nel pomeriggio** (14:30-16:30 CET) se GO.

---

## Telegram

Il report viene inviato automaticamente su Telegram dopo ogni esecuzione
(locale o CI). Zero dipendenze aggiuntive (usa `urllib`).

**Setup (2 min):**
1. Telegram → `@BotFather` → `/newbot` → copia il token
2. Invia un messaggio al bot
3. Apri `https://api.telegram.org/bot<TOKEN>/getUpdates` → copia `chat_id`
4. Aggiungi al tuo shell:
```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_CHAT_ID="987654321"
```

Per GitHub Actions: aggiungi come secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).

Se non configurato, nessun errore — il report viene solo stampato a terminale.

---

## Automazione (GitHub Actions)

| Workflow | Cron | Trigger manuale |
| :-- | :-- | :-- |
| ITA Validator | 8:30 CEST (Mon-Fri) | GitHub app → Actions → Run workflow |
| ETF Validator | 14:00 CEST (Mon-Fri) | GitHub app → Actions → Run workflow |

Inserisci i tickers nel campo input (es. `STLAM.MI,FCT.MI,ENI.MI`). Il workflow
aggiorna il config, esegue lo script, salva il CSV come artifact, e invia il
report su Telegram.

Gratuito: 2000 min/mese su repo privato, illimitato su pubblico.

---

## TradingView

Indicatore PineScript per validazione visiva su grafico **H1**:

```
pinescript/ita_cfd_validator.pine
```

- 6 check scored + 2 gates nella dashboard
- Livelli Stop / TP1 / Chandelier sul grafico
- Segnali entry (GAP_UP, BONE_ZONE, PULLBACK, ORB) con label
- Alert configurabili per GO/WATCH/Chandelier Exit
- Background verde (GO) / arancione (WATCH)

Setup: apri `MIL:UCG` (ITA) o `MIL:DFND` (ETF) → Pine Editor → Add to Chart.

---

## Quick Start

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Opzionale: Telegram
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."

# Esegui
python main_ita.py    # ITA CFD
python main_etf.py    # ETF settoriali
```

---

## Regole Operative Fisse

1. **Macro Veto**: FOMC / CPI / NFP / ECB / EU CPI → nessun trade
2. **Gates**: gate fallito degrada GO → WATCH automaticamente
3. **No entry dopo le 17:00 CET**
4. **Stop Loss immediato**: inserire nel broker appena si entra
5. **Chandelier Exit**: se close < trailing stop → EXIT
6. **Weekend**: chiudere o ridurre 50% (CFD ha costo overnight)
7. **Earnings**: mai tenere CFD aperto la notte prima
8. **Score ≤ 3/6**: skip sempre
9. **Position sizing**: usare lo script, mai superare
10. **BTP-Bund** (ITA): widening >10bp → chiudere bancari
11. **EUR/USD** (ETF): EUR in rafforzamento erode rendimenti
12. **Max posizioni**: ITA max 3 CFD, ETF max 3

---

## Dipendenze

```
yfinance>=0.2.40
pandas-ta>=0.3.14b
pandas>=2.0
pyyaml>=6.0
rich>=13.0
```
