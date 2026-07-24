"""Gold mean-reversion scalper with same-direction grid recovery.

Reverse-engineered from Equiti account 1013596414 (XAUUSD.pr) investor history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Params:
    stoch_period: int = 14
    stoch_k: int = 3
    stoch_oversold: float = 10.0
    stoch_overbought: float = 90.0
    ema_period: int = 20
    stretch_min: float = 14.0  # USD from EMA20 (matched to live density)
    move3_against_min: float = 5.0  # USD adverse move over last 3 M1 bars
    solo_tp: float = 1.5  # USD take-profit for single position
    basket_tp: float = 0.40  # USD beyond weighted average for basket exit
    grid_step: float = 6.0  # USD adverse from last entry to add
    max_positions: int = 5
    lot: float = 0.05
    # UTC hours observed on the live account
    trade_hours: tuple = (2, 3, 4, 5, 6, 9, 10, 11, 15, 16, 17, 18)
    contract_size: float = 100.0  # XAUUSD: $1 move * 0.01 lot ~= $1; profit ~= delta * lot * 100
    point_value_per_lot: float = 100.0  # $ per $1 price move per 1.0 lot


@dataclass
class Position:
    side: str  # 'buy' | 'sell'
    entry: float
    volume: float
    open_time: int
    tp: Optional[float] = None


@dataclass
class ClosedTrade:
    side: str
    entry: float
    exit: float
    volume: float
    open_time: int
    close_time: int
    profit: float
    basket_size: int


@dataclass
class Engine:
    params: Params = field(default_factory=Params)
    positions: List[Position] = field(default_factory=list)
    closed: List[ClosedTrade] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    balance: float = 5000.0

    def side_sign(self, side: str) -> int:
        return 1 if side == "buy" else -1

    def open_side(self) -> Optional[str]:
        if not self.positions:
            return None
        return self.positions[0].side

    def weighted_avg(self) -> float:
        num = sum(p.entry * p.volume for p in self.positions)
        den = sum(p.volume for p in self.positions)
        return num / den

    def floating_pnl(self, price: float) -> float:
        pnl = 0.0
        for p in self.positions:
            delta = (price - p.entry) if p.side == "buy" else (p.entry - price)
            pnl += delta * p.volume * self.params.point_value_per_lot
        return pnl

    def close_all(self, price: float, ts: int) -> None:
        if not self.positions:
            return
        size = len(self.positions)
        for p in list(self.positions):
            delta = (price - p.entry) if p.side == "buy" else (p.entry - price)
            profit = delta * p.volume * self.params.point_value_per_lot
            self.balance += profit
            self.closed.append(
                ClosedTrade(
                    side=p.side,
                    entry=p.entry,
                    exit=price,
                    volume=p.volume,
                    open_time=p.open_time,
                    close_time=ts,
                    profit=profit,
                    basket_size=size,
                )
            )
        self.positions.clear()

    def try_open(self, side: str, price: float, ts: int) -> None:
        open_side = self.open_side()
        if open_side and open_side != side:
            return
        if len(self.positions) >= self.params.max_positions:
            return

        if not self.positions:
            # fresh solo entry
            tp = price + self.params.solo_tp if side == "buy" else price - self.params.solo_tp
            self.positions.append(
                Position(side=side, entry=price, volume=self.params.lot, open_time=ts, tp=tp)
            )
            return

        # grid add: require adverse move from last entry
        last = self.positions[-1]
        adverse = (last.entry - price) if side == "buy" else (price - last.entry)
        if adverse >= self.params.grid_step:
            self.positions.append(
                Position(side=side, entry=price, volume=self.params.lot, open_time=ts, tp=None)
            )

    def manage_exits(self, bar: Dict[str, float], ts: int) -> None:
        if not self.positions:
            return
        high = bar["high"]
        low = bar["low"]
        close = bar["close"]

        if len(self.positions) == 1:
            p = self.positions[0]
            if p.side == "buy" and high >= p.tp:
                self.close_all(p.tp, ts)
            elif p.side == "sell" and low <= p.tp:
                self.close_all(p.tp, ts)
            return

        # Basket: exit near weighted average +/- basket_tp
        avg = self.weighted_avg()
        side = self.positions[0].side
        target = avg + self.params.basket_tp if side == "buy" else avg - self.params.basket_tp
        if side == "buy" and high >= target:
            self.close_all(target, ts)
        elif side == "sell" and low <= target:
            self.close_all(target, ts)


def compute_indicators(bars: List[Dict[str, float]], p: Params):
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]

    # EMA
    ema = [closes[0]]
    k = 2 / (p.ema_period + 1)
    for c in closes[1:]:
        ema.append(c * k + ema[-1] * (1 - k))

    # Stochastic %K smoothed
    raw = [None] * len(closes)
    n = p.stoch_period
    for i in range(n - 1, len(closes)):
        hh = max(highs[i - n + 1 : i + 1])
        ll = min(lows[i - n + 1 : i + 1])
        raw[i] = 50.0 if hh == ll else 100.0 * (closes[i] - ll) / (hh - ll)
    stoch = [None] * len(closes)
    for i in range(len(closes)):
        if i >= n - 1 + p.stoch_k - 1 and all(
            raw[j] is not None for j in range(i - p.stoch_k + 1, i + 1)
        ):
            stoch[i] = sum(raw[i - p.stoch_k + 1 : i + 1]) / p.stoch_k

    return ema, stoch


def hour_utc(ts: int) -> int:
    return (ts % 86400) // 3600


def signal_at(i: int, bars, ema, stoch, p: Params) -> Optional[str]:
    if i < max(p.ema_period, p.stoch_period + p.stoch_k, 5):
        return None
    if stoch[i] is None:
        return None
    if hour_utc(bars[i]["time"]) not in p.trade_hours:
        return None

    close = bars[i]["close"]
    move3 = close - bars[i - 3]["close"]

    # Buy: oversold + stretched below EMA + recent dump
    if stoch[i] <= p.stoch_oversold:
        stretch = ema[i] - close
        against = -move3  # positive if price fell
        if stretch >= p.stretch_min and against >= p.move3_against_min:
            return "buy"

    # Sell: overbought + stretched above EMA + recent rally
    if stoch[i] >= p.stoch_overbought:
        stretch = close - ema[i]
        against = move3
        if stretch >= p.stretch_min and against >= p.move3_against_min:
            return "sell"

    return None


def run_backtest(bars: List[Dict[str, float]], params: Optional[Params] = None) -> Engine:
    p = params or Params()
    eng = Engine(params=p, balance=5000.0)
    ema, stoch = compute_indicators(bars, p)

    for i, bar in enumerate(bars):
        ts = int(bar["time"])
        # exits first on this bar's range
        eng.manage_exits(bar, ts)

        # grid adds while in a basket use adverse from last entry vs close
        open_side = eng.open_side()
        if open_side and len(eng.positions) < p.max_positions:
            last = eng.positions[-1]
            price = bar["close"]
            adverse = (last.entry - price) if open_side == "buy" else (price - last.entry)
            if adverse >= p.grid_step:
                # only add if still stretched / not recovered
                eng.try_open(open_side, price, ts)

        # fresh signals only when flat or same side (try_open handles)
        sig = signal_at(i, bars, ema, stoch, p)
        if sig:
            # if flat -> open; if same side -> try_open may grid
            if not eng.positions:
                eng.try_open(sig, bar["close"], ts)
            elif eng.open_side() == sig:
                eng.try_open(sig, bar["close"], ts)

        eng.equity_curve.append(
            {
                "time": ts,
                "balance": eng.balance,
                "equity": eng.balance + eng.floating_pnl(bar["close"]),
                "positions": len(eng.positions),
            }
        )

    # flatten at end
    if eng.positions:
        eng.close_all(bars[-1]["close"], int(bars[-1]["time"]))
    return eng
