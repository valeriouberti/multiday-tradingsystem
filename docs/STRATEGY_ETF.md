# ETF Settoriali Strategy — Prompts & Parameters

> Cash ETF settoriali su Borsa Italiana via broker. No leva. Capitale: €4.000. Benchmark: CSSPX.MI.

---

## Workflow ETF

### 07:30 — Prompt 0: Overnight Check (da telefono)

> Valida i settori scelti ieri dopo la chiusura US + sessione asiatica.

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

### 13:30 — Prompt 1 ETF: Sector Rotation (Perplexity)

```
Act as an institutional quantitative macro strategist. Today is [DATA].

Search for the latest real-time market news and analyze the global equity
market for TODAY's session.

CONTEXT: I trade sector ETFs listed on Borsa Italiana (Milan) in EUR via
broker (cash, no leverage). These ETFs track global/US sector indices.
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
- EXCLUDE sectors with major scheduled macro risk in the next 48 hours
- Prefer sectors already showing relative strength vs CSSPX.MI over 5 sessions
- Consider EUR/USD direction
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
make ALL entries risky. If present, flag with MACRO VETO DAY.
```

### Prompt 2 ETF: Deep Dive (Perplexity)

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
   → Flag as CLEAR (>5 sessions) / NEARBY (2-5 sessions) / IMMINENT (<2 sessions)

2. FUND FLOWS: Any significant inflows or outflows in this sector's ETFs
   (both US-listed and EU-listed) in the last 5 days?
   → Flag as INFLOWS / OUTFLOWS / NEUTRAL

3. SECTOR BREADTH: Are the majority of large-cap components in this sector
   trending up (above their 20-day EMA), or is it carried by 1-2 names?
   → Flag as BROAD (>60% above EMA20) / NARROW (40-60%) / WEAK (<40%)

4. CORRELATION RISK: Are two or more of my 3 sectors highly correlated
   right now?
   → If YES: flag as CORRELATED — reduce combined size

5. CURRENCY RISK: Current EUR/USD trend and impact on my positions.
   → Flag as EUR WEAKENING (tailwind) / EUR STRENGTHENING (headwind) / FLAT

6. INTERMARKET SIGNAL: Any confirming signal from related assets?
   (DXY, EUR/USD, Bund yields, US yields, VIX, VSTOXX, commodity futures)
   → List the most relevant one per sector

OUTPUT FORMAT (strict, one block per sector):
[ticker.MI] | Macro | Flows | Breadth |
             EUR/USD | Intermarket: [signal]

CORRELATION CHECK: [result]
```

### 13:45 — Script ETF

Aggiorna `config_etf.yaml` con i 3 ticker, poi:

```bash
python main.py --mode etf
```

### 14:30-16:30 — ETF Entry (broker app)

Se lo script dice **GO**, compra a mercato. Non serve cercare setup specifici:
senza dati real-time ETF, il pomeriggio e la finestra piu sicura (spread stretti,
US open alle 15:30 conferma il move).

---

## Score ETF (parametri Optuna WFA)

| Score | Gates OK | Azione |
| :-- | :-- | :-- |
| >= 3/6 | tutti OK | **GO** — prepara ordini su broker |
| >= 3/6 | almeno 1 FAIL | **WATCH** — gate ha bloccato |
| 2/6 | qualsiasi | **WATCH** |
| <= 1/6 | qualsiasi | **SKIP** |

Gates (4): VIX < 35, Benchmark EMA20 > EMA50, ADX >= 10 su CSSPX.MI, Correlazione pairwise < 0.7

---

## Parametri Tuned (Optuna WFA)

| Parametro | Originale | Tuned | Motivazione |
| :-- | :-- | :-- | :-- |
| `rsi_threshold` | 50 | **35** | Modo WFA (3/8 finestre) |
| `mfi_threshold` | 50 | **40** | Modo WFA (4/8 finestre), MFI length 20 |
| `vix_threshold` | 25 | **35** | Gate meno restrittivo, modo WFA (3/8 finestre) |
| `adx_threshold` | 20 | **10** | Rilassamento consistente (4/8 finestre) |
| `go_threshold` | 5 | **3** | Modo WFA (4/8 finestre) |

**Validazione Optuna WFA (8 finestre OOS):**
- Avg OOS return: -0.45% per finestra (3/8 finestre profittevoli)
- Parametri migliorano marginalmente vs config originale (-0.45% vs -0.52%)
- Rischio overfitting: MODERATO (efficiency ratio 0.27)
- Universo limitato (7 ETF) riduce la significativita statistica
- La strategia tecnica pura ha edge limitato sugli ETF settoriali — i prompt Perplexity (catalyst + rotation) restano il filtro principale

---

## Position Sizing (cash, no leva)

```
shares = min(
    (€4.000 × 1.5%) / (ATR × 1.5),         # risk-based (€60 rischio)
    (€4.000 × 40%) / prezzo                 # capital cap (€1.600)
)
```

Commissione: €2.95/trade (round-trip €5.90)

---

## ETF Disponibili (Borsa Italiana)

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

## Regole Specifiche ETF

- **EUR/USD**: EUR in rafforzamento erode rendimenti ETF con sottostante USD
- **Correlazione**: se pairwise > 0.7, dimezzare il size combinato
- **Max posizioni**: 3 ETF contemporanei
- **No entry dopo le 16:30 CET**
- **Commissioni**: €2.95/trade (considerare nel breakeven)
