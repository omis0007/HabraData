"""Realistic broker / order execution layer."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from .models import (
    BrokerConfig,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Side,
    Tick,
    Trade,
)


@dataclass
class _Pending:
    order: Order


class Broker:
    def __init__(self, config: BrokerConfig):
        self.cfg = config
        self.balance = config.initial_balance
        self.equity = config.initial_balance
        self.positions: list[Position] = []
        self.pending: Deque[_Pending] = deque()
        self.trades: list[Trade] = []
        self.rejected_orders = 0
        self._next_order_id = 1
        self._next_pos_id = 1
        self._recent_mids: Deque[float] = deque(maxlen=50)
        self.warnings: list[str] = []
        self.current_tick: Optional[Tick] = None

    def _points(self, price_delta: float) -> float:
        return abs(price_delta) / self.cfg.point

    def _price_from_points(self, points: float) -> float:
        return points * self.cfg.point

    def _lot_value(self, volume: float) -> float:
        return volume  # volume already in lots

    def _commission(self, volume: float) -> float:
        if self.cfg.optimistic:
            return 0.0
        return self.cfg.commission_per_lot * abs(volume)

    def _slippage_price(self, side: Side, tick: Tick) -> tuple[float, float]:
        """Return (fill_price, slippage_points)."""
        if self.cfg.optimistic:
            px = tick.ask if side == Side.BUY else tick.bid
            return px, 0.0

        vol_pts = 0.0
        if len(self._recent_mids) >= 2:
            vol_pts = self._points(max(self._recent_mids) - min(self._recent_mids))
        slip_pts = self.cfg.base_slippage_points + self.cfg.volatility_slippage_factor * (
            vol_pts / max(len(self._recent_mids), 1)
        )
        slip = self._price_from_points(slip_pts)
        if side == Side.BUY:
            return tick.ask + slip, slip_pts
        return tick.bid - slip, slip_pts

    def _margin_required(self, volume: float, price: float) -> float:
        notional = abs(volume) * self.cfg.contract_size * price
        return notional / self.cfg.leverage

    def free_margin(self, tick: Tick) -> float:
        used = 0.0
        for p in self.positions:
            used += self._margin_required(p.volume, p.open_price)
        return self.equity - used

    def update_equity(self, tick: Tick) -> None:
        upl = sum(p.unrealized_pnl(tick, self.cfg.contract_size) for p in self.positions)
        # For FX, pnl in quote currency approx volume * contract * price_diff
        # Using contract_size as multiplier keeps units consistent with balance in account currency.
        self.equity = self.balance + upl
        self.current_tick = tick
        self._recent_mids.append(tick.mid)

    def submit_market(
        self,
        side: Side,
        volume: float,
        *,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        magic: int = 0,
        now: Optional[float] = None,
    ) -> Order:
        assert self.current_tick is not None
        now = now if now is not None else self.current_tick.time
        latency = 0.0 if self.cfg.optimistic else self.cfg.latency_ms / 1000.0
        order = Order(
            id=self._next_order_id,
            side=side,
            order_type=OrderType.MARKET,
            volume=volume,
            sl=sl,
            tp=tp,
            created_at=now,
            executable_at=now + latency,
            comment=comment,
            magic=magic,
        )
        self._next_order_id += 1
        self.pending.append(_Pending(order))
        return order

    def close_position(self, position_id: int, comment: str = "close") -> None:
        assert self.current_tick is not None
        pos = next((p for p in self.positions if p.id == position_id), None)
        if pos is None:
            return
        close_side = Side.SELL if pos.side == Side.BUY else Side.BUY
        # Closing is also a market order with latency
        self.submit_market(
            close_side,
            pos.volume,
            comment=f"{comment}|close:{pos.id}",
            magic=pos.magic,
        )

    def _validate_stops(self, side: Side, fill: float, sl: Optional[float], tp: Optional[float]) -> bool:
        if self.cfg.optimistic:
            return True
        min_dist = self._price_from_points(self.cfg.min_stop_level_points)
        if sl is not None:
            if side == Side.BUY and fill - sl < min_dist:
                return False
            if side == Side.SELL and sl - fill < min_dist:
                return False
        if tp is not None:
            if side == Side.BUY and tp - fill < min_dist:
                return False
            if side == Side.SELL and fill - tp < min_dist:
                return False
        return True

    def _open_position(self, order: Order, tick: Tick) -> None:
        if len(self.positions) >= self.cfg.max_positions:
            order.status = OrderStatus.REJECTED
            self.rejected_orders += 1
            return

        fill, slip_pts = self._slippage_price(order.side, tick)
        if not self._validate_stops(order.side, fill, order.sl, order.tp):
            order.status = OrderStatus.REJECTED
            self.rejected_orders += 1
            self.warnings.append(
                f"Order {order.id} rejected: SL/TP too close to market (stop level)."
            )
            return

        margin = self._margin_required(order.volume, fill)
        if margin > self.free_margin(tick):
            order.status = OrderStatus.REJECTED
            self.rejected_orders += 1
            self.warnings.append(f"Order {order.id} rejected: insufficient margin.")
            return

        commission = self._commission(order.volume)
        self.balance -= commission
        pos = Position(
            id=self._next_pos_id,
            side=order.side,
            volume=order.volume,
            open_price=fill,
            open_time=tick.time,
            sl=order.sl,
            tp=order.tp,
            comment=order.comment,
            magic=order.magic,
            commission=commission,
        )
        self._next_pos_id += 1
        self.positions.append(pos)
        order.status = OrderStatus.FILLED
        # stash slippage on comment for later reporting if needed
        pos.comment = f"{pos.comment}|slip:{slip_pts:.2f}"

    def _close_matching(self, order: Order, tick: Tick) -> bool:
        """If order comment encodes close:ID, close that position."""
        if "|close:" not in order.comment:
            return False
        try:
            pid = int(order.comment.split("|close:")[-1].split("|")[0])
        except ValueError:
            return False
        pos = next((p for p in self.positions if p.id == pid), None)
        if pos is None:
            order.status = OrderStatus.REJECTED
            self.rejected_orders += 1
            return True

        # Closing BUY uses bid (+sell slippage), closing SELL uses ask
        if pos.side == Side.BUY:
            fill, slip_pts = self._slippage_price(Side.SELL, tick)
            pnl = (fill - pos.open_price) * pos.volume * self.cfg.contract_size
        else:
            fill, slip_pts = self._slippage_price(Side.BUY, tick)
            pnl = (pos.open_price - fill) * pos.volume * self.cfg.contract_size

        commission = self._commission(pos.volume)
        self.balance += pnl - commission
        self.trades.append(
            Trade(
                position_id=pos.id,
                side=pos.side,
                volume=pos.volume,
                open_price=pos.open_price,
                close_price=fill,
                open_time=pos.open_time,
                close_time=tick.time,
                pnl=pnl,
                commission=pos.commission + commission,
                swap=pos.swap,
                slippage_points=slip_pts,
                comment=pos.comment,
                magic=pos.magic,
            )
        )
        self.positions = [p for p in self.positions if p.id != pos.id]
        order.status = OrderStatus.FILLED
        return True

    def _check_sl_tp(self, tick: Tick) -> None:
        to_close: list[int] = []
        for pos in self.positions:
            hit = False
            if pos.side == Side.BUY:
                if pos.sl is not None and tick.bid <= pos.sl:
                    hit = True
                if pos.tp is not None and tick.bid >= pos.tp:
                    hit = True
            else:
                if pos.sl is not None and tick.ask >= pos.sl:
                    hit = True
                if pos.tp is not None and tick.ask <= pos.tp:
                    hit = True
            if hit:
                to_close.append(pos.id)
        for pid in to_close:
            # SL/TP triggers immediately at current tick (with slippage), no extra latency
            # to avoid double-pending complexity; still applies slippage unless optimistic.
            pos = next(p for p in self.positions if p.id == pid)
            if pos.side == Side.BUY:
                fill, slip_pts = self._slippage_price(Side.SELL, tick)
                pnl = (fill - pos.open_price) * pos.volume * self.cfg.contract_size
            else:
                fill, slip_pts = self._slippage_price(Side.BUY, tick)
                pnl = (pos.open_price - fill) * pos.volume * self.cfg.contract_size
            commission = self._commission(pos.volume)
            self.balance += pnl - commission
            self.trades.append(
                Trade(
                    position_id=pos.id,
                    side=pos.side,
                    volume=pos.volume,
                    open_price=pos.open_price,
                    close_price=fill,
                    open_time=pos.open_time,
                    close_time=tick.time,
                    pnl=pnl,
                    commission=pos.commission + commission,
                    swap=pos.swap,
                    slippage_points=slip_pts,
                    comment=pos.comment + "|sltp",
                    magic=pos.magic,
                )
            )
            self.positions = [p for p in self.positions if p.id != pid]

    def _stop_out(self, tick: Tick) -> None:
        if self.cfg.optimistic:
            return
        used = sum(self._margin_required(p.volume, p.open_price) for p in self.positions)
        if used <= 0:
            return
        level = self.equity / used
        if level <= self.cfg.stop_out_level:
            self.warnings.append(
                f"Stop-out at {tick.time}: equity/margin={level:.2%} <= {self.cfg.stop_out_level:.0%}"
            )
            for pos in list(self.positions):
                self.close_position(pos.id, comment="stop_out")

    def on_tick(self, tick: Tick) -> None:
        self.update_equity(tick)
        self._check_sl_tp(tick)

        # Process pending orders whose latency elapsed
        still: Deque[_Pending] = deque()
        while self.pending:
            item = self.pending.popleft()
            order = item.order
            if tick.time < order.executable_at:
                still.append(item)
                continue
            if self._close_matching(order, tick):
                continue
            if order.order_type == OrderType.MARKET:
                self._open_position(order, tick)
            else:
                order.status = OrderStatus.REJECTED
                self.rejected_orders += 1
        self.pending = still

        self.update_equity(tick)
        self._stop_out(tick)
        # flush any stop-out closes submitted this tick (zero latency for stop-out path via pending)
        # Re-process with forced executable_at <= now for stop_out closes only
        if self.pending:
            forced: Deque[_Pending] = deque()
            for item in self.pending:
                if item.order.comment.startswith("stop_out"):
                    item.order.executable_at = tick.time
                forced.append(item)
            self.pending = forced
            still2: Deque[_Pending] = deque()
            while self.pending:
                item = self.pending.popleft()
                order = item.order
                if tick.time < order.executable_at:
                    still2.append(item)
                    continue
                if self._close_matching(order, tick):
                    continue
                if order.order_type == OrderType.MARKET:
                    self._open_position(order, tick)
            self.pending = still2
            self.update_equity(tick)
