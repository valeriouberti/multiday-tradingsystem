# Multiday Trading System — ITA CFD + ETF Settoriali

> Due strategie su Borsa Italiana via **Fineco**. Selezione titoli via AI
> (Perplexity Pro, prompt schedulati). Validazione tecnica con Python.
> Holding period: 3-7 sessioni.
>
> | Strategia | Strumento | Leva | Capitale | Benchmark |
> | :-- | :-- | :-- | :-- | :-- |
> | **ITA CFD** | CFD su azioni FTSE MIB | 5:1 ESMA | €1.000 | ETFMIB.MI |
> | **ETF Settoriali** | Cash ETF Borsa Italiana | 1:1 | €4.000 | CSSPX.MI |
> | **Totale** | | | **€5.000** | |

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

### 08:00 — ITA CFD: Prompt 1 + 2 + Script (10 min)

> Tutto in sequenza rapida. I prompt sono schedulati su Perplexity.

#### PROMPT 1 ITA: Selezione Titoli (schedulato)

```
Agisci come analista istituzionale specializzato in azioni italiane
large-cap (FTSE MIB).

Cerca le ultime notizie di mercato in tempo reale e analizza Borsa
Italiana per la sessione di OGGI.

CONTESTO: Faccio trading su azioni italiane large-cap come CFD su Fineco
con leva 5:1. Il mio benchmark e il FTSE MIB. Capitale: €1.000.
Mantengo le posizioni per 3-7 sessioni.

COMPITO: Identifica i 3 titoli italiani piu forti per uno swing trade
multiday basandoti sui catalyst delle ultime 24-48 ore.

Catalyst validi:
- Decisioni BCE (tassi, conferenza stampa — impatto forte su bancari)
- Politica governo italiano (spesa difesa, politica energetica, infrastrutture)
- Trimestrali sopra/sotto le attese dei componenti FTSE MIB
- Rotazione settoriale nei mercati europei
- Operazioni M&A che coinvolgono aziende italiane
- Cambiamenti normativi UE con impatto sull'Italia
- Movimenti materie prime (petrolio → ENI/TEN, rame → industriali)
- Movimenti EUR/USD che amplificano titoli export italiani
- Movimenti spread BTP-Bund (impatto su bancari)
- Sorprese su PIL/PMI Italia

Per OGNI titolo fornisci:
- Il catalyst specifico (con fonte e data)
- Perche ha gambe per piu giorni (non ancora prezzato)

REGOLE RIGIDE:
- Solo componenti FTSE MIB (liquidi, CFD disponibili su Fineco)
- ESCLUDI titoli che pubblicano trimestrali nei prossimi 7 giorni
- ESCLUDI titoli in calo >2% nel premarket
- Preferisci titoli con forza relativa positiva vs FTSE MIB su 5 sessioni
- Considera la direzione dello spread BTP-Bund per i bancari
- Ordina per convinzione: TITOLO 1 = massima convinzione

FORMATO OUTPUT (rigoroso):

## TITOLO 1: [ticker.MI] — [Nome Azienda]
Catalyst: [1-2 frasi, cosa e successo e perche ha gambe multiday]
RS vs FTSE MIB (5gg): [piu forte / piu debole / flat]
Contesto settoriale: [1 frase]

## TITOLO 2: [stesso formato]
## TITOLO 3: [stesso formato]

MACRO VETO: Segnala qualsiasi evento BCE/UE oggi che rende TUTTE le
entry rischiose.
```

#### PROMPT 2 ITA: Deep Dive (schedulato)

```
Sei un analista istituzionale che copre azioni italiane.

Ho intenzione di aprire posizioni CFD multiday (3-7 sessioni, leva 5:1)
su i precedenti titoli italiani:

Per OGNI titolo, esegui una valutazione rapida del rischio:

1. RISCHIO TRIMESTRALI: Pubblicazione utili nei prossimi 10 giorni?
   → Segnala come ⛔ RISCHIO TRIMESTRALE o ✅ OK

2. SENSIBILITA MACRO ITALIA: Prossima riunione BCE, PMI Italia, asta BTP
   che potrebbe invertire il titolo? Quante sessioni mancano?
   → 🟢 LIBERO (>5 sessioni) / 🟡 VICINO (2-5) / 🔴 IMMINENTE (<2)

3. SPREAD BTP-BUND: Livello attuale e direzione.
   Per bancari (ISP, UCG, BAMI): spread in allargamento = negativo.
   → 🟢 IN RESTRINGIMENTO / 🔴 IN ALLARGAMENTO / ➡️ STABILE

4. FLUSSI ISTITUZIONALI: Acquisti/vendite insider recenti, block trade
   rilevanti o comunicazioni Consob negli ultimi 5 giorni?
   → 🟢 ACQUISTO IST / 🔴 VENDITA IST / ➡️ NEUTRALE

5. SHORT INTEREST: Posizioni short significative (registro Consob)?
   → ⚠️ SHORT ELEVATO o ✅ NORMALE

FORMATO OUTPUT (rigoroso, una riga per titolo):
[ticker.MI] | ⛔/✅ Trimestrali | 🟢/🟡/🔴 Macro | 🟢/🔴/➡️ BTP | 🟢/🔴/➡️ Ist | ⚠️/✅ Short
```

#### 08:30 — Script ITA

Aggiorna `config_ita.yaml` con i 3 ticker, poi:

```bash
python main_ita.py
```

→ Se GO: prepara ordini su Fineco per le 09:00.
→ Se WATCH/SKIP: non operare.

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

### 13:00 — ETF: Prompt 1 + 2 (8 min, pausa pranzo, da telefono)

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
| **07:30** | Entrambe | Macro veto | 2 min |
| **07:30** | ETF | Prompt 0 — overnight check | 3 min |
| **08:00** | ITA CFD | Prompt 1 + 2 (schedulati) | 5 min |
| **08:30** | ITA CFD | `python main_ita.py` + aggiorna config | 2 min |
| **09:00** | ITA CFD | Entry su Fineco (GAP_UP/PB/ORB/BZ) | 5 min |
| **13:00** | ETF | Prompt 1 + 2 (schedulati, pausa pranzo) | 8 min |
| **13:20** | ETF | `python main_etf.py` + aggiorna config | 2 min |
| **14:30-16:30** | ETF | Entry su Fineco (buy a mercato) | 5 min |
| **17:00** | Entrambe | Deadline — no entry dopo | 0 min |
| **22:00** | Entrambe | Prompt 3 — exit review + aggiorna Trail | 10 min |

**Tempo totale: ~40 minuti/giorno**

---

## Dettaglio Tecnico

### 6 Check (comuni a entrambe le strategie)

| # | Check | Timeframe | Logica |
| :-- | :-- | :-- | :-- |
| 1 | EMA 20 > EMA 50 | Daily | Trend rialzista |
| 2 | EMA 20 > EMA 50 | Weekly | Trend strutturale |
| 3 | MACD > Signal | Daily | Momentum in accelerazione |
| 4 | RSI > 50 | Daily | Forza relativa positiva |
| 5 | MFI > 50 | Daily | Money Flow Index — flusso istituzionale |
| 6 | RS vs Benchmark | Daily | Titolo/settore batte il benchmark (20d, 5d ROC) |

### Gates

| Gate | ITA CFD | ETF | Effetto |
| :-- | :-- | :-- | :-- |
| VIX < 25 | ✅ | ✅ | GO → WATCH |
| ADX >= 20 su benchmark | ✅ | ✅ | GO → WATCH |
| Benchmark Health (EMA20 > EMA50) | — | ✅ | GO → WATCH |
| Correlazione pairwise < 0.7 | — | ✅ | Dimezza size combinato |

### Score

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
8. **Score <= 3/6**: skip sempre
9. **Position sizing**: usare il numero di shares dello script, mai superare
10. **BTP-Bund spread** (ITA): widening >10bp in un giorno → chiudere bancari
11. **EUR/USD** (ETF): EUR in rafforzamento erode rendimenti ETF con sottostante USD
12. **Max posizioni**: ITA max 3 CFD, ETF max 3 posizioni
13. **Correlazione** (ETF): se pairwise > 0.7, dimezzare il size combinato

---

## PineScript — TradingView

Indicatore per validazione visiva:

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
python main_ita.py                          # ITA CFD (default: config_ita.yaml)
python main_etf.py                          # ETF (default: config_etf.yaml)
python main_ita.py --config custom.yaml     # override
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

---

## Automazione (GitHub Actions)

- ITA: trigger automatico alle 8:30 CET o manuale da GitHub mobile app
- ETF: trigger automatico alle 14:00 CET o manuale da GitHub mobile app
- Input tickers via `workflow_dispatch` (GitHub app → Actions → Run workflow)
- Telegram: il Python script invia il report se i secrets sono configurati
