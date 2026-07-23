"""Symbol presets. Default stress-tests target XAUUSD."""

from __future__ import annotations

from dataclasses import dataclass

from .models import BrokerConfig
from .random_paths import PathSpec


@dataclass(frozen=True)
class SymbolSpec:
    name: str
    broker: BrokerConfig
    path: PathSpec
    # Strategy defaults tuned to the symbol
    lot: float
    sl_points: float
    tp_points: float
    bar_seconds: float = 60.0


def xauusd(
    *,
    initial_balance: float = 10_000.0,
    optimistic: bool = False,
    seed: int = 42,
    bars: int = 2000,
    model: str = "jump",
) -> SymbolSpec:
    """
    XAUUSD (Gold) retail-like defaults.

    Assumptions (common MT5 gold specs; brokers vary):
    - digits=2, point=0.01
    - contract size=100 oz / lot
    - spread ~25 points ($0.25), wider on jumps
    """
    broker = BrokerConfig(
        initial_balance=initial_balance,
        leverage=100.0,
        contract_size=100.0,
        point=0.01,
        digits=2,
        commission_per_lot=0.0 if optimistic else 6.0,
        base_slippage_points=0.0 if optimistic else 5.0,
        volatility_slippage_factor=0.0 if optimistic else 0.8,
        latency_ms=0.0 if optimistic else 100.0,
        min_stop_level_points=0.0 if optimistic else 30.0,
        freeze_level_points=0.0 if optimistic else 10.0,
        min_spread_points=15.0,
        max_spread_points=120.0,
        spread_widen_on_gap_points=40.0,
        optimistic=optimistic,
    )
    path = PathSpec(
        bars=bars,
        timeframe_seconds=60.0,
        start_price=2650.0,
        mu_per_year=0.0,
        sigma_per_year=0.16,  # gold typically more volatile than majors
        jump_prob_per_bar=0.003,
        jump_sigma=0.0025,
        ou_theta=0.03,
        ou_mu=2650.0,
        regime_switch_prob=0.012,
        point=0.01,
        base_spread_points=25.0,
        ticks_per_bar=8,
        model=model,  # type: ignore[arg-type]
        seed=seed,
    )
    return SymbolSpec(
        name="XAUUSD",
        broker=broker,
        path=path,
        lot=0.01,
        sl_points=400.0,  # $4.00
        tp_points=600.0,  # $6.00
        bar_seconds=60.0,
    )


DEFAULT_SYMBOL = "XAUUSD"


def get_symbol(name: str = DEFAULT_SYMBOL, **kwargs) -> SymbolSpec:
    key = name.strip().upper()
    if key in {"XAUUSD", "GOLD", "XAU"}:
        return xauusd(**kwargs)
    raise ValueError(f"Unsupported symbol '{name}'. Currently supported: XAUUSD")
