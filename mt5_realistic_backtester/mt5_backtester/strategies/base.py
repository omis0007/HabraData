"""Strategy interface (port EA OnTick logic here)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..broker import Broker
    from ..models import Tick


class Strategy(ABC):
    """Minimal EA-like interface."""

    name: str = "strategy"

    def on_init(self, broker: "Broker") -> None:
        pass

    @abstractmethod
    def on_tick(self, broker: "Broker", tick: "Tick", bars: list[dict]) -> None:
        """Called every tick. `bars` contains only completed bars (no look-ahead)."""

    def on_deinit(self, broker: "Broker") -> None:
        pass


class MovingAverageCross(Strategy):
    """Simple MA cross — useful as a baseline on random paths."""

    name = "ma_cross"

    def __init__(
        self,
        fast: int = 10,
        slow: int = 30,
        timeframe_seconds: float = 60.0,
        lot: float = 0.01,  # XAUUSD micro lot default
        sl_points: float = 400.0,  # $4 on 2-digit gold
        tp_points: float = 600.0,  # $6 on 2-digit gold
    ):
        self.fast = fast
        self.slow = slow
        self.timeframe_seconds = timeframe_seconds
        self.lot = lot
        self.sl_points = sl_points
        self.tp_points = tp_points
        self._last_bar_time: Optional[float] = None
        self._prev_diff: Optional[float] = None

    def on_tick(self, broker, tick, bars: list[dict]) -> None:
        if len(bars) < self.slow + 2:
            return
        bar = bars[-1]
        if self._last_bar_time == bar["time"]:
            return  # new decision only on new bar
        self._last_bar_time = bar["time"]

        closes = [b["close"] for b in bars]
        fast_ma = sum(closes[-self.fast :]) / self.fast
        slow_ma = sum(closes[-self.slow :]) / self.slow
        diff = fast_ma - slow_ma
        point = broker.cfg.point

        if self._prev_diff is None:
            self._prev_diff = diff
            return

        cross_up = self._prev_diff <= 0 < diff
        cross_dn = self._prev_diff >= 0 > diff
        self._prev_diff = diff

        # one position at a time
        if broker.positions:
            pos = broker.positions[0]
            if (pos.side.value == "buy" and cross_dn) or (pos.side.value == "sell" and cross_up):
                broker.close_position(pos.id, comment="ma_reverse")
            return

        from ..models import Side

        if cross_up:
            sl = tick.bid - self.sl_points * point
            tp = tick.ask + self.tp_points * point
            broker.submit_market(Side.BUY, self.lot, sl=sl, tp=tp, comment="ma_buy")
        elif cross_dn:
            sl = tick.ask + self.sl_points * point
            tp = tick.bid - self.tp_points * point
            broker.submit_market(Side.SELL, self.lot, sl=sl, tp=tp, comment="ma_sell")
