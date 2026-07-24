#!/usr/bin/env python3
"""Approximate backtest of Quantum Queen X recovered portfolio.

Supports asset presets: XAU | NAS100 | US30 | ATR_AUTO
(scales TP/grid vs gold point distances; remaps sessions for US indices).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

# Gold-native: digits=2 → TP/grid = raw_points * 0.01
GOLD_POINT = 0.01


@dataclass
class AssetConfig:
    name: str
    scale: float  # multiplies gold price distances (TP/grid)
    point_value_per_lot: float
    us_index_hours: bool
    use_atr: bool = False
    atr_ref: float = 4.0
    atr_period: int = 14
    lot_mode: str = "auto_high"


ASSETS: Dict[str, AssetConfig] = {
    "XAU": AssetConfig("XAU", 1.0, 100.0, False),
    "NAS100": AssetConfig("NAS100", 8.0, 1.0, True),
    "US30": AssetConfig("US30", 13.0, 1.0, True),
    "ATR_AUTO": AssetConfig("ATR_AUTO", 1.0, 1.0, True, use_atr=True),
}


@dataclass
class Profile:
    number: int
    family: int
    first_tf: int
    first_period: int
    first_upper: float
    first_lower: float
    second_tf: int
    second_period: int
    second_upper: float
    second_lower: float
    session_start: int
    session_end: int
    native_dir: int
    tp_base: int
    grid_base: int
    orders_max: int


PROFILES: List[Profile] = [
    Profile(1, 1, 6, 18, 0.7, 0.3, 15, 16, 0.7, 0.3, 22, 24, 1, 50, 150, 25),
    Profile(8, 4, 5, 12, 0.5, 0.3, 60, 20, 0.9, 0.3, 6, 12, 1, 150, 150, 25),
    Profile(10, 5, 10, 20, 0.7, 0.3, 15, 10, 0.9, 0.3, 22, 23, 1, 200, 300, 15),
    Profile(12, 6, 12, 10, 0.7, 0.1, 15, 20, 0.7, 0.3, 8, 10, -1, 100, 200, 25),
]


@dataclass
class Position:
    side: int
    entry: float
    volume: float
    open_time: int
    strategy: int


@dataclass
class Closed:
    strategy: int
    side: int
    entry: float
    exit: float
    volume: float
    open_time: int
    close_time: int
    profit: float
    basket: int


@dataclass
class Engine:
    asset: AssetConfig
    balance: float = 5000.0
    equity_peak: float = 5000.0
    dd_lock: bool = False
    dd_limit_pct: float = 25.0
    positions: Dict[int, List[Position]] = field(default_factory=dict)
    closed: List[Closed] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)
    fixed_lot: float = 0.01
    current_scale: float = 1.0

    def lot(self) -> float:
        mode = self.asset.lot_mode
        if mode == "fixed":
            return self.fixed_lot
        if mode == "auto_low_medium":
            return max(0.01, round(self.balance / 100000.0, 2))
        if mode == "auto_medium":
            return max(0.01, round(self.balance / 60000.0, 2))
        return max(0.01, round(self.balance / 55250.0, 2))

    def pv(self) -> float:
        return self.asset.point_value_per_lot

    def floating(self, price: float) -> float:
        pnl = 0.0
        for legs in self.positions.values():
            for p in legs:
                delta = (price - p.entry) if p.side > 0 else (p.entry - price)
                pnl += delta * p.volume * self.pv()
        return pnl

    def equity(self, price: float) -> float:
        return self.balance + self.floating(price)

    def close_strategy(self, sid: int, price: float, ts: int) -> None:
        legs = self.positions.get(sid) or []
        if not legs:
            return
        basket = len(legs)
        for p in legs:
            delta = (price - p.entry) if p.side > 0 else (p.entry - price)
            profit = delta * p.volume * self.pv()
            self.balance += profit
            self.closed.append(
                Closed(
                    strategy=sid,
                    side=p.side,
                    entry=p.entry,
                    exit=price,
                    volume=p.volume,
                    open_time=p.open_time,
                    close_time=ts,
                    profit=profit,
                    basket=basket,
                )
            )
        self.positions[sid] = []

    def close_all(self, price: float, ts: int) -> None:
        for sid in list(self.positions.keys()):
            self.close_strategy(sid, price, ts)


def aggregate_tf(m1: List[dict], minutes: int) -> List[dict]:
    out: List[dict] = []
    bucket = None
    cur = None
    for b in m1:
        t = int(b["time"])
        key = t - (t % (minutes * 60))
        if bucket != key:
            if cur:
                out.append(cur)
            bucket = key
            cur = {
                "time": key,
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
            }
        else:
            cur["high"] = max(cur["high"], b["high"])
            cur["low"] = min(cur["low"], b["low"])
            cur["close"] = b["close"]
    if cur:
        out.append(cur)
    return out


def demarker(bars: List[dict], period: int) -> List[Optional[float]]:
    n = len(bars)
    demax = [0.0] * n
    demin = [0.0] * n
    for i in range(1, n):
        up = bars[i]["high"] - bars[i - 1]["high"]
        dn = bars[i - 1]["low"] - bars[i]["low"]
        demax[i] = up if up > 0 else 0.0
        demin[i] = dn if dn > 0 else 0.0
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        smax = sum(demax[i - period + 1 : i + 1])
        smin = sum(demin[i - period + 1 : i + 1])
        den = smax + smin
        out[i] = 0.0 if den == 0 else smax / den
    return out


def atr_series(m1: List[dict], period: int) -> List[Optional[float]]:
    n = len(m1)
    atr: List[Optional[float]] = [None] * n
    if n < 2:
        return atr
    trs = [0.0] * n
    for i in range(1, n):
        trs[i] = max(
            m1[i]["high"] - m1[i]["low"],
            abs(m1[i]["high"] - m1[i - 1]["close"]),
            abs(m1[i]["low"] - m1[i - 1]["close"]),
        )
    if n <= period:
        return atr
    first = sum(trs[1 : period + 1]) / period
    atr[period] = first
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + trs[i]) / period
    return atr


def threshold_dir(value: float, upper: float, lower: float) -> int:
    if value > upper:
        return 1
    if value < lower:
        return -1
    return 0


def is_nfp_friday(ts: int) -> bool:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.weekday() == 4 and dt.day <= 7


def session_ok(p: Profile, hour: int, us_hours: bool) -> bool:
    if us_hours:
        return 13 <= hour < 21
    return p.session_start <= hour < p.session_end


def build_dem_maps(m1: List[dict], profiles: List[Profile]):
    needed: Dict[Tuple[int, int], None] = {}
    for p in profiles:
        needed[(p.first_tf, p.first_period)] = None
        needed[(p.second_tf, p.second_period)] = None
    maps: Dict[Tuple[int, int], Dict[int, float]] = {}
    for tf, period in needed:
        bars = aggregate_tf(m1, tf)
        dem = demarker(bars, period)
        m: Dict[int, float] = {}
        for i in range(1, len(bars)):
            if dem[i - 1] is None:
                continue
            m[int(bars[i]["time"])] = float(dem[i - 1])
        maps[(tf, period)] = m
    return maps


def dem_at(maps, tf: int, period: int, ts: int) -> Optional[float]:
    m = maps[(tf, period)]
    key = ts - (ts % (tf * 60))
    return m.get(key)


def resolve_scale(asset: AssetConfig, atr_val: Optional[float]) -> float:
    if asset.use_atr:
        if atr_val is None or atr_val <= 0 or asset.atr_ref <= 0:
            return 1.0
        return max(0.25, atr_val / asset.atr_ref)
    return asset.scale


def run_backtest(
    m1: List[dict],
    asset: AssetConfig,
    initial: float = 5000.0,
) -> Engine:
    eng = Engine(asset=asset, balance=initial, equity_peak=initial, current_scale=asset.scale)
    for p in PROFILES:
        eng.positions[p.number] = []

    maps = build_dem_maps(m1, PROFILES)
    atrs = atr_series(m1, asset.atr_period) if asset.use_atr else [None] * len(m1)
    last_entry_bar = {p.number: 0 for p in PROFILES}

    for i, b in enumerate(m1):
        ts = int(b["time"])
        price = float(b["close"])
        high = float(b["high"])
        low = float(b["low"])
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hour = dt.hour
        mt5_dow = (dt.weekday() + 1) % 7
        scale = resolve_scale(asset, atrs[i] if atrs else None)
        eng.current_scale = scale

        eq = eng.equity(price)
        if eq > eng.equity_peak:
            eng.equity_peak = eq
        if not eng.dd_lock and eng.equity_peak > 0:
            dd_pct = 100.0 * (eng.equity_peak - eq) / eng.equity_peak
            if dd_pct >= eng.dd_limit_pct:
                eng.close_all(price, ts)
                eng.dd_lock = True

        if eng.dd_lock:
            eng.equity_curve.append(
                {"time": ts, "balance": eng.balance, "equity": eng.equity(price), "positions": 0}
            )
            continue

        for p in PROFILES:
            if eng.positions[p.number]:
                continue
            bar_key = ts - (ts % (p.first_tf * 60))
            if bar_key == last_entry_bar[p.number]:
                continue
            last_entry_bar[p.number] = bar_key

            if not session_ok(p, hour, asset.us_index_hours):
                continue
            if mt5_dow == 0 or mt5_dow == 6:
                continue
            if mt5_dow == 5 and hour >= 22:
                continue
            if is_nfp_friday(ts):
                continue

            d1 = dem_at(maps, p.first_tf, p.first_period, ts)
            d2 = dem_at(maps, p.second_tf, p.second_period, ts)
            if d1 is None or d2 is None:
                continue
            s1 = threshold_dir(d1, p.first_upper, p.first_lower)
            s2 = threshold_dir(d2, p.second_upper, p.second_lower)
            if s1 == 0 or s1 != s2:
                continue
            if p.native_dir > 0 and s1 < 0:
                continue
            if p.native_dir < 0 and s1 > 0:
                continue

            eng.positions[p.number].append(
                Position(side=s1, entry=price, volume=eng.lot(), open_time=ts, strategy=p.number)
            )

        for p in PROFILES:
            legs = eng.positions[p.number]
            if not legs:
                continue
            side = legs[0].side
            vol_sum = sum(x.volume for x in legs)
            be = sum(x.entry * x.volume for x in legs) / vol_sum
            tp_dist = p.tp_base * GOLD_POINT * scale
            tp = be + tp_dist if side > 0 else be - tp_dist
            hit = (side > 0 and high >= tp) or (side < 0 and low <= tp)
            if hit:
                eng.close_strategy(p.number, tp, ts)
                continue
            if len(legs) >= p.orders_max:
                continue
            last_ref = legs[0].entry
            for x in legs:
                if side > 0:
                    last_ref = min(last_ref, x.entry)
                else:
                    last_ref = max(last_ref, x.entry)
            grid_dist = p.grid_base * GOLD_POINT * scale
            grid_px = last_ref - grid_dist if side > 0 else last_ref + grid_dist
            add = (side > 0 and low <= grid_px) or (side < 0 and high >= grid_px)
            if add:
                eng.positions[p.number].append(
                    Position(
                        side=side,
                        entry=grid_px,
                        volume=eng.lot(),
                        open_time=ts,
                        strategy=p.number,
                    )
                )

        npos = sum(len(v) for v in eng.positions.values())
        eng.equity_curve.append(
            {
                "time": ts,
                "balance": eng.balance,
                "equity": eng.equity(price),
                "positions": npos,
            }
        )

    if any(eng.positions.values()):
        eng.close_all(m1[-1]["close"], int(m1[-1]["time"]))
    return eng


def summarize(eng: Engine) -> dict:
    trades = eng.closed
    if not trades:
        return {"n": 0, "asset": eng.asset.name}
    wins = [t for t in trades if t.profit > 0]
    losses = [t for t in trades if t.profit <= 0]
    peak = 0.0
    max_dd = 0.0
    max_dd_pct = 0.0
    for e in eng.equity_curve:
        peak = max(peak, e["equity"])
        dd = peak - e["equity"]
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = 100.0 * dd / peak if peak else 0.0
    by_s: Dict[int, List[Closed]] = {}
    for t in trades:
        by_s.setdefault(t.strategy, []).append(t)
    per_strategy = {
        f"S{sid:02d}": {
            "n": len(ts_),
            "net": round(sum(x.profit for x in ts_), 2),
            "wr": round(sum(1 for x in ts_ if x.profit > 0) / len(ts_), 4),
        }
        for sid, ts_ in sorted(by_s.items())
    }
    return {
        "asset": eng.asset.name,
        "distance_scale": eng.asset.scale if not eng.asset.use_atr else "ATR/ATR_ref",
        "us_index_hours": eng.asset.us_index_hours,
        "set": "IC Markets RAW HIGH RISK (S01,S08,S10,S12)",
        "lots": "Auto Lots High (balance/55250)",
        "initial_balance": 5000.0,
        "final_balance": round(eng.balance, 2),
        "net_profit": round(eng.balance - 5000.0, 2),
        "n_closed_legs": len(trades),
        "winrate": round(len(wins) / len(trades), 4),
        "avg_profit": round(mean(t.profit for t in trades), 2),
        "avg_win": round(mean(t.profit for t in wins), 2) if wins else 0,
        "avg_loss": round(mean(t.profit for t in losses), 2) if losses else 0,
        "profit_factor": round(
            sum(t.profit for t in wins) / abs(sum(t.profit for t in losses)), 3
        )
        if losses and sum(t.profit for t in losses) != 0
        else None,
        "median_duration_min": round(
            median([(t.close_time - t.open_time) / 60 for t in trades]), 2
        ),
        "max_equity_dd_usd": round(max_dd, 2),
        "max_equity_dd_pct": round(max_dd_pct, 2),
        "dd_lock_triggered": eng.dd_lock,
        "max_concurrent_legs": max((e["positions"] for e in eng.equity_curve), default=0),
        "per_strategy": per_strategy,
        "disclaimer": (
            "Recovered QQX approx; not official ex5. Index presets scale TP/grid "
            "and use US hours 13-20 UTC. Need matching M1 bars for real index BT."
        ),
    }


def main():
    ap = argparse.ArgumentParser(description="QQX recovered multi-asset backtest")
    ap.add_argument("--asset", default="XAU", choices=sorted(ASSETS.keys()))
    ap.add_argument("--bars", default="", help="M1 JSON path (default data/xau_m1.json)")
    ap.add_argument("--list-assets", action="store_true")
    ap.add_argument("--risk", default="high", choices=["low_medium", "medium", "high", "fixed"])
    args = ap.parse_args()

    if args.list_assets:
        for k, a in ASSETS.items():
            print(
                f"{k}: scale={a.scale} pv={a.point_value_per_lot} "
                f"us_hours={a.us_index_hours} atr={a.use_atr}"
            )
        return

    bars_path = Path(args.bars) if args.bars else ROOT / "data" / "xau_m1.json"
    m1 = sorted(json.loads(bars_path.read_text()), key=lambda b: b["time"])
    asset = ASSETS[args.asset]
    risk_map = {
        "low_medium": "auto_low_medium",
        "medium": "auto_medium",
        "high": "auto_high",
        "fixed": "fixed",
    }
    asset.lot_mode = risk_map[args.risk]

    eng = run_backtest(m1, asset, 5000.0)
    report = summarize(eng)
    report["bars_file"] = str(bars_path)
    report["window_utc"] = [
        datetime.fromtimestamp(m1[0]["time"], timezone.utc).isoformat(),
        datetime.fromtimestamp(m1[-1]["time"], timezone.utc).isoformat(),
    ]
    out = Path(__file__).resolve().parent / "report.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
