# MT5 Realistic Backtester + Monte Carlo Forward (XAUUSD)

Tool in Python per stress-testare la logica di un Expert Advisor su **XAUUSD** **come se fosse live**, e per fare **backtest in avanti su dati generati casualmente** (Monte Carlo). Serve a ridurre il rischio di fidarsi di backtest manipolati / curve-fitted.

## Perché

Molti EA venduti su Gold mostrano equity curve perfette perché il tester MT5 è impostato in modo ottimistico (open prices, spread 0, zero latency, overfitting su un periodo).

Questo progetto fa due cose utili:

1. **Esecuzione realistica XAUUSD**: spread tipico gold, slippage, commissioni, latenza, stop level, stop-out (`point=0.01`, `contract_size=100`).
2. **Forward Monte Carlo su XAUUSD**: genera N percorsi casuali intorno a ~2650$ (GBM / jump / mean-reversion / regime) e ripete il backtest.

> Non esegue file `.ex5`. Devi **portare la logica dell’EA** in una classe Python `Strategy`. Per i report MT5 già pronti c’è anche `audit`.

## Setup

```bash
cd mt5_realistic_backtester
python3 -m pip install -r requirements.txt
```

## Uso rapido — Monte Carlo XAUUSD su dati casuali

```bash
python3 main.py montecarlo --symbol XAUUSD --runs 40 --bars 1500 --model jump
```

Default già impostati su XAUUSD (non serve forzare EURUSD).

## Singolo backtest XAUUSD

```bash
python3 main.py backtest --random --model regime
python3 main.py backtest --ohlc mio_xauusd_m1.csv
python3 main.py backtest --ticks ticks_xauusd.csv
```

## Audit report MT5

```bash
python3 main.py audit examples/sample_mt5_report.html
```

## Spec XAUUSD usate

| Parametro | Default |
|-----------|---------|
| Prezzo start | 2650.0 |
| Point / digits | 0.01 / 2 |
| Contract size | 100 oz |
| Spread | ~25 points |
| Lot strategia esempio | 0.01 |
| SL / TP | 400 / 600 points |
| Vol annualizzata path | 0.16 |

## Porta il tuo EA

```python
from mt5_backtester import Strategy, xauusd, run_monte_carlo, MonteCarloConfig
from mt5_backtester.models import Side

class MyGoldEA(Strategy):
    name = "my_gold_ea"

    def on_tick(self, broker, tick, bars):
        if len(bars) < 50:
            return
        if not broker.positions and bars[-1]["close"] > bars[-2]["close"]:
            point = broker.cfg.point
            broker.submit_market(
                Side.BUY, 0.01,
                sl=tick.bid - 400 * point,
                tp=tick.ask + 600 * point,
            )

sym = xauusd(bars=1500, seed=42)
report = run_monte_carlo(lambda: MyGoldEA(), MonteCarloConfig(runs=50, path=sym.path, realistic=sym.broker))
print(report.realistic.verdict)
```

## Limiti onesti

- Dati casuali **non** sono il mercato reale: servono a stress-test e a smascherare overfitting banale.
- Broker gold differiscono su digit (2 vs 3), contract size e commissioni: adatta `symbols.xauusd()` al tuo broker.
- Per validazione seria: Monte Carlo **+** forward demo reale **+** out-of-sample su tick XAUUSD veri.
