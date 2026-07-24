# Quantum Queen X — multi-asset (recovered)

**Non è l’`.ex5` ufficiale.** Portfolio recovered + scale per indici.

## Asset profile (MT5)

File: `ea/QuantumQueenX_MultiAsset.mq5`

| Profile | Scale TP/grid | Ore |
|---|---:|---|
| **XAU** | ×1 (nativo) | sessioni strategia |
| **NAS100** | ×8 | 13–20 UTC |
| **US30** | ×13 | 13–20 UTC |
| **ATR_AUTO** | ATR(M1)/4 | 13–20 UTC |
| **Custom** | `InpDistanceScale` | opz. Force US hours |

Compila, allega a M1 del simbolo, scegli **Asset profile**, abilita trading recovered se richiesto dagli interlock.

## Backtest Python

```bash
python3 gold_scalper/quantum_queen/backtest_qqx.py --list-assets
python3 gold_scalper/quantum_queen/backtest_qqx.py --asset XAU --risk high
python3 gold_scalper/quantum_queen/backtest_qqx.py --asset NAS100 --bars nas_m1.json --risk high
python3 gold_scalper/quantum_queen/backtest_qqx.py --asset US30 --bars us30_m1.json --risk high
python3 gold_scalper/quantum_queen/backtest_qqx.py --asset ATR_AUTO --bars any_m1.json
```

Senza M1 di NAS/US30 nel repo, i preset indici su dati oro **non** sono un backtest reale (solo smoke).
