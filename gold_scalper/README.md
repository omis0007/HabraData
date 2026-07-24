# MR Scalper Grid (XAU + Indices)

Bot ricostruito dallo storico investitore Equiti su `XAUUSD.pr`, con **preset** per indici.

## Preset asset

| Profile | Uso |
|---|---|
| XAU | oro (default, matched live) |
| NAS100 | NAS100 / USTEC |
| US30 | US30 / DJ30 |
| ATR_AUTO | qualsiasi simbolo via ATR(M1) |
| Custom | distanze manuali |

Dettagli: [`ASSETS.md`](ASSETS.md)

## Strategia

Mean-reversion + griglia **stessa direzione**:

1. Stochastic(14,3) estremo
2. Stretch vs EMA(20)
3. Move avverso ultime 3 barre M1
4. TP singolo / grid / basket (da preset o ATR)
5. Filtro ore UTC per asset

## Backtest

```bash
python3 gold_scalper/backtest/run_backtest.py --preset XAU
python3 gold_scalper/backtest/run_backtest.py --list-presets
```

## MT5

Copia `ea/GoldMRScalperGrid.mq5` → Experts, compila, allega a M1, scegli **Asset profile**.

## Disclaimer

Ricostruzione statistica. Spread/commissioni/contract size del CFD cambiano i risultati.
