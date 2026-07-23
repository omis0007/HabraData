# MT5 Realistic Backtester + Monte Carlo Forward

Tool in Python per stress-testare la logica di un Expert Advisor **come se fosse live**, e soprattutto per fare **backtest in avanti su dati generati casualmente** (Monte Carlo). Serve a ridurre il rischio di fidarsi di backtest manipolati / curve-fitted.

## Perché

Molti EA venduti mostrano equity curve perfette perché il tester MT5 è impostato in modo ottimistico (open prices, spread 0, zero latency, overfitting su un periodo).

Questo progetto fa due cose utili:

1. **Esecuzione realistica**: spread, slippage, commissioni, latenza, stop level, stop-out.
2. **Forward Monte Carlo**: genera N percorsi di prezzo casuali (GBM / jump / mean-reversion / regime) e ripete il backtest. Se l’EA “miracoloso” collassa sui path random, l’edge era probabilmente finto.

> Non esegue file `.ex5`. Devi **portare la logica dell’EA** in una classe Python `Strategy` (pattern simile a `OnTick`). Per i report MT5 già pronti c’è anche `audit`.

## Setup

```bash
cd mt5_realistic_backtester
python3 -m pip install -r requirements.txt
```

## Uso rapido — Monte Carlo su dati casuali

```bash
python3 main.py montecarlo --runs 40 --bars 1500 --model jump
```

Output chiave:
- `verdict`: `ROBUSTA` / `RISCHIOSA` / `FRAGILE` / `INCONCLUSIVA`
- confronto **realistic vs optimistic** (quanto il backtest “da brochure” gonfia i numeri)
- percentili di return e max drawdown

Modelli path:
- `gbm` — random walk geometrico
- `jump` — GBM + salti (news shock)
- `ou` — mean reversion
- `regime` — alterna fasi calme/volatili

## Singolo backtest

```bash
# path casuale
python3 main.py backtest --random --model regime

# da CSV OHLC esportato da MT5
python3 main.py backtest --ohlc mio_eurusd_m1.csv

# da tick CSV (time,bid,ask)
python3 main.py backtest --ticks ticks.csv

# confronto con modalità ottimistica
python3 main.py backtest --random --optimistic
```

## Audit report MT5

Esporta il report HTML dal Strategy Tester e:

```bash
python3 main.py audit report.htm
```

Cerca red-flag tipo: Open prices only, spread 0, delay 0, profit factor estremo, ottimizzazione genetica senza walk-forward.

## Porta il tuo EA

```python
from mt5_backtester import Strategy
from mt5_backtester.models import Side

class MyEA(Strategy):
    name = "my_ea"

    def on_tick(self, broker, tick, bars):
        # bars = solo candele CHIUSE (niente look-ahead)
        if len(bars) < 50:
            return
        if not broker.positions and bars[-1]["close"] > bars[-2]["close"]:
            broker.submit_market(Side.BUY, 0.1, sl=tick.bid - 0.0015, tp=tick.ask + 0.0025)
```

Poi nel Monte Carlo:

```python
from mt5_backtester import run_monte_carlo, MonteCarloConfig

report = run_monte_carlo(lambda: MyEA(), MonteCarloConfig(runs=50))
print(report.realistic.verdict)
```

## Limiti onesti

- Dati casuali **non** sono il mercato reale: servono a stress-test e a smascherare overfitting banale.
- Un EA robusto su Monte Carlo può comunque perdere live (costi, liquidità, news, broker).
- Per validazione seria: Monte Carlo **+** forward demo reale **+** out-of-sample su tick veri.

## Layout

```
mt5_realistic_backtester/
  main.py
  mt5_backtester/
    broker.py          # esecuzione realistica
    engine.py          # backtest single-path
    random_paths.py    # generatori stocastici
    montecarlo.py      # forward N-path
    report_audit.py    # audit HTML MT5
    strategies/        # esempi EA
```
