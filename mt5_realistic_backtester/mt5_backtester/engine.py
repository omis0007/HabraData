"""Single-path backtest engine (no look-ahead)."""

from __future__ import annotations

import math
from typing import Optional

from .broker import Broker
from .metrics import enrich_result
from .models import BacktestResult, BrokerConfig, Tick
from .strategies.base import Strategy


class BacktestEngine:
    def __init__(self, config: Optional[BrokerConfig] = None):
        self.config = config or BrokerConfig()

    def run(
        self,
        ticks: list[Tick],
        strategy: Strategy,
        *,
        bar_seconds: float = 60.0,
    ) -> BacktestResult:
        broker = Broker(self.config)
        strategy.on_init(broker)

        bars: list[dict] = []
        bucket: list[Tick] = []
        bucket_start: Optional[float] = None
        curve: list[tuple[float, float]] = []

        def flush_bar() -> None:
            nonlocal bucket, bucket_start
            if not bucket or bucket_start is None:
                return
            mids = [t.mid for t in bucket]
            bars.append(
                {
                    "time": bucket_start,
                    "open": mids[0],
                    "high": max(mids),
                    "low": min(mids),
                    "close": mids[-1],
                    "volume": sum(t.volume for t in bucket),
                    "spread": bucket[-1].spread,
                }
            )
            bucket = []
            bucket_start = None

        for tick in ticks:
            start = math.floor(tick.time / bar_seconds) * bar_seconds
            if bucket_start is None:
                bucket_start = start
            if start != bucket_start:
                flush_bar()
                bucket_start = start
            bucket.append(tick)

            broker.on_tick(tick)
            # Strategy sees only completed bars (excludes current forming bar)
            strategy.on_tick(broker, tick, bars)
            curve.append((tick.time, broker.equity))

        flush_bar()
        # Close leftovers at last tick for a fair final equity
        if ticks and broker.positions:
            last = ticks[-1]
            for pos in list(broker.positions):
                broker.close_position(pos.id, comment="eod")
            broker.on_tick(last)
            curve.append((last.time, broker.equity))

        strategy.on_deinit(broker)
        result = BacktestResult(
            balance_curve=curve,
            trades=list(broker.trades),
            rejected_orders=broker.rejected_orders,
            equity_final=broker.equity,
            balance_final=broker.balance,
            warnings=list(broker.warnings),
        )
        return enrich_result(result, self.config.initial_balance)
