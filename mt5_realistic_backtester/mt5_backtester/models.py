"""Core trading domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Tick:
    time: float  # unix seconds (fractional ok)
    bid: float
    ask: float
    volume: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class Order:
    id: int
    side: Side
    order_type: OrderType
    volume: float
    price: Optional[float] = None  # trigger/limit price when needed
    sl: Optional[float] = None
    tp: Optional[float] = None
    created_at: float = 0.0
    executable_at: float = 0.0  # after latency
    status: OrderStatus = OrderStatus.PENDING
    comment: str = ""
    magic: int = 0


@dataclass
class Position:
    id: int
    side: Side
    volume: float
    open_price: float
    open_time: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    comment: str = ""
    magic: int = 0
    commission: float = 0.0
    swap: float = 0.0

    def unrealized_pnl(self, tick: Tick, point_value: float = 1.0) -> float:
        if self.side == Side.BUY:
            return (tick.bid - self.open_price) * self.volume * point_value
        return (self.open_price - tick.ask) * self.volume * point_value


@dataclass
class Trade:
    """Closed trade record."""

    position_id: int
    side: Side
    volume: float
    open_price: float
    close_price: float
    open_time: float
    close_time: float
    pnl: float
    commission: float
    swap: float
    slippage_points: float
    comment: str = ""
    magic: int = 0

    @property
    def net_pnl(self) -> float:
        return self.pnl - self.commission - self.swap


@dataclass
class BrokerConfig:
    """Execution assumptions that separate 'lab' backtests from near-live."""

    initial_balance: float = 10_000.0
    leverage: float = 100.0
    contract_size: float = 100_000.0  # FX standard lot
    point: float = 0.00001  # 5-digit FX
    digits: int = 5

    # Costs
    commission_per_lot: float = 7.0  # round-turn USD per lot (typical ECN)
    swap_long_points: float = 0.0
    swap_short_points: float = 0.0

    # Friction
    base_slippage_points: float = 2.0
    volatility_slippage_factor: float = 0.5  # extra pts from recent range
    latency_ms: float = 80.0
    min_stop_level_points: float = 10.0
    freeze_level_points: float = 5.0

    # Spread model (used when tick has zero/constant spread)
    min_spread_points: float = 8.0
    max_spread_points: float = 40.0
    spread_widen_on_gap_points: float = 25.0

    # Risk
    margin_call_level: float = 0.5  # 50%
    stop_out_level: float = 0.2

    # Simulation mode
    optimistic: bool = False
    """If True: zero latency, fixed min spread, no slippage (classic fake-looking tester)."""

    allow_hedging: bool = True
    max_positions: int = 50


@dataclass
class BacktestResult:
    balance_curve: list[tuple[float, float]] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    rejected_orders: int = 0
    equity_final: float = 0.0
    balance_final: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    metrics: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
