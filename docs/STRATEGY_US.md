# US S&P 500 CFD Strategy — Prompts & Parameters

> CFD su azioni S&P 500 via broker. Leva 5:1 ESMA. Capitale: $1.000. Benchmark: SPY.

---

## Workflow US

### 13:00 — Prompt 1 US: Market Context + Catalyst (Perplexity)

> US premarket attivo da 7:00 AM ET (13:00 CET), dati macro EU digeriti.

```
Act as an institutional equity strategist covering US large-cap stocks
(S&P 500). Search real-time news. Today is [DATE].

CONTEXT: I swing trade US large-cap stocks as CFDs via broker (5:1 ESMA
leverage, $1,000 capital, 3-7 session holding period). An automated
Python screener scans all 100 stocks technically — I need macro context
and active catalysts to validate the signals.

TASK: Pre-market briefing in 3 sections.

1. US MACRO (today + next 48h):
   - Fed/FOMC status, next meeting date
   - Key data releases: CPI, PPI, NFP, jobless claims, retail sales
   - 10Y Treasury yield: level and direction
   - USD/EUR: direction and impact on multinationals
   - S&P 500 / Nasdaq futures at 7:00 AM ET: direction vs prev close
   - MACRO VETO: is there an event TODAY that makes ALL entries risky?
     If yes → MACRO VETO DAY (specify which)

2. ACTIVE CATALYSTS (last 24-48h with multi-day legs):
   List ONLY concrete catalysts (with source and date) moving S&P 500 stocks:
   - Earnings beats/misses (which stocks, which sector)
   - Fed speakers / rate expectations shift
   - Sector regulation (antitrust, AI policy, pharma pricing)
   - Geopolitical (tariffs, trade deals, defense spending)
   - Commodity moves (oil → XOM/COP, copper → FCX, gold → NEM)
   - M&A activity involving S&P 500 names
   - Fund flow data / sector rotation signals

   For each catalyst:
   [TICKER] | Catalyst: [1 sentence] | Legs: [why not priced in yet]

3. RISK FLAGS:
   - S&P 500 stocks reporting earnings in the next 7 trading days
   - Stocks down >2% in pre-market
   - Sectors at risk from imminent events

FORMAT: Concise. Bullet points. No filler.
```

### 13:15 — Script US (automatico)

```bash
python main.py --mode us    # scansiona tutti i ~100 titoli S&P 500
```

Lo script:
1. Scansiona tutti i ~100 titoli nel config
2. Calcola i 6 check + 2 gate per ciascuno (benchmark: SPY)
3. Classifica i top 5 per rank (score + RS)
4. Genera un **PDF report** con i **top 5** ticker (tabella, action plan, Perplexity prompt)
5. Invia il PDF su Telegram con caption riassuntiva (top 5 + gates)

### Prompt 2 US: Deep Dive (nel PDF, pagina dedicata)

Il PDF include una pagina "Perplexity Prompt (copy & paste)" in font monospaced,
pronta da copiare. Contiene i ticker GO/WATCH del top 5 con 3 domande deal-breaker:

| # | Domanda | Logica |
| :-- | :-- | :-- |
| 1 | **Earnings Risk** | Trimestrali nei prossimi 7gg? = veto automatico |
| 2 | **Catalyst** | C'e un catalyst attivo 48h con gambe multiday? |
| 3 | **Killer Event** | FOMC, CPI, NFP, ex-div, antitrust nelle prossime 48h? |

**Regole specifiche US:**
- Earnings → SKIP automatico (mai tenere CFD attraverso earnings)
- Per rate-sensitive (bancari, REIT, utilities): nota su 10Y yield move >5bp
- Per mega-cap tech (AAPL, MSFT, NVDA, META, GOOGL, AMZN): nota su antitrust / AI regulation

### 15:30 — US CFD Entry (broker app)

> US market apre alle 15:30 CET. Entry nella prima mezz'ora.

| Entry Method | Finestra | Condizione |
| :-- | :-- | :-- |
| GAP_UP | 15:30-15:45 | Gap >= 0.5% sopra EMA20 + max giorno precedente |
| PULLBACK | 15:45+ | Rimbalzo su EMA20 Daily |
| ORB | 15:45+ | Breakout Opening Range H1 con volume >= 1.5x |
| BONE_ZONE | 15:45+ | Dip nella zona EMA 9-20, candela verde sopra EMA9 |
| WAIT | — | Nessun setup → skip |

---

## Score US (parametri Optuna WFA)

| Score | Gates OK | Azione |
| :-- | :-- | :-- |
| >= 4/6 | tutti OK | **GO** — prepara ordini su broker |
| >= 4/6 | almeno 1 FAIL | **WATCH** — gate ha bloccato |
| 3/6 | qualsiasi | **WATCH** |
| <= 2/6 | qualsiasi | **SKIP** |

Gates: VIX < 30, ADX >= 10 su SPY

---

## Parametri Tuned (Optuna WFA)

| Parametro | Default | Tuned | Motivazione |
| :-- | :-- | :-- | :-- |
| `rsi_threshold` | 45 | **40** | RSI 35-45 dominante nelle finestre WFA |
| `mfi_threshold` | 45 | **45** | Stabile, nel mezzo del range WFA |
| `vix_threshold` | 30 | **30** | VIX gate confermato necessario (2022-H1) |
| `adx_threshold` | 20 | **10** | Selezionato consistentemente in tutte le finestre |
| `go_threshold` | 4 | **4** | Moda WFA (5/8 finestre usano GO=4 o 5) |

**Validazione Optuna WFA (8 finestre OOS):**
- Avg OOS return: +2.27% per finestra (7/8 finestre profittevoli)
- Unica finestra negativa: 2022-H1 (-4.59%, meno grave di ITA -6.94%)
- US performa meglio con drawdown inferiori grazie alla diversificazione settoriale
- Total OOS PnL: +$5,980

---

## PineScript — US CFD Validator v1.0

```
pinescript/us_cfd_validator.pine
```

Parametri: RSI 40, MFI 45, VIX 30, ADX 10, GO >= 4

Setup TradingView:
1. Apri un titolo US (`NASDAQ:AAPL`, `NYSE:JPM`)
2. Pine Editor → incolla → Add to Chart
3. Benchmark: `AMEX:SPY` (default)
4. Alert: tasto destro → "Add Alert" per GO/WATCH/Chandelier Exit

---

## Universo (Top 100 S&P 500)

Definito in `config/us.yaml` — 100 titoli suddivisi per settore GICS:
Technology (15), Financials (12), Health Care (10), Consumer Disc. (8),
Industrials (10), Energy (7), Communication (5), Consumer Staples (7),
Utilities (5), Materials (5), Real Estate (4), Semiconductors (6), Mega-cap (3).

**Optimization sample** (33 titoli, 3 per settore):
AAPL/MSFT/NVDA, JPM/GS/BLK, UNH/LLY/JNJ, TSLA/HD/AMZN, GE/CAT/RTX,
XOM/CVX/COP, NFLX/GOOGL/META, PG/KO/COST, NEE/SO/DUK, LIN/FCX/SHW, PLD/AMT/EQIX

---

## Regole Specifiche US

- **US overnight**: CFD US ha costo overnight ~0.05%/giorno
- **US earnings season**: ~25% S&P 500 riporta per trimestre — earnings gate critico
- **10Y yield**: move >5bp impatta bancari, REIT, utilities
- **Deadline**: no entry dopo le 20:00 CET (16:00 ET)
- **Max posizioni**: 3 CFD US contemporanei
