# Quantum Queen X v4.1 — backtest approssimato

Sorgente: `Quantum_Queen_X_v4.1_recovered.mq5.txt` (portfolio recovered, dual `iDeMarker` + grid).

**Non è il binario ufficiale `.ex5`** — logica ricostruita; OHLC M1 senza spread/commissioni.

## Come lanciare

```bash
python3 gold_scalper/quantum_queen/backtest_qqx.py
```

## Setup simulato

- Symbol: XAU (dati `gold_scalper/data/xau_m1.json`)
- Finestra: 2026-04-14 → 2026-07-17 UTC (~3 mesi)
- Saldo iniziale: **$5.000**
- Set: **IC Markets RAW HIGH RISK** → S01, S08, S10, S12
- Lotti: Auto **High** (`balance/55250`)
- DD lock: 25% equity
