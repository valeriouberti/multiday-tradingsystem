# Multiday Trading System — ITA CFD + ETF Settoriali

> Tre strategie via **Fineco**. Selezione titoli automatica (screening tecnico Python)
> + validazione fondamentale via AI (Perplexity Pro).
> Holding period: 3-7 sessioni.
>
> | Strategia | Strumento | Leva | Capitale | Benchmark |
> | :-- | :-- | :-- | :-- | :-- |
> | **ITA CFD** | CFD su azioni FTSE MIB | 5:1 ESMA | €1.000 | ETFMIB.MI |
> | **US CFD** | CFD su azioni S&P 500 | 5:1 ESMA | $1.000 | SPY |
> | **ETF Settoriali** | Cash ETF Borsa Italiana | 1:1 | €4.000 | CSSPX.MI |
> | **Totale** | | | **~€6.000** | |

---

## Workflow Giornaliero

### 07:30 — Macro Veto (2 min, da telefono)

Controlla [Investing.com](https://investing.com/economic-calendar).

**STOP se presente:**

| Macro EU | Macro USA |
| :-- | :-- |
| ECB (tassi o conferenza) | FOMC (decisione o minutes) |
| EU CPI / HICP | CPI USA |
| PMI Eurozona | NFP (1° venerdi mese) |
| Asta BTP / rating Italia | PPI |

Se macro veto → nessun trade per nessuna delle due strategie.

---

### 07:30 — PROMPT 0: Overnight Check ETF (3 min, da telefono)

> Solo per ETF. Valida i settori scelti ieri dopo la chiusura US + sessione
> asiatica. Se un settore e stato KILLED, lo salti e aspetti Prompt 1 alle 13:00.

**Perplexity Pro (schedulato)**

```
I hold (or plan to enter) these Borsa Italiana sector ETFs today:
1. [ticker.MI] — [sector] — Catalyst: [from yesterday's Prompt 1]
2. [ticker.MI] — [sector] — Catalyst: [...]
3. [ticker.MI] — [sector] — Catalyst: [...]

What happened OVERNIGHT (US market close, after-hours, Asia session,
European pre-market futures) that affects these sectors?

For each sector, answer in ONE line:
- CONFIRMED: overnight news strengthens the thesis (specify what)
- NEUTRAL: no material change, proceed as planned
- KILLED: overnight reversal, new risk, or catalyst exhausted (specify what)

Also check:
- VIX futures: did VIX move >2 points overnight? If yes, flag it.
- EUR/USD overnight: significant move that changes sector exposure?
- S&P 500 futures at 07:30 CET: direction vs yesterday's close?

OUTPUT FORMAT (strict, one line per sector):
[ticker.MI] | CONFIRMED / NEUTRAL / KILLED | [reason in 10 words max]
VIX futures: [value] | S&P futures: [+/- %] | EUR/USD: [level]
```

| Risultato | Azione |
| :-- | :-- |
| Tutti CONFIRMED/NEUTRAL | Procedi con i settori di ieri |
| Un settore KILLED | Rimuovilo. A 13:00 sostituisci col Prompt 1 |
| Tutti KILLED | Skip mattina. Aspetta Prompt 1 alle 13:00 |
| VIX futures > 27 | Gate VIX blocchera i GO |

---

### 08:00 — ITA CFD: Prompt 1 + Script + Prompt 2 auto (10 min)

> Flusso ottimizzato: Prompt 1 per contesto → Script scansiona tutti i 40 titoli →
> Prompt 2 inviato automaticamente su Telegram con i ticker GO/WATCH.

#### PROMPT 1 ITA: Market Context + Catalyst (schedulato su Perplexity)

> Non serve piu selezionare 3 titoli. Lo script scansiona tutti i 40 FTSE MIB.
> Prompt 1 serve solo per contesto macro e catalyst attivi.

```
Agisci come analista istituzionale su Borsa Italiana / FTSE MIB.
Cerca notizie in tempo reale. Oggi e [DATA].

CONTESTO: Faccio swing trading CFD (3-7 sessioni, leva 5:1 Fineco)
su tutti i 40 titoli FTSE MIB. Uno script Python seleziona automaticamente
i titoli con segnali tecnici positivi. Ho bisogno di contesto macro
e catalyst per validare i segnali.

COMPITO: Fammi un briefing pre-market in 3 sezioni.

1. MACRO ITALIA & EU (oggi e prossime 48h):
   - Eventi BCE, aste BTP, PMI, CPI, PIL
   - Spread BTP-Bund: livello e direzione
   - Futures FTSE MIB / Euro Stoxx 50: direzione
   - MACRO VETO: c'e un evento oggi che rende TUTTE le entry rischiose?
     Se si → ⚠️ MACRO VETO DAY (specifica quale)

2. CATALYST ATTIVI (ultime 24-48h con gambe multiday):
   Elenca SOLO catalyst concreti (con fonte e data) che muovono titoli FTSE MIB:
   - Trimestrali sopra/sotto attese (quali titoli)
   - Decisioni governo (difesa, energia, infrastrutture)
   - M&A, cambi normativi UE, rotazione settoriale
   - Commodity (petrolio → ENI/TEN, rame → industriali)
   - EUR/USD → impatto export
   - Spread BTP-Bund → impatto bancari

   Per ogni catalyst:
   [ticker.MI] | Catalyst: [1 frase] | Gambe: [perche non ancora prezzato]

3. RISK FLAGS:
   - Titoli FTSE MIB che pubblicano trimestrali nei prossimi 7 giorni
   - Titoli in calo >2% nel premarket
   - Settori a rischio per eventi imminenti

FORMATO: Sii conciso. Bullet point. No filler.
```

#### 08:30 — Script ITA (automatico)

```bash
python main_ita.py    # scansiona tutti i 40 titoli FTSE MIB
```

Lo script:
1. Scansiona tutti i 40 titoli nel config
2. Calcola i 6 check + 2 gate per ciascuno
3. Invia il report su Telegram (GO / WATCH / SKIP)
4. **Invia automaticamente il Prompt 2 su Telegram** con i ticker GO/WATCH pre-compilati

→ Se GO: leggi Prompt 2 su Telegram, copialo su Perplexity, poi prepara ordini Fineco.
→ Se nessun GO/WATCH: niente da fare, lo script non invia Prompt 2.

#### PROMPT 2 ITA: Deep Dive (auto-generato dallo script)

> **Non serve piu scriverlo a mano.** Lo script lo compone con i ticker esatti
> e lo invia su Telegram in 2 messaggi. Basta copiare il secondo su Perplexity.

**Messaggio 1 (contesto):** Riepilogo tecnico per ogni ticker GO/WATCH:
- Score, check passati/falliti, entry method, premarket %
- Stop loss, TP1, chandelier stop
- Size, notional, margin

**Messaggio 2 (il prompt da copiare):** Chiede a Perplexity solo 3 domande
focalizzate sui deal-breaker che il tecnico non vede:

| # | Domanda | Logica |
| :-- | :-- | :-- |
| 1 | **Earnings Risk** | Trimestrali nei prossimi 7gg? ⛔ = veto automatico |
| 2 | **Catalyst** | C'e un catalyst attivo 48h con gambe multiday? |
| 3 | **Evento Killer** | Evento specifico che inverte il titolo prima del TP1? |

**Regole di decisione integrate nel prompt:**
- ⛔ Earnings → SKIP automatico
- 🔴 No catalyst + ⚠️ Evento → SKIP
- 🟡 Catalyst debole → WAIT
- 🟢 Catalyst attivo + ✅ No evento → ENTRY
- Per bancari: nota su spread BTP-Bund se in allargamento

> **Perche solo 3 domande?** Le vecchie 6 domande (short interest, flussi
> istituzionali, ecc.) producevano rumore. Per un hold 3-7 giorni, i veri
> deal-breaker sono: earnings (veto binario), catalyst (il "perche" del trade),
> evento imminente (il rischio concreto). Il resto e noise.

---

### 09:00 — ITA CFD Entry (5 min, Fineco app)

| Entry Method | Finestra | Condizione |
| :-- | :-- | :-- |
| GAP_UP | 09:00-09:15 | Gap >= 0.5% sopra EMA20 + max giorno precedente |
| PULLBACK | 09:15+ | Rimbalzo su EMA20 Daily |
| ORB | 09:15+ | Breakout Opening Range H1 con volume >= 1.5x |
| BONE_ZONE | 09:15+ | Dip nella zona EMA 9-20, candela verde sopra EMA9 |
| WAIT | — | Nessun setup → skip |

Subito dopo entry: inserire Stop Loss + TP1 come ordini su Fineco.

---

### 13:00 — US S&P 500 CFD: Prompt 1 + Script + Prompt 2 auto (10 min)

> Stesso flusso ITA: Prompt 1 per contesto US → Script scansiona 100 titoli →
> Prompt 2 inviato automaticamente su Telegram con i ticker GO/WATCH.
> US premarket attivo da 7:00 AM ET (13:00 CET), dati macro EU digeriti.

| Aspetto | Valore |
| :-- | :-- |
| Universo | Top 100 S&P 500 per liquidita |
| Benchmark | SPY |
| Capitale | $1.000 (separato da ITA) |
| Leva | 5:1 (Fineco ESMA CFD) |
| VIX gate | < 30 |
| ADX gate | >= 20 su SPY |
| Valuta | USD |

#### PROMPT 1 US: Market Context + Catalyst (Perplexity, 13:00 CET)

```
Act as an institutional equity strategist covering US large-cap stocks
(S&P 500). Search real-time news. Today is [DATE].

CONTEXT: I swing trade US large-cap stocks as CFDs via Fineco (5:1 ESMA
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
     If yes → ⚠️ MACRO VETO DAY (specify which)

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

#### 13:15 — Script US (automatico)

```bash
python main_us.py    # scansiona tutti i ~100 titoli S&P 500
```

Lo script:
1. Scansiona tutti i ~100 titoli nel config
2. Calcola i 6 check + 2 gate per ciascuno (benchmark: SPY)
3. Invia il report su Telegram (GO / WATCH / SKIP, solo GO/WATCH in dettaglio)
4. **Invia automaticamente il Prompt 2 su Telegram** con i ticker GO/WATCH

→ Se GO: leggi Prompt 2 su Telegram, copialo su Perplexity, poi prepara ordini Fineco.
→ Se nessun GO/WATCH: niente da fare.

#### PROMPT 2 US: Deep Dive (auto-generato dallo script)

> **Stesso sistema dell'ITA.** Lo script lo compone con i ticker esatti
> e lo invia su Telegram in 2 messaggi.

**Messaggio 1 (contesto):** Riepilogo tecnico per ogni ticker GO/WATCH (USD):
- Score, check passati/falliti, entry method, premarket %
- Stop loss, TP1, chandelier stop
- Size, notional, margin

**Messaggio 2 (il prompt da copiare):** 3 domande deal-breaker:

| # | Domanda | Logica |
| :-- | :-- | :-- |
| 1 | **Earnings Risk** | Trimestrali nei prossimi 7gg? ⛔ = veto automatico |
| 2 | **Catalyst** | C'e un catalyst attivo 48h con gambe multiday? |
| 3 | **Killer Event** | FOMC, CPI, NFP, ex-div, antitrust nelle prossime 48h? |

**Regole specifiche US:**
- ⛔ Earnings → SKIP automatico (mai tenere CFD attraverso earnings)
- Per rate-sensitive (bancari, REIT, utilities): nota su 10Y yield move >5bp
- Per mega-cap tech (AAPL, MSFT, NVDA, META, GOOGL, AMZN): nota su antitrust / AI regulation

---

### 15:30 — US CFD Entry (5 min, Fineco app)

> US market apre alle 15:30 CET. Entry nella prima mezz'ora.

| Entry Method | Finestra | Condizione |
| :-- | :-- | :-- |
| GAP_UP | 15:30-15:45 | Gap >= 0.5% sopra EMA20 + max giorno precedente |
| PULLBACK | 15:45+ | Rimbalzo su EMA20 Daily |
| ORB | 15:45+ | Breakout Opening Range H1 con volume >= 1.5x |
| BONE_ZONE | 15:45+ | Dip nella zona EMA 9-20, candela verde sopra EMA9 |
| WAIT | — | Nessun setup → skip |

Subito dopo entry: inserire Stop Loss + TP1 come ordini su Fineco.

---

### 13:30 — ETF: Prompt 1 + 2 (8 min, pausa pranzo, da telefono)

> US pre-market attivo da 2 ore (7:00 AM ET), futures stabiliti,
> dati macro EU digeriti. Momento ottimale per sector rotation.

#### PROMPT 1 ETF: Sector Rotation (schedulato)

```
Act as an institutional quantitative macro strategist. Today is [DATA].

Search for the latest real-time market news and analyze the global equity
market for TODAY's session.

CONTEXT: I trade sector ETFs listed on Borsa Italiana (Milan) in EUR via
Fineco (cash, no leverage). These ETFs track global/US sector indices.
My benchmark is CSSPX.MI (iShares Core S&P 500 on Borsa Italiana).

TASK: Identify the 3 strongest equity SECTORS for a multiday swing trade
(3-7 sessions holding period) based on catalysts from the last 24-48 hours.

Valid sector catalysts include:
- Commodity price surges/collapses (oil, gas, gold, copper, etc.)
- Central bank actions: Fed AND ECB decisions, macro data surprises
- Regulatory/policy changes with sector impact (tariffs, EU regulations,
  Green Deal, defense spending)
- Sector-wide earnings trend (multiple beats/misses in the same sector)
- Fund flow data: ETF inflows/outflows acceleration
- Geopolitical events with measurable sector impact
- EUR/USD moves that amplify or dampen sector returns for EUR-based investors

For EACH of the 3 sectors, map it to the best Borsa Italiana ETF from
this list:
  XDWD.MI  (Tech/World)       XDW0.MI  (Energy MSCI World)
  XDWF.MI  (Financials)      XDWI.MI  (Industrials)
  XDWM.MI  (Materials)       XDWH.MI  (Health Care)
  DFND.MI  (Aerospace/Def)

STRICT RULES:
- Only select sectors where the catalyst has a MULTI-DAY thesis
  (not a one-day event that is already priced in)
- EXCLUDE sectors with major scheduled macro risk in the next 48 hours
  (e.g., don't pick XDWF.MI the day before a Fed or ECB decision)
- Prefer sectors already showing relative strength vs CSSPX.MI over 5 sessions
- Consider EUR/USD direction: a weakening EUR amplifies returns on
  USD-denominated underlying sectors, and vice versa
- Rank sectors by conviction: SECTOR 1 = highest

OUTPUT FORMAT (strict):

## SECTOR 1: [Name] — ETF: [ticker.MI]
Catalyst: [1-2 sentences, what happened and why it has multi-day legs]
RS vs CSSPX.MI (5d): [stronger / weaker / flat]
EUR/USD impact: [tailwind / headwind / neutral]
ETF last close: [price EUR]

## SECTOR 2: [same format]
## SECTOR 3: [same format]

MACRO VETO: List any scheduled macro event today (US or EU) that would
make ALL entries risky. If present, flag with ⚠️ MACRO VETO DAY.
```

#### PROMPT 2 ETF: Deep Dive (schedulato)

```
You are an institutional sector rotation analyst focused on European-listed
ETFs with US/global underlying exposure.

I plan to open multiday swing positions (3-7 sessions) on these Borsa
Italiana sector ETFs (EUR-denominated, cash, no leverage):

SECTOR 1: [ticker.MI] — Catalyst: [from Prompt 1]
SECTOR 2: [ticker.MI] — Catalyst: [from Prompt 1]
SECTOR 3: [ticker.MI] — Catalyst: [from Prompt 1]

For EACH sector ETF, run a rapid risk assessment:

1. MACRO SENSITIVITY: What is the next major macro event — both US (FOMC,
   CPI, NFP, PPI) AND EU (ECB, EU CPI/HICP, PMI) — that could reverse
   this sector's trend? How many sessions away?
   → Flag as 🟢 CLEAR (>5 sessions) / 🟡 NEARBY (2-5 sessions) /
   🔴 IMMINENT (<2 sessions)

2. FUND FLOWS: Any significant inflows or outflows in this sector's ETFs
   (both US-listed and EU-listed) in the last 5 days?
   → Flag as 🟢 INFLOWS / 🔴 OUTFLOWS / ➡️ NEUTRAL

3. SECTOR BREADTH: Are the majority of large-cap components in this sector
   trending up (above their 20-day EMA), or is it carried by 1-2 names?
   → Flag as 🟢 BROAD (>60% above EMA20) / 🟡 NARROW (40-60%) /
   🔴 WEAK (<40%)

4. CORRELATION RISK: Are two or more of my 3 sectors highly correlated
   right now? (e.g., XDW0.MI and XDWM.MI both driven by China demand)
   → If YES: flag as ⚠️ CORRELATED — reduce combined size

5. CURRENCY RISK: Current EUR/USD trend and impact on my positions.
   These ETFs are EUR-denominated but track USD-denominated underlying.
   A strengthening EUR reduces returns, a weakening EUR amplifies them.
   → Flag as 🟢 EUR WEAKENING (tailwind) / 🔴 EUR STRENGTHENING (headwind) /
   ➡️ FLAT

6. INTERMARKET SIGNAL: Any confirming signal from related assets?
   (DXY, EUR/USD, Bund yields, US yields, VIX, VSTOXX, commodity futures)
   → List the most relevant one per sector

OUTPUT FORMAT (strict, one block per sector):
[ticker.MI] | 🟢/🟡/🔴 Macro | 🟢/🔴/➡️ Flows | 🟢/🟡/🔴 Breadth |
             🟢/🔴/➡️ EUR/USD | Intermarket: [signal]

CORRELATION CHECK: [result]
```

#### 13:20 — Script ETF

Aggiorna `config_etf.yaml` con i 3 ticker, poi:

```bash
python main_etf.py
```

→ Se GO: prepara ordini su Fineco per le 14:30.

---

### 14:30-16:30 — ETF Entry (5 min, Fineco app)

Se lo script dice **GO**, compra a mercato. Non serve cercare setup specifici
(GAP_UP, pullback): senza dati real-time ETF, il pomeriggio e la finestra
piu sicura (spread stretti, US open alle 15:30 conferma il move).

Subito dopo entry: inserire Stop Loss + TP1 su Fineco.

---

### 22:00 — PROMPT 3: Exit Review (10 min, dopo cena)

> Per entrambe le strategie. Se hai posizioni aperte ITA + ETF, un solo prompt.

**Perplexity Pro**

```
Ho posizioni aperte su Borsa Italiana:

AZIONI ITA (CFD Fineco):
[lista ticker.MI attivi con data entry e P&L %]

ETF SETTORIALI (cash Fineco):
[lista ticker.MI attivi con data entry e P&L %]

Cerca notizie nelle ultime 8 ore che possano invalidare i catalyst.

Per OGNI posizione rispondi:
1. Catalyst originale ancora valido? SI / NO / IN INDEBOLIMENTO
2. RS vs benchmark (ETFMIB.MI per ITA, CSSPX.MI per ETF): migliorata o peggiorata?
3. Nuovi rischi nelle prossime 48 ore? (BCE, dati macro, geopolitica)
4. Raccomandazione: MANTENERE / RIDURRE / CHIUDERE

Per le azioni ITA aggiungere:
- Spread BTP-Bund: in allargamento o restringimento?

Per gli ETF aggiungere:
- EUR/USD: ha aiutato o danneggiato il rendimento in EUR?

Sii conciso. Un paragrafo per posizione.
```

Dopo il prompt: aggiorna il Chandelier Stop su Fineco per ogni posizione aperta.

---

## Riepilogo Orario

| Ora CET | Strategia | Azione | Durata |
| :-- | :-- | :-- | :-- |
| **07:30** | Tutte | Macro veto (EU + US) | 2 min |
| **07:30** | ETF | Prompt 0 — overnight check | 3 min |
| **08:00** | ITA CFD | Prompt 1 — market context ITA (Perplexity) | 3 min |
| **08:30** | ITA CFD | `python main_ita.py` → report + Prompt 2 auto | 2 min |
| **08:35** | ITA CFD | Copia Prompt 2 da Telegram su Perplexity → deep dive | 3 min |
| **09:00** | ITA CFD | Entry su Fineco (GAP_UP/PB/ORB/BZ) | 5 min |
| **13:00** | US CFD | Prompt 1 — market context US (Perplexity) | 3 min |
| **13:15** | US CFD | `python main_us.py` → report + Prompt 2 auto | 3 min |
| **13:20** | US CFD | Copia Prompt 2 da Telegram su Perplexity → deep dive | 3 min |
| **13:30** | ETF | Prompt 1 + 2 (schedulati, pausa pranzo) | 8 min |
| **13:45** | ETF | `python main_etf.py` + aggiorna config | 2 min |
| **14:30-16:30** | ETF | Entry su Fineco (buy a mercato) | 5 min |
| **15:30** | US CFD | Entry su Fineco (GAP_UP/PB/ORB/BZ) | 5 min |
| **17:00** | ITA CFD | Deadline ITA — no entry dopo | 0 min |
| **20:00** | US CFD | Deadline US — no new entry | 0 min |
| **22:00** | Tutte | Prompt 3 — exit review + aggiorna Trail | 10 min |

**Tempo totale: ~50 minuti/giorno** (3 strategie)

> Nota: ITA e US girano in parallelo nella pausa pranzo. US entry alle 15:30 non
> interferisce con la chiusura ITA alle 17:00.

---

## Dettaglio Tecnico

### 6 Check (comuni a entrambe le strategie)

| # | Check | Timeframe | Logica |
| :-- | :-- | :-- | :-- |
| 1 | EMA 20 > EMA 50 | Daily | Trend rialzista |
| 2 | EMA 20 > EMA 50 | Weekly | Trend strutturale |
| 3 | MACD > Signal | Daily | Momentum in accelerazione |
| 4 | RSI > 45 | Daily | Forza relativa positiva (tuned da 50) |
| 5 | MFI > 40 | Daily | Money Flow Index — flusso istituzionale (tuned 50→45→40) |
| 6 | RS vs Benchmark | Daily | Titolo/settore batte il benchmark (20d, 5d ROC) |

### Gates

| Gate | ITA CFD | ETF | Effetto |
| :-- | :-- | :-- | :-- |
| VIX < 35 (ITA) / < 25 (ETF) | ✅ | ✅ | GO → WATCH |
| ADX >= 15 (ITA) / >= 20 (ETF) su benchmark | ✅ | ✅ | GO → WATCH |
| Benchmark Health (EMA20 > EMA50) | — | ✅ | GO → WATCH |
| Correlazione pairwise < 0.7 | — | ✅ | Dimezza size combinato |

### Score (ITA CFD — parametri Optuna WFA)

| Score | Gates OK | Azione |
| :-- | :-- | :-- |
| 3/6, 4/6, 5/6 o 6/6 | tutti OK | **GO** — prepara ordini su Fineco |
| 3/6, 4/6, 5/6 o 6/6 | almeno 1 FAIL | **WATCH** — gate ha bloccato |
| 2/6 | qualsiasi | **WATCH** |
| <= 1/6 | qualsiasi | **SKIP** |

### Score (ETF — parametri originali)

| Score | Gates OK | Azione |
| :-- | :-- | :-- |
| 5/6 o 6/6 | tutti OK | **GO** — prepara ordini su Fineco |
| 5/6 o 6/6 | almeno 1 FAIL | **WATCH** — gate ha bloccato |
| 4/6 | qualsiasi | **WATCH** |
| <= 3/6 | qualsiasi | **SKIP** |

### Position Sizing

**ITA CFD (con leva 5:1):**
```
shares = min(
    (€1.000 × 2%) / (ATR × 1.5),           # risk-based (€20 rischio)
    (€1.000 × 40% × 5) / prezzo            # margin cap (€2.000 notional)
)
```

**ETF (cash, no leva):**
```
shares = min(
    (€4.000 × 1.5%) / (ATR × 1.5),         # risk-based (€60 rischio)
    (€4.000 × 40%) / prezzo                 # capital cap (€1.600)
)
```

### Gestione Posizione

| Livello | Calcolo | Azione |
| :-- | :-- | :-- |
| Stop Loss | Close - ATR(14) × 1.5 | Inserire subito dopo entry |
| TP1 | Close + ATR(14) × 1.5 | Chiudi 50%, sposta stop a breakeven |
| Chandelier | Highest(H,22) - ATR(14) × 3 | Trailing stop, aggiornare ogni sera |

---

## Ticker di Riferimento

### FTSE MIB (ITA CFD)

| Settore | Ticker | Nome | Prezzo ~€ |
| :-- | :-- | :-- | :-- |
| Banking | `ISP.MI` | Intesa Sanpaolo | ~5 |
| Banking | `UCG.MI` | Unicredit | ~61 |
| Banking | `BAMI.MI` | Banco BPM | ~12 |
| Banking | `FBK.MI` | FinecoBank | ~19 |
| Energy | `ENI.MI` | ENI | ~23 |
| Utilities | `ENEL.MI` | Enel | ~9 |
| Energy | `TEN.MI` | Tenaris | ~25 |
| Defence | `LDO.MI` | Leonardo | ~59 |
| Automotive | `RACE.MI` | Ferrari | ~283 |
| Insurance | `G.MI` | Generali | ~34 |
| Insurance | `UNI.MI` | Unipol | ~19 |
| Consumer | `CPR.MI` | Campari | ~6 |
| Semicond. | `STMMI.MI` | STMicroelectronics | ~29 |

**Benchmark**: `ETFMIB.MI` (Lyxor FTSE MIB ETF)

### ETF Settoriali (Borsa Italiana)

| Settore | Ticker MI | Nome ETF |
| :-- | :-- | :-- |
| S&P 500 (benchmark) | `CSSPX.MI` | iShares Core S&P 500 UCITS ETF |
| Tech / World | `XDWD.MI` | Xtrackers MSCI World UCITS ETF 1C |
| Energy | `XDW0.MI` | Xtrackers MSCI World Energy UCITS ETF |
| Financials | `XDWF.MI` | Xtrackers MSCI World Financials |
| Industrials | `XDWI.MI` | Xtrackers MSCI World Industrials |
| Materials | `XDWM.MI` | Xtrackers MSCI World Materials |
| Health Care | `XDWH.MI` | Xtrackers MSCI World Health Care |
| Aerospace/Def | `DFND.MI` | iShares Global Aerospace & Defence |

---

## Regole Operative Fisse

1. **Macro Veto**: FOMC / CPI / NFP / ECB / EU CPI → nessun trade
2. **Gates**: gate fallito degrada GO → WATCH (lo script lo fa automaticamente)
3. **No entry dopo le 17:00 CET**: Borsa chiude alle 17:25
4. **Stop Loss immediato**: inserire nel broker appena si entra
5. **Chandelier Exit**: se close < Chandelier stop → EXIT
6. **Weekend**: chiudere o ridurre 50% — CFD ha costo overnight (~0.05%/giorno)
7. **Earnings**: mai tenere CFD aperto la notte prima degli earnings
8. **Score <= 1/6**: skip sempre (ITA), **Score <= 2/6**: skip (ETF)
9. **Position sizing**: usare il numero di shares dello script, mai superare
10. **BTP-Bund spread** (ITA): widening >10bp in un giorno → chiudere bancari
11. **EUR/USD** (ETF): EUR in rafforzamento erode rendimenti ETF con sottostante USD
12. **Max posizioni**: ITA max 3 CFD, US max 3 CFD, ETF max 3 posizioni
13. **Correlazione** (ETF): se pairwise > 0.7, dimezzare il size combinato
14. **US overnight**: CFD US ha costo overnight simile a ITA (~0.05%/giorno)
15. **US earnings season**: ~25% S&P 500 riporta per trimestre — earnings gate critico
16. **10Y yield** (US): move >5bp impatta bancari, REIT, utilities

---

## PineScript — TradingView

Indicatore v1.2 con parametri Optuna WFA (RSI 45, MFI 40, VIX 35, ADX 15, GO >= 3):

```
pinescript/ita_cfd_validator.pine
```

Setup TradingView:
1. Apri un titolo italiano (`MIL:UCG`) o ETF (`MIL:DFND`)
2. Pine Editor → incolla → Add to Chart
3. Configura benchmark: `MIL:ETFMIB` (ITA) o `MIL:CSSPX` (ETF)
4. Alert: tasto destro → "Add Alert" per GO/WATCH/Chandelier Exit

---

## Running

```bash
python main_ita.py                          # ITA CFD — 40 titoli FTSE MIB
python main_us.py                           # US CFD — ~100 titoli S&P 500
python main_etf.py                          # ETF settoriali
python main_us.py --tickers "AAPL,NVDA"     # override tickers
```

## Telegram

Il report viene inviato automaticamente su Telegram dopo ogni esecuzione
dello script (locale o CI). Nessuna dipendenza aggiuntiva (usa urllib).

### Setup (una tantum, 2 min)

1. Apri Telegram → cerca `@BotFather` → `/newbot` → copia il **token**
2. Invia un messaggio qualsiasi al tuo bot
3. Apri nel browser: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Copia il `chat_id` dal JSON

### Configurazione

**Locale** — aggiungi al tuo `.zshrc` o `.bashrc`:
```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_CHAT_ID="987654321"
```

**GitHub Actions** — aggiungi come secrets nel repo:
- Settings → Secrets → `TELEGRAM_BOT_TOKEN`
- Settings → Secrets → `TELEGRAM_CHAT_ID`

Se le variabili non sono impostate, il report viene stampato solo a terminale (nessun errore).

### Esempio messaggio

```
🇮🇹 ITA CFD Report

VIX: 24.8 ✅ | ADX: 22.0 ✅

🟢 LDO.MI 6/6 GO
   Entry: PULLBACK | Premkt: +1.32%
   Stop: €56.20 | TP1: €61.80 | Trail: €53.10
   Size: 3 shares (€177 not. / €35 margin)

🟡 UCG.MI 4/6 WATCH
   Entry: WAIT | Premkt: -0.21%
   Stop: €58.40 | TP1: €63.60 | Trail: €55.30

🔴 ENI.MI 2/6 SKIP

6 GO | 1 WATCH | 2 SKIP
```

**US CFD:**
```
🇺🇸 US S&P 500 CFD Report

VIX: 18.2 ✅ | ADX: 24.5 ✅

🟢 NVDA 6/6 GO
   Entry: GAP_UP | Premkt: +2.15%
   Stop: $118.40 | TP1: $128.60 | Trail: $112.30
   Size: 2 shares ($248 not. / $50 margin)

🟡 JPM 4/6 WATCH
   Entry: PULLBACK | Premkt: +0.45%
   Stop: $238.20 | TP1: $252.80 | Trail: $230.10

12 GO | 8 WATCH | 77 SKIP
```

---

## Automazione (GitHub Actions)

- ITA: trigger automatico alle 8:30 CET o manuale da GitHub mobile app
- ETF: trigger automatico alle 14:00 CET o manuale da GitHub mobile app
- Input tickers via `--tickers` flag (GitHub app → Actions → Run workflow)
- Telegram: il Python script invia il report se i secrets sono configurati

---

## Backtester

Motore di backtesting completo per validare la strategia su dati storici.

### Componenti

| Script | Descrizione |
| :-- | :-- |
| `backtest.py` | Backtest singolo ticker (`--ticker ISP.MI --start 2023-01-01 --end 2024-12-31`) |
| `backtest_ftsemib.py` | Backtest tutti i 39 titoli FTSE MIB con report aggregato |
| `optimize_params.py` | Grid search in-sample (1080 combinazioni su 2020-2024) |
| `walk_forward.py` | Walk-Forward Analysis (8 finestre rolling, validazione OOS) |
| `optimize_optuna.py` | Optuna Bayesian optimization (ITA + US, simple + WFA) |

### Trade Lifecycle (simulazione)

```
GO signal → Entry at Close
  → Stop Loss: Close - ATR(14) × 1.5
  → TP1: Close + ATR(14) × 1.5
     Se TP1 raggiunto: chiudi 50%, sposta stop a breakeven
  → Chandelier Trailing: Highest(H,22) - ATR(14) × 3.0
     Ratchet up only (non scende mai)
  → Exit: stop hit, oppure fine dati
```

### CFD Margin Accounting

Il backtester gestisce correttamente la leva CFD:
- Entry cost = notional / leverage (margine, non intero notional)
- Close proceeds = margine restituito + P&L realizzato
- Equity = cash + margine bloccato + P&L non realizzato

---

## Ottimizzazione Parametri

### Parametri Tuned (ITA CFD)

Ottimizzati tramite grid search su 2020-2024 (tutti i 39 titoli FTSE MIB):

| Parametro | Originale | Tuned | Motivazione |
| :-- | :-- | :-- | :-- |
| `rsi_threshold` | 50 | **45** | Cattura entry nella fase iniziale del trend |
| `mfi_threshold` | 50 | **40** | Filtro meno restrittivo sui flussi (45→40 via Optuna WFA) |
| `vix_threshold` | 25 | **35** | Gate VIX troppo stretto, bloccava trade validi in fear moderata |
| `adx_threshold` | 20 | **15** | Lieve rilassamento, filtra ancora mercati piatti (Optuna WFA) |
| `go_threshold` | 5 | **3** | Perfettamente stabile su tutte le 8 finestre WFA (5→4→3) |

Il set originale si posizionava #476/1080 combinazioni.

**Validazione Optuna WFA (8 finestre OOS):**
- Avg OOS return: +1.84% per finestra (7/8 finestre profittevoli)
- Unica finestra negativa: 2022-H1 (guerra Ucraina + rialzo tassi)
- GO=3 selezionato in tutte le 8 finestre (massima stabilita)
- VIX gate ON confermato critico (protezione bear market)

### Grid Search (`optimize_params.py`)

Griglia:
```
vix_threshold: [20, 25, 30, 35, 999(=OFF)]
mfi_threshold: [40, 45, 50, 55]
mfi_length:    [10, 14, 20]
rsi_threshold: [45, 50, 55]
adx_threshold: [15, 20, 25]
go_threshold:  [4, 5]
```

Totale: 5 × 4 × 3 × 3 × 3 × 2 = **1.080 combinazioni**

Output: `output/optimization/param_optimization.csv` con ranking per avg return.

### Walk-Forward Analysis (`walk_forward.py`)

Il grid search da solo e pericoloso (overfitting). La WFA valida la robustezza:

```
Finestra 1: Train 2019-01→2020-12 | Test 2021-H1  (OOS)
Finestra 2: Train 2019-07→2021-06 | Test 2021-H2  (OOS)
Finestra 3: Train 2020-01→2021-12 | Test 2022-H1  (OOS)
Finestra 4: Train 2020-07→2022-06 | Test 2022-H2  (OOS)
Finestra 5: Train 2021-01→2022-12 | Test 2023-H1  (OOS)
Finestra 6: Train 2021-07→2023-06 | Test 2023-H2  (OOS)
Finestra 7: Train 2022-01→2023-12 | Test 2024-H1  (OOS)
Finestra 8: Train 2022-07→2024-06 | Test 2024-H2  (OOS)
```

**Metriche chiave:**
- **Efficiency Ratio** = OOS return / IS return (>0.5 = robusto, <0.25 = overfit)
- **Parameter Stability** = quanto spesso lo stesso valore viene selezionato across windows
- **Baseline comparison** = WFA vs parametri fissi su tutte le finestre OOS

Output: `output/walk_forward/walk_forward_results.csv`

### Optuna Bayesian Optimization (`optimize_optuna.py`)

Alternativa al grid search brute-force. Usa il **TPE sampler** (Tree-structured Parzen Estimator) per convergere verso i parametri ottimali in ~300 trial invece di 1.080 combinazioni.

**Vantaggi rispetto al grid search:**
- ~3-4x piu veloce (300 trial vs 1.080 combos)
- Spazio di ricerca piu ampio (continuo, non discreto)
- Pruning automatico dei trial non promettenti
- Parameter importance analysis integrata

**Spazio di ricerca:**
```
vix_threshold: [20, 25, 30, 35, 999]
mfi_threshold: 35-60 (step 5)
mfi_length:    [10, 14, 20]
rsi_threshold: 35-60 (step 5)
adx_threshold: 10-30 (step 5)
go_threshold:  3-5
```

**Due modalita:**

1. **Simple** — ottimizzazione single-period (2020-2024):
```bash
python optimize_optuna.py --mode ita --trials 300    # ITA (39 tickers)
python optimize_optuna.py --mode us --trials 300     # US (33 sector-sample stocks)
```

2. **Walk-Forward** — WFA con Optuna per finestra (8 windows):
```bash
python optimize_optuna.py --mode ita --wfa --trials 200    # ITA WFA
python optimize_optuna.py --mode us --wfa --trials 200     # US WFA
```

**Output:**
- `output/optimization_{mode}/optuna_results.csv` (simple)
- `output/optimization_{mode}/optuna_wfa_results.csv` (WFA)
- Top 20 trial table con parametri e return
- Parameter importance ranking
- WFA: efficiency ratio, parameter stability, overfitting verdict

**US sector sample (33 stocks):** 3 titoli rappresentativi per ciascuno degli 11 settori GICS:
AAPL/MSFT/NVDA, JPM/GS/BLK, UNH/LLY/JNJ, TSLA/HD/AMZN, GE/CAT/RTX,
XOM/CVX/COP, NFLX/GOOGL/META, PG/KO/COST, NEE/SO/DUK, LIN/FCX/SHW, PLD/AMT/EQIX

---

### Prossimi Step di Ottimizzazione

1. **Monte Carlo Simulation** — Shuffle ordine trade (o resample daily returns con replacement) migliaia di volte. Produce distribuzione di outcome invece di una singola equity curve: intervalli di confidenza, probabilita di ruin, worst-case drawdown realistico.

2. **Parameter Sensitivity Heatmap** — Heatmap 2D di return vs coppie di parametri. Un picco isolato (RSI=45 ottimo, RSI=44/46 pessimi) segnala overfitting. Un plateau (RSI 40-50 tutti simili) conferma robustezza.

3. **Regime-Aware Testing** — Testare la strategia per regime di mercato separatamente:
   - Bull trending (2021, 2023-2024)
   - Crash/high-vol (Feb-Mar 2020, 2022 selloff)
   - Range-bound (choppy 2022)
   - Valida se i gate VIX/ADX proteggono effettivamente nei regimi sfavorevoli.

4. **Transaction Cost Sensitivity** — Aggiungere costi reali al backtester:
   - Spread bid-ask (0.1-0.3% su titoli .MI)
   - Costo overnight CFD (~0.05%/giorno)
   - Slippage su entry/exit
   - Una strategia +8% a costi zero puo diventare -2% con friction realistici.

5. **Combinatorial Purged Cross-Validation (CPCV)** — Metodo di Lopez de Prado: genera tutte le possibili combinazioni train/test eliminando overlap temporali. Piu rigoroso statisticamente del k-fold CV per serie temporali finanziarie.

6. **ETF Parameter Tuning** — Applicare lo stesso pipeline (grid search + WFA) alla strategia ETF settoriali con i suoi 4 gate e il benchmark CSSPX.MI.
