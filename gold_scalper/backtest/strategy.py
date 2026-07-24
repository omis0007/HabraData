"""Gold mean-reversion scalper with same-direction grid recovery.

Reverse-engineered from Equiti account 1013596414 (XAUUSD.pr) investor history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Params:
    asset: str = "XAU"
    stoch_period: int = 14
    stoch_k: int = 3
    stoch_oversold: float = 10.0
    stoch_overbought: float = 90.0
    # DeMarker (iDeMarker) confirmation — classic 0.3 / 0.7 bands
    use_demarker: bool = False  # off by default: better PnL; set True to filter openings
    demarker_period: int = 14
    demarker_oversold: float = 0.30
    demarker_overbought: float = 0.70
    ema_period: int = 20
    stretch_min: float = 14.0  # price units from EMA20
    move3_against_min: float = 5.0
    solo_tp: float = 1.5
    basket_tp: float = 0.40
    grid_step: float = 6.0
    max_positions: int = 5
    lot: float = 0.05
    trade_hours: tuple = (2, 3, 4, 5, 6, 9, 10, 11, 15, 16, 17, 18)
    contract_size: float = 100.0
    point_value_per_lot: float = 100.0
    # ATR_AUTO mode: distances = ATR × multipliers each bar
    use_atr: bool = False
    atr_period: int = 14
    atr_solo_tp: float = 0.375
    atr_basket_tp: float = 0.10
    atr_grid_step: float = 1.50
    atr_stretch_min: float = 3.50
    atr_move3_against_min: float = 1.25

    def distances_at(self, atr: Optional[float] = None) -> Dict[str, float]:
        if self.use_atr and atr is not None and atr > 0:
            return {
                "solo_tp": atr * self.atr_solo_tp,
                "basket_tp": atr * self.atr_basket_tp,
                "grid_step": atr * self.atr_grid_step,
                "stretch_min": atr * self.atr_stretch_min,
                "move3_against_min": atr * self.atr_move3_against_min,
            }
        return {
            "solo_tp": self.solo_tp,
            "basket_tp": self.basket_tp,
            "grid_step": self.grid_step,
            "stretch_min": self.stretch_min,
            "move3_against_min": self.move3_against_min,
        }


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

    def try_open(self, side: str, price: float, ts: int, grid_step: Optional[float] = None) -> None:
        open_side = self.open_side()
        if open_side and open_side != side:
            return
        if len(self.positions) >= self.params.max_positions:
            return
        step = self.params.grid_step if grid_step is None else grid_step

        if not self.positions:
            # fresh solo entry
            tp = price + self.params.solo_tp if side == "buy" else price - self.params.solo_tp
            # caller may pass atr-scaled solo_tp via params mutation; prefer explicit
            self.positions.append(
                Position(side=side, entry=price, volume=self.params.lot, open_time=ts, tp=tp)
            )
            return

        # grid add: require adverse move from last entry
        last = self.positions[-1]
        adverse = (last.entry - price) if side == "buy" else (price - last.entry)
        if adverse >= step:
            self.positions.append(
                Position(side=side, entry=price, volume=self.params.lot, open_time=ts, tp=None)
            )

    def manage_exits(
        self, bar: Dict[str, float], ts: int, solo_tp: Optional[float] = None, basket_tp: Optional[float] = None
    ) -> None:
        if not self.positions:
            return
        high = bar["high"]
        low = bar["low"]
        s_tp = self.params.solo_tp if solo_tp is None else solo_tp
        b_tp = self.params.basket_tp if basket_tp is None else basket_tp

        if len(self.positions) == 1:
            p = self.positions[0]
            tp = p.entry + s_tp if p.side == "buy" else p.entry - s_tp
            if p.side == "buy" and high >= tp:
                self.close_all(tp, ts)
            elif p.side == "sell" and low <= tp:
                self.close_all(tp, ts)
            return

        avg = self.weighted_avg()
        side = self.positions[0].side
        target = avg + b_tp if side == "buy" else avg - b_tp
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

    # DeMarker (same definition as MT5 iDeMarker)
    demax = [0.0] * len(closes)
    demin = [0.0] * len(closes)
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        demax[i] = up if up > 0 else 0.0
        demin[i] = dn if dn > 0 else 0.0
    dem = [None] * len(closes)
    dn_period = p.demarker_period
    for i in range(dn_period, len(closes)):
        smax = sum(demax[i - dn_period + 1 : i + 1])
        smin = sum(demin[i - dn_period + 1 : i + 1])
        den = smax + smin
        dem[i] = 0.0 if den == 0 else smax / den

    # Wilder ATR
    atr: List[Optional[float]] = [None] * len(closes)
    if len(closes) > 1:
        trs = [0.0] * len(closes)
        for i in range(1, len(closes)):
            trs[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        ap = p.atr_period
        if len(closes) > ap:
            first = sum(trs[1 : ap + 1]) / ap
            atr[ap] = first
            for i in range(ap + 1, len(closes)):
                atr[i] = (atr[i - 1] * (ap - 1) + trs[i]) / ap

    return ema, stoch, dem, atr


def hour_utc(ts: int) -> int:
    return (ts % 86400) // 3600


def signal_at(i: int, bars, ema, stoch, dem, p: Params, dist: Dict[str, float]) -> Optional[str]:
    warm = max(p.ema_period, p.stoch_period + p.stoch_k, p.demarker_period, p.atr_period, 5)
    if i < warm:
        return None
    if stoch[i] is None:
        return None
    if p.use_demarker and dem[i] is None:
        return None
    if hour_utc(bars[i]["time"]) not in p.trade_hours:
        return None

    close = bars[i]["close"]
    move3 = close - bars[i - 3]["close"]
    dem_ok_buy = (not p.use_demarker) or (dem[i] <= p.demarker_oversold)
    dem_ok_sell = (not p.use_demarker) or (dem[i] >= p.demarker_overbought)

    if stoch[i] <= p.stoch_oversold and dem_ok_buy:
        stretch = ema[i] - close
        against = -move3
        if stretch >= dist["stretch_min"] and against >= dist["move3_against_min"]:
            return "buy"

    if stoch[i] >= p.stoch_overbought and dem_ok_sell:
        stretch = close - ema[i]
        against = move3
        if stretch >= dist["stretch_min"] and against >= dist["move3_against_min"]:
            return "sell"

    return None


def run_backtest(bars: List[Dict[str, float]], params: Optional[Params] = None) -> Engine:
    p = params or Params()
    eng = Engine(params=p, balance=5000.0)
    ema, stoch, dem, atr = compute_indicators(bars, p)

    for i, bar in enumerate(bars):
        ts = int(bar["time"])
        a = atr[i] if atr[i] is not None else None
        dist = p.distances_at(a)

        # temporarily align solo_tp on params for try_open TP calc
        saved = (p.solo_tp, p.basket_tp, p.grid_step)
        p.solo_tp, p.basket_tp, p.grid_step = dist["solo_tp"], dist["basket_tp"], dist["grid_step"]

        eng.manage_exits(bar, ts, solo_tp=dist["solo_tp"], basket_tp=dist["basket_tp"])

        open_side = eng.open_side()
        if open_side and len(eng.positions) < p.max_positions:
            last = eng.positions[-1]
            price = bar["close"]
            adverse = (last.entry - price) if open_side == "buy" else (price - last.entry)
            if adverse >= dist["grid_step"]:
                eng.try_open(open_side, price, ts, grid_step=dist["grid_step"])

        if not eng.positions:
            sig = signal_at(i, bars, ema, stoch, dem, p, dist)
            if sig:
                eng.try_open(sig, bar["close"], ts)

        p.solo_tp, p.basket_tp, p.grid_step = saved

        eng.equity_curve.append(
            {
                "time": ts,
                "balance": eng.balance,
                "equity": eng.balance + eng.floating_pnl(bar["close"]),
                "positions": len(eng.positions),
            }
        )

    if eng.positions:
        eng.close_all(bars[-1]["close"], int(bars[-1]["time"]))
    return eng
