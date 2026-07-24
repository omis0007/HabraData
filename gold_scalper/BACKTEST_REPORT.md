# Backtest Report — GoldMRScalperGrid (matched)

**Symbol:** XAUUSD M1  
**Window:** 2026-04-14 → 2026-07-17 UTC  
**Initial balance (sim):** $5,000 · **Lot:** 0.05  
**Entry filter:** Stochastic (+ DeMarker opzionale, default off)  

## Confronto diretto (stessa finestra)

| Metrica | Conto live | Bot (DeM off) |
|---|---:|---:|
| Trade | **186** | **194** |
| Winrate | **83.3%** | **85.1%** |
| TP mediano | **$1.48** | **$1.50** |
| Buy % | **39.8%** | **40.2%** |
| Profit medio/trade | **+$5.26** | **+$5.83** |
| Profit netto trade | **+$979** | **+$1,130** |
| Max posizioni | **5** | **5** |
| Durata mediana | 2.25 min | 1.0 min |
| Max DD equity (trading) | **~$706 (~7%)** | **~$770** |

## Drawdown — chiarimento

Sul **conto live**:
- **Equity DD ≈ 40.4% ($3,159)** — reale, con griglia fino a 5 posizioni (picco 26 May 2026)
- **Balance DD ≈ 37% ($3,001)** — in gran parte **prelievi** (`trf:`), non solo trading
- Il conto ha anche incassato **CPfee copy ≈ +$8,922** (non nel bot)

Sul **bot matched** (filtri più stretti per eguagliare il n° trade):
- **Equity DD ≈ 12.9% ($770)** — più basso perché stretch/filtri riducono le griglie profonde
- Se allento i filtri per “inseguire” il DD 40%, esplode il n° trade e si allontana dal conto

## Cosa combacia / cosa no

**Allineato:** n° trade, winrate, TP, buy%, avg win/loss, profit netto.  
**Diverso:** durata (sim M1 chiude TP troppo in fretta) e DD (conto live più “profondo” in griglia; bot matched più selettivo).

## Parametri matched

- Stoch(14,3): ≤10 / ≥90  
- DeMarker(14) opzionale (default off; `InpUseDeMarker` / `use_demarker`)  
- Stretch EMA20 ≥ 14 USD  
- Move3 against ≥ 5 USD  
- Solo TP 1.5 · Grid 6.0 · Basket TP 0.4 · Max pos 5  

## Riproduzione

```bash
python3 gold_scalper/backtest/run_backtest.py
```
