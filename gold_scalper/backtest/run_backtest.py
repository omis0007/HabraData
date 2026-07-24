#!/usr/bin/env python3
"""Run MR scalper backtest (asset presets: XAU, NAS100, US30, ATR_AUTO)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backtest"))

from presets import PRESETS, apply_preset_to_params, list_presets  # noqa: E402
from strategy import Params, run_backtest  # noqa: E402


def load_bars(path: Path):
    return sorted(json.loads(path.read_text()), key=lambda b: b["time"])


def positions_from_deals(deals, t0=None, t1=None):
    trade = [d for d in deals if d.get("symbol") == "XAUUSD.pr"]
    by = defaultdict(list)
    for d in trade:
        by[d["position_id"]].append(d)
    positions = []
    for pid, ds in by.items():
        inn = sorted([d for d in ds if d["entry"] == 0], key=lambda x: x["time"])
        out = [d for d in ds if d["entry"] == 1]
        if not inn or not out:
            continue
        if t0 is not None and not (t0 <= inn[0]["time"] <= t1):
            continue
        positions.append(
            {
                "side": "buy" if inn[0]["type"] == 0 else "sell",
                "tin": inn[0]["time"],
                "tout": out[-1]["time"],
                "pin": inn[0]["price"],
                "pout": out[-1]["price"],
                "pr": sum(float(d.get("profit") or 0) for d in ds),
            }
        )
    return positions


def fingerprint(positions):
    if not positions:
        return {"n_positions": 0}
    durs = [(p["tout"] - p["tin"]) / 60 for p in positions]
    tps = [abs(p["pout"] - p["pin"]) for p in positions]
    wins = sum(1 for p in positions if p["pr"] > 0)
    return {
        "n_positions": len(positions),
        "winrate": wins / len(positions),
        "avg_profit": mean([p["pr"] for p in positions]),
        "sum_profit": sum(p["pr"] for p in positions),
        "median_duration_min": median(durs),
        "median_tp_dist": median(tps),
        "buy_pct": sum(1 for p in positions if p["side"] == "buy") / len(positions),
    }


def bt_fingerprint(eng):
    trades = eng.closed
    if not trades:
        return {"n_positions": 0}
    durs = [(t.close_time - t.open_time) / 60 for t in trades]
    tps = [abs(t.exit - t.entry) for t in trades]
    wins = sum(1 for t in trades if t.profit > 0)
    return {
        "n_positions": len(trades),
        "winrate": wins / len(trades),
        "avg_profit": mean([t.profit for t in trades]),
        "sum_profit": sum(t.profit for t in trades),
        "median_duration_min": median(durs),
        "median_tp_dist": median(tps),
        "buy_pct": sum(1 for t in trades if t.side == "buy") / len(trades),
        "final_balance": eng.balance,
        "max_concurrent_observed": max((e["positions"] for e in eng.equity_curve), default=0),
    }


def main():
    ap = argparse.ArgumentParser(description="MR scalper backtest")
    ap.add_argument(
        "--preset",
        default="XAU",
        help=f"Asset preset: {', '.join(list_presets())}",
    )
    ap.add_argument("--bars", default="", help="Optional M1 JSON path (default: data/xau_m1.json)")
    ap.add_argument("--list-presets", action="store_true")
    args = ap.parse_args()

    if args.list_presets:
        for name, cfg in PRESETS.items():
            print(f"{name}: {cfg.get('note', '')}")
            print(
                f"  TP={cfg.get('solo_tp')} grid={cfg.get('grid_step')} "
                f"stretch={cfg.get('stretch_min')} hours={cfg.get('trade_hours')} "
                f"atr={cfg.get('use_atr')}"
            )
        return

    data = ROOT / "data"
    bars_path = Path(args.bars) if args.bars else data / "xau_m1.json"
    bars = load_bars(bars_path)
    deals = json.loads((data / "account_deals.json").read_text())
    t0, t1 = bars[0]["time"], bars[-1]["time"]
    preset_key = args.preset.upper()
    acct = (
        fingerprint(positions_from_deals(deals, t0, t1))
        if preset_key in ("XAU", "XAUUSD", "GOLD")
        else {}
    )

    params = Params()
    apply_preset_to_params(params, args.preset)
    eng = run_backtest(bars, params)
    bt = bt_fingerprint(eng)

    report = {
        "preset": args.preset,
        "bars_file": str(bars_path),
        "window_utc": [
            datetime.fromtimestamp(t0, timezone.utc).isoformat(),
            datetime.fromtimestamp(t1, timezone.utc).isoformat(),
        ],
        "account_window": acct,
        "params": params.__dict__,
        "backtest": bt,
        "alignment": {
            "winrate_bt_vs_account": [bt.get("winrate"), acct.get("winrate")],
            "tp_bt_vs_account": [bt.get("median_tp_dist"), acct.get("median_tp_dist")],
            "duration_bt_vs_account": [
                bt.get("median_duration_min"),
                acct.get("median_duration_min"),
            ],
            "profit_bt_vs_account": [bt.get("sum_profit"), acct.get("sum_profit")],
            "trades_bt_vs_account": [bt.get("n_positions"), acct.get("n_positions")],
            "notes": (
                f"Preset={args.preset}. DeMarker optional (default off). "
                "Index presets need matching M1 bars for a meaningful result."
            ),
        },
    }

    out = ROOT / "backtest" / "report.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    (ROOT / "backtest" / "best_params.json").write_text(
        json.dumps(params.__dict__, indent=2, default=str)
    )
    print(json.dumps(report["alignment"], indent=2))
    print("preset", args.preset)
    print("account", acct)
    print("backtest", bt)
    print("wrote", out)


if __name__ == "__main__":
    main()
