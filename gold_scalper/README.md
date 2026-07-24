# Gold MR Scalper Grid

Bot ricostruito dallo storico investitore Equiti `1013596414` su `XAUUSD.pr`.

## Strategia

Mean-reversion su oro + griglia **stessa direzione** se il trade va contro:

1. Stochastic(14,3) estremo (`<=15` buy / `>=85` sell)
2. Stretch vs EMA(20) ≥ ~8 USD
3. Ultime 3 barre M1 contro la direzione (fade)
4. TP singolo ~1.5 USD
5. Se avverso ≥ ~6 USD → aggiunge posizione stessa direzione (max 3)
6. Basket: chiusura vicino alla media ponderata (+0.15 USD)
7. Filtro ore UTC: 2–6, 9–11, 15–18

Sul conto live: magic diversi per trade + `CPfee[pf]` → provider di copy trading, non EA Market con magic fisso.

## Risultati backtest (finestra M1 disponibile)

Confronto vs storico conto sulla stessa finestra (~14 Apr – 17 Lug 2026):

| Metrica | Conto | Bot (tuned) |
|---|---:|---:|
| Winrate | ~83% | ~85% |
| TP mediano | ~1.48 | 1.50 |
| Durata mediana | ~2.3 min | ~1.0 min |
| Profit netto | +979 | +4100* |
| N. trade | 186 | 760 |

\*Il bot è **più aggressivo** (più segnali): lo stile è allineato, la selettività del provider live non è replicata al 100%.

Parametri tuned in `backtest/best_params.json` e default dell’EA.

## Uso

```bash
# Backtest Python
python3 gold_scalper/backtest/run_backtest.py

# MT5: copia ea/GoldMRScalperGrid.mq5 in MQL5/Experts, compila, allega a XAUUSD M1
```

## Disclaimer

Ricostruzione statistica da deal history. Non è garanzia di profitto; spread/commissioni/slippage reali possono cambiare i risultati.
