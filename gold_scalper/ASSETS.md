# Asset presets

The EA and Python backtest share these profiles:

| Preset | Input MT5 | Distances | Hours UTC | Typical symbols |
|---|---|---|---|---|
| **XAU** | `ASSET_XAU` | TP 1.5 · grid 6 · stretch 14 | 2–6, 9–11, 15–18 | XAUUSD, GOLD |
| **NAS100** | `ASSET_NAS100` | TP 12 · grid 40 · stretch 55 | 13–20 | NAS100, USTEC, US100 |
| **US30** | `ASSET_US30` | TP 20 · grid 70 · stretch 100 | 13–20 | US30, DJ30 |
| **ATR_AUTO** | `ASSET_ATR_AUTO` | ATR(M1)× gold multipliers | 13–20 | any index/metal |
| **Custom** | `ASSET_CUSTOM` | your inputs | gold hours default | — |

## MT5

1. Compile `ea/GoldMRScalperGrid.mq5`
2. Attach to chart M1 of the symbol
3. Set **Asset profile** = NAS100 / US30 / ATR_AUTO
4. Set **Lot** for that CFD (often 0.10) — verify `$/point` with your broker

`ATR_AUTO` is the safest starting point on a new index: distances scale with volatility.

## Python

```bash
python3 gold_scalper/backtest/run_backtest.py --list-presets
python3 gold_scalper/backtest/run_backtest.py --preset XAU
python3 gold_scalper/backtest/run_backtest.py --preset NAS100 --bars /path/to/nas100_m1.json
python3 gold_scalper/backtest/run_backtest.py --preset US30 --bars /path/to/us30_m1.json
python3 gold_scalper/backtest/run_backtest.py --preset ATR_AUTO --bars /path/to/any_m1.json
```

M1 JSON format: `[{"time": unix, "open":.., "high":.., "low":.., "close":..}, ...]`

## Notes

- Index point value differs by broker (`point_value_per_lot` in presets defaults to `$1/point/lot`).
- Fixed NAS100/US30 distances are starting points — retune after a real Strategy Tester run.
- Without index M1 history in this repo, only the **XAU** preset has a validated backtest here.
