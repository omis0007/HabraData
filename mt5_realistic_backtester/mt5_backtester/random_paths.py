"""Random price-path generators for forward / Monte Carlo stress tests."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from .data import ohlc_to_ticks
from .models import Tick

PathModel = Literal["gbm", "ou", "jump", "regime"]


@dataclass
class PathSpec:
    """Default path generator is tuned for XAUUSD."""

    symbol: str = "XAUUSD"
    bars: int = 2000
    timeframe_seconds: float = 60.0
    start_price: float = 2650.0
    # annualized-ish params scaled to bar
    mu_per_year: float = 0.0  # drift
    sigma_per_year: float = 0.16  # gold vol
    jump_prob_per_bar: float = 0.003
    jump_sigma: float = 0.0025
    ou_theta: float = 0.03  # mean reversion speed
    ou_mu: float = 2650.0
    regime_switch_prob: float = 0.012
    point: float = 0.01
    digits: int = 2
    base_spread_points: float = 25.0
    ticks_per_bar: int = 8
    model: PathModel = "jump"
    seed: int = 42


def _bar_sigma(spec: PathSpec) -> float:
    bars_per_year = (365.25 * 24 * 3600) / spec.timeframe_seconds
    return spec.sigma_per_year / math.sqrt(bars_per_year)


def _bar_mu(spec: PathSpec) -> float:
    bars_per_year = (365.25 * 24 * 3600) / spec.timeframe_seconds
    return spec.mu_per_year / bars_per_year


def generate_ohlc(spec: PathSpec) -> pd.DataFrame:
    """Generate synthetic OHLC with the selected stochastic model."""
    rng = random.Random(spec.seed)
    mu = _bar_mu(spec)
    sigma = _bar_sigma(spec)
    price = spec.start_price
    t0 = 1_700_000_000.0
    high_vol = False
    rows = []

    for i in range(spec.bars):
        local_sigma = sigma * (2.2 if high_vol else 1.0)
        if spec.model == "regime" and rng.random() < spec.regime_switch_prob:
            high_vol = not high_vol

        if spec.model == "ou":
            # Ornstein-Uhlenbeck on log-ish price level
            shock = rng.gauss(0.0, local_sigma)
            price = price + spec.ou_theta * (spec.ou_mu - price) + price * shock
        elif spec.model in ("gbm", "jump", "regime"):
            shock = rng.gauss(0.0, local_sigma)
            price = price * math.exp(mu - 0.5 * local_sigma**2 + shock)
            if spec.model in ("jump", "regime") and rng.random() < spec.jump_prob_per_bar:
                price *= math.exp(rng.gauss(0.0, spec.jump_sigma))
        else:
            raise ValueError(f"Unknown model: {spec.model}")

        price = max(price, spec.point * 100)
        # Build a bar around the close
        o = rows[-1]["close"] if rows else spec.start_price
        c = price
        wiggle = abs(rng.gauss(0.0, local_sigma * price * 0.7))
        h = max(o, c) + wiggle
        l = min(o, c) - wiggle
        d = spec.digits
        rows.append(
            {
                "time": t0 + i * spec.timeframe_seconds,
                "open": round(o, d),
                "high": round(h, d),
                "low": round(l, d),
                "close": round(c, d),
                "volume": rng.randint(30, 300),
            }
        )

    df = pd.DataFrame(rows)
    df.attrs["timeframe_seconds"] = spec.timeframe_seconds
    return df


def generate_ticks(spec: PathSpec) -> list[Tick]:
    ohlc = generate_ohlc(spec)
    return ohlc_to_ticks(
        ohlc,
        point=spec.point,
        base_spread_points=spec.base_spread_points,
        ticks_per_bar=spec.ticks_per_bar,
        seed=spec.seed,
    )


def generate_many_paths(base: PathSpec, n: int) -> list[list[Tick]]:
    paths: list[list[Tick]] = []
    for i in range(n):
        spec = PathSpec(**{**base.__dict__, "seed": base.seed + i * 9973})
        paths.append(generate_ticks(spec))
    return paths
