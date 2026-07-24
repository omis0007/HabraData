# Backtest Report — GoldMRScalperGrid

**Symbol:** XAUUSD (M1)  
**Period:** 2026-04-14 → 2026-07-17 (UTC)  
**Initial balance (sim):** $5,000  
**Lot:** 0.05  

## Results (bot)

| Metric | Value |
|---|---:|
| Net profit | **+$4,100.25** |
| Final balance | **$9,100.25** |
| Trades | 760 |
| Winrate | **85.13%** |
| Avg profit / trade | +$5.40 |
| Median TP distance | $1.50 |
| Median duration | 1.0 min |
| Max concurrent positions | 3 |
| Buy / Sell mix | 52.6% buy |

## Comparison vs live account (same window)

| Metric | Live account | Backtest bot |
|---|---:|---:|
| Trades | 186 | 760 |
| Winrate | 83.3% | 85.1% |
| Median TP | $1.48 | $1.50 |
| Median duration | 2.25 min | 1.0 min |
| Avg profit / trade | +$5.26 | +$5.40 |
| Net profit | +$979.28 | +$4,100.25 |

## Parameters used

- Stochastic(14,3): buy ≤ 15 / sell ≥ 85  
- EMA stretch min: 8.0 USD  
- Move-against (3 bars): 2.5 USD  
- Solo TP: 1.5 USD  
- Grid step: 6.0 USD  
- Basket TP: 0.15 USD beyond average  
- Max positions: 3  
- Hours UTC: 2–6, 9–11, 15–18  

## Notes

1. Style is aligned with the live account (WR, TP, avg $/trade).  
2. The bot is **more aggressive** (more trades) → higher net profit in sim, not a tick-perfect clone.  
3. No commission/spread/slippage modeled beyond OHLC M1 simulation.  
4. Live account also received copy-trading `CPfee` income (not included in trade PnL comparison above).  

## How to reproduce

```bash
python3 gold_scalper/backtest/run_backtest.py
# → gold_scalper/backtest/report.json
```
