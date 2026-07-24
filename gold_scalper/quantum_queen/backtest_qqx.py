#!/usr/bin/env python3
"""Approximate backtest of Quantum Queen X v4.1 recovered portfolio on XAU M1.

Source: recovered MQ5 (dual iDeMarker + same-direction grid). Not the official
binary — results are indicative on the available M1 OHLC window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
POINT = 0.01  # XAU digits=2
POINT_VALUE_PER_LOT = 100.0  # $ per $1 move per 1.0 lot


@dataclass
class Profile:
    number: int
    family: int
    first_tf: int  # minutes
    first_period: int
    first_upper: float
    first_lower: float
    second_tf: int
    second_period: int
    second_upper: float
    second_lower: float
    session_start: int
    session_end: int
    native_dir: int  # 1 buy-only, -1 sell-only, 0 both
    tp_base: int
    grid_base: int
    orders_max: int


# IC Markets RAW HIGH RISK enabled modules (see RecoveredStrategyEnabled)
PROFILES: List[Profile] = [
    Profile(1, 1, 6, 18, 0.7, 0.3, 15, 16, 0.7, 0.3, 22, 24, 1, 50, 150, 25),
    Profile(8, 4, 5, 12, 0.5, 0.3, 60, 20, 0.9, 0.3, 6, 12, 1, 150, 150, 25),
    Profile(10, 5, 10, 20, 0.7, 0.3, 15, 10, 0.9, 0.3, 22, 23, 1, 200, 300, 15),
    Profile(12, 6, 12, 10, 0.7, 0.1, 15, 20, 0.7, 0.3, 8, 10, -1, 100, 200, 25),
]


@dataclass
class Position:
    side: int  # 1 buy / -1 sell
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
    balance: float = 5000.0
    equity_peak: float = 5000.0
    dd_lock: bool = False
    dd_limit_pct: float = 25.0
    positions: Dict[int, List[Position]] = field(default_factory=dict)
    closed: List[Closed] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)
    lot_mode: str = "auto_low_medium"  # balance/100000
    fixed_lot: float = 0.01

    def lot(self) -> float:
        if self.lot_mode == "fixed":
            return self.fixed_lot
        # Low-Medium auto lots from recovered EA
        return max(0.01, round(self.balance / 100000.0, 2))

    def floating(self, price: float) -> float:
        pnl = 0.0
        for legs in self.positions.values():
            for p in legs:
                delta = (price - p.entry) if p.side > 0 else (p.entry - price)
                pnl += delta * p.volume * POINT_VALUE_PER_LOT
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
            profit = delta * p.volume * POINT_VALUE_PER_LOT
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


def threshold_dir(value: float, upper: float, lower: float) -> int:
    if value > upper:
        return 1
    if value < lower:
        return -1
    return 0


def is_nfp_friday(ts: int) -> bool:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.weekday() == 4 and dt.day <= 7


def build_dem_maps(m1: List[dict], profiles: List[Profile]):
    """For each TF/period pair used, map bar_open_time -> demarker of last closed bar."""
    needed: Dict[Tuple[int, int], None] = {}
    for p in profiles:
        needed[(p.first_tf, p.first_period)] = None
        needed[(p.second_tf, p.second_period)] = None

    maps: Dict[Tuple[int, int], Dict[int, float]] = {}
    for tf, period in needed:
        bars = aggregate_tf(m1, tf)
        dem = demarker(bars, period)
        # value at open of bar i uses closed bar i-1
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


def run_backtest(m1: List[dict], initial: float = 5000.0) -> Engine:
    eng = Engine(balance=initial, equity_peak=initial)
    for p in PROFILES:
        eng.positions[p.number] = []

    maps = build_dem_maps(m1, PROFILES)
    last_entry_bar = {p.number: 0 for p in PROFILES}

    for b in m1:
        ts = int(b["time"])
        price = float(b["close"])
        high = float(b["high"])
        low = float(b["low"])
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hour = dt.hour
        weekday = dt.weekday()  # Mon=0 ... Sun=6; MT5 Sun=0 mismatch — use Python then map
        # MT5 day_of_week: 0=Sun … 5=Fri. Convert:
        mt5_dow = (weekday + 1) % 7

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

        # --- entries on new first-TF bar when strategy flat ---
        for p in PROFILES:
            if eng.positions[p.number]:
                continue
            bar_key = ts - (ts % (p.first_tf * 60))
            if bar_key == last_entry_bar[p.number]:
                continue
            last_entry_bar[p.number] = bar_key

            # session / filters
            if not (p.session_start <= hour < p.session_end):
                continue
            if mt5_dow == 0 or mt5_dow == 6:  # Sun/Sat
                continue
            if mt5_dow == 5 and hour >= 22:  # Friday night cutoff
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

            vol = eng.lot()
            eng.positions[p.number].append(
                Position(side=s1, entry=price, volume=vol, open_time=ts, strategy=p.number)
            )

        # --- manage open baskets on every M1 bar ---
        for p in PROFILES:
            legs = eng.positions[p.number]
            if not legs:
                continue
            side = legs[0].side
            vol_sum = sum(x.volume for x in legs)
            be = sum(x.entry * x.volume for x in legs) / vol_sum
            level = max(0, len(legs) - 1)
            tp_dist = p.tp_base * POINT
            tp = be + tp_dist if side > 0 else be - tp_dist

            # TP hit on bar range
            hit = (side > 0 and high >= tp) or (side < 0 and low <= tp)
            if hit:
                eng.close_strategy(p.number, tp, ts)
                continue

            if len(legs) >= p.orders_max:
                continue

            last_ref = legs[0].entry
            for x in legs[1:]:
                if side > 0:
                    last_ref = min(last_ref, x.entry)
                else:
                    last_ref = max(last_ref, x.entry)
            # recovered uses last reference as extreme in adverse direction among legs
            last_ref = legs[-1].entry  # approximate: last opened
            # Better match ReadRecoveredCycle lastReference:
            last_ref = legs[0].entry
            for x in legs:
                if side > 0:
                    last_ref = min(last_ref, x.entry)
                else:
                    last_ref = max(last_ref, x.entry)

            grid_dist = p.grid_base * POINT
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
        return {"n": 0}
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

    per_strategy = {}
    for sid, ts_ in sorted(by_s.items()):
        per_strategy[f"S{sid:02d}"] = {
            "n": len(ts_),
            "net": round(sum(x.profit for x in ts_), 2),
            "wr": round(sum(1 for x in ts_ if x.profit > 0) / len(ts_), 4),
        }

    return {
        "window_note": "Same XAU M1 window as GoldMRScalperGrid data",
        "set": "IC Markets RAW HIGH RISK (S01,S08,S10,S12)",
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
            "Recovered dual-DeMarker portfolio approx on M1 OHLC; not official QQX "
            "binary. No spread/commission/swap modeled."
        ),
    }


def main():
    m1 = sorted(json.loads((ROOT / "data" / "xau_m1.json").read_text()), key=lambda b: b["time"])
    eng = run_backtest(m1, 5000.0)
    report = summarize(eng)
    t0 = datetime.fromtimestamp(m1[0]["time"], timezone.utc).isoformat()
    t1 = datetime.fromtimestamp(m1[-1]["time"], timezone.utc).isoformat()
    report["window_utc"] = [t0, t1]
    out = Path(__file__).resolve().parent / "report.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
