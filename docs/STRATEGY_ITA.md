# ITA CFD Strategy — Prompts & Parameters

> CFD su azioni FTSE MIB via broker. Leva 5:1 ESMA. Capitale: €1.000. Benchmark: ETFMIB.MI.

---

## Workflow ITA

### 08:00 — Prompt 1 ITA: Market Context + Catalyst (Perplexity)

> Lo script scansiona tutti i 40 FTSE MIB. Prompt 1 serve solo per contesto macro e catalyst.

```
Agisci come analista istituzionale su Borsa Italiana / FTSE MIB.
Cerca notizie in tempo reale. Oggi e [DATA].

CONTESTO: Faccio swing trading CFD (3-7 sessioni, leva 5:1 broker)
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

### 08:30 — Script ITA (automatico)

```bash
python main.py --mode ita    # scansiona tutti i 40 titoli FTSE MIB
```

Lo script:
1. Scansiona tutti i 40 titoli nel config
2. Calcola i 6 check + 2 gate per ciascuno
3. Genera un **PDF report** con i **top 5** ticker (tabella, action plan, Perplexity prompt)
4. Invia il PDF su Telegram con caption riassuntiva (top 5 + gates)

### Prompt 2 ITA: Deep Dive (nel PDF, pagina dedicata)

Il PDF include una pagina "Perplexity Prompt (copy & paste)" in font monospaced,
pronta da copiare. Contiene i ticker GO/WATCH del top 5 con 3 domande deal-breaker:

| # | Domanda | Logica |
| :-- | :-- | :-- |
| 1 | **Earnings Risk** | Trimestrali nei prossimi 7gg? = veto automatico |
| 2 | **Catalyst** | C'e un catalyst attivo 48h con gambe multiday? |
| 3 | **Evento Killer** | Evento specifico che inverte il titolo prima del TP1? |

**Regole di decisione:**
- Earnings → SKIP automatico
- No catalyst + Evento → SKIP
- Catalyst debole → WAIT
- Catalyst attivo + No evento → ENTRY
- Per bancari: nota su spread BTP-Bund se in allargamento

### 09:00 — ITA CFD Entry (broker app)

| Entry Method | Finestra | Condizione |
| :-- | :-- | :-- |
| GAP_UP | 09:00-09:15 | Gap >= 0.5% sopra EMA20 + max giorno precedente |
| PULLBACK | 09:15+ | Rimbalzo su EMA20 Daily |
| ORB | 09:15+ | Breakout Opening Range H1 con volume >= 1.5x |
| BONE_ZONE | 09:15+ | Dip nella zona EMA 9-20, candela verde sopra EMA9 |
| WAIT | — | Nessun setup → skip |

---

## Score ITA (parametri Optuna WFA)

| Score | Gates OK | Azione |
| :-- | :-- | :-- |
| >= 3/6 | tutti OK | **GO** — prepara ordini su broker |
| >= 3/6 | almeno 1 FAIL | **WATCH** — gate ha bloccato |
| 2/6 | qualsiasi | **WATCH** |
| <= 1/6 | qualsiasi | **SKIP** |

Gates: VIX < 35, ADX >= 15 su ETFMIB.MI

---

## Parametri Tuned (Optuna WFA)

| Parametro | Originale | Tuned | Motivazione |
| :-- | :-- | :-- | :-- |
| `rsi_threshold` | 50 | **45** | Cattura entry nella fase iniziale del trend |
| `mfi_threshold` | 50 | **40** | Filtro meno restrittivo sui flussi (45→40 via Optuna WFA) |
| `vix_threshold` | 25 | **35** | Gate VIX troppo stretto, bloccava trade validi in fear moderata |
| `adx_threshold` | 20 | **15** | Lieve rilassamento, filtra ancora mercati piatti (Optuna WFA) |
| `go_threshold` | 5 | **3** | Perfettamente stabile su tutte le 8 finestre WFA (5→4→3) |

**Validazione Optuna WFA (8 finestre OOS):**
- Avg OOS return: +1.84% per finestra (7/8 finestre profittevoli)
- Unica finestra negativa: 2022-H1 (guerra Ucraina + rialzo tassi)
- GO=3 selezionato in tutte le 8 finestre (massima stabilita)
- VIX gate ON confermato critico (protezione bear market)

---

## PineScript — ITA CFD Validator v1.2

```
pinescript/ita_cfd_validator.pine
```

Parametri: RSI 45, MFI 40, VIX 35, ADX 15, GO >= 3

Setup TradingView:
1. Apri un titolo italiano (`MIL:UCG`) o ETF (`MIL:DFND`)
2. Pine Editor → incolla → Add to Chart
3. Configura benchmark: `MIL:ETFMIB` (ITA) o `MIL:CSSPX` (ETF)
4. Alert: tasto destro → "Add Alert" per GO/WATCH/Chandelier Exit

---

## Ticker di Riferimento (FTSE MIB)

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

Benchmark: `ETFMIB.MI` (Lyxor FTSE MIB ETF)
