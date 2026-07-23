"""Historical data loaders and synthetic tick generation from OHLC."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from .models import Tick


REQUIRED_TICK_COLS = {"time", "bid", "ask"}
REQUIRED_OHLC_COLS = {"time", "open", "high", "low", "close"}


def _parse_time_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        # Heuristic: ms vs s
        sample = float(series.dropna().iloc[0])
        if sample > 1e12:
            return series.astype(float) / 1000.0
        return series.astype(float)
    return pd.to_datetime(series, utc=True).astype("int64") / 1e9


def load_ticks_csv(path: str | Path) -> list[Tick]:
    """
    Load tick CSV.

    Expected columns: time, bid, ask [, volume]
    time can be ISO datetime or unix seconds/ms.
    """
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    missing = REQUIRED_TICK_COLS - set(cols)
    if missing:
        raise ValueError(f"Tick CSV missing columns: {sorted(missing)}")

    df = df.rename(columns={cols[k]: k for k in cols})
    df["time"] = _parse_time_series(df["time"])
    if "volume" not in df.columns:
        df["volume"] = 0.0

    ticks: list[Tick] = []
    for row in df.itertuples(index=False):
        ticks.append(
            Tick(
                time=float(row.time),
                bid=float(row.bid),
                ask=float(row.ask),
                volume=float(getattr(row, "volume", 0.0) or 0.0),
            )
        )
    return ticks


def load_ohlc_csv(path: str | Path, timeframe_seconds: Optional[float] = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    missing = REQUIRED_OHLC_COLS - set(cols)
    if missing:
        raise ValueError(f"OHLC CSV missing columns: {sorted(missing)}")
    df = df.rename(columns={cols[k]: k for k in cols})
    df["time"] = _parse_time_series(df["time"])
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df = df.sort_values("time").reset_index(drop=True)
    if timeframe_seconds is None and len(df) > 1:
        diffs = df["time"].diff().dropna()
        timeframe_seconds = float(diffs.median())
    df.attrs["timeframe_seconds"] = timeframe_seconds or 60.0
    return df


def ohlc_to_ticks(
    ohlc: pd.DataFrame,
    *,
    point: float = 0.00001,
    base_spread_points: float = 10.0,
    ticks_per_bar: int = 12,
    seed: int = 42,
) -> list[Tick]:
    """
    Build path-dependent ticks from OHLC without look-ahead within a bar.

    Path used: open -> (random mid path constrained by H/L) -> close.
    Spread widens when bar range is large (proxy for volatility / news).
    """
    rng = random.Random(seed)
    tf = float(ohlc.attrs.get("timeframe_seconds", 60.0))
    ticks: list[Tick] = []

    for row in ohlc.itertuples(index=False):
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
        start = float(row.time)
        rng_bar = max(h - l, point)
        spread_pts = base_spread_points + (rng_bar / point) * 0.05
        spread = spread_pts * point

        # Directional skeleton: open -> extreme1 -> extreme2 -> close
        if c >= o:
            path = [o, l, h, c]
        else:
            path = [o, h, l, c]

        # Expand to ticks_per_bar with jitter, clipped to [low, high]
        expanded = [path[0]]
        for i in range(1, len(path)):
            steps = max(1, ticks_per_bar // (len(path) - 1))
            a, b = path[i - 1], path[i]
            for s in range(1, steps + 1):
                t = s / steps
                px = a + (b - a) * t
                px += rng.uniform(-rng_bar * 0.02, rng_bar * 0.02)
                px = min(h, max(l, px))
                expanded.append(px)

        n = len(expanded)
        for i, mid in enumerate(expanded):
            # mild intra-bar spread variation
            local_spread = spread * (1.0 + 0.15 * math.sin(i))
            half = local_spread / 2.0
            ts = start + (tf * i / max(n - 1, 1))
            ticks.append(
                Tick(
                    time=ts,
                    bid=mid - half,
                    ask=mid + half,
                    volume=float(getattr(row, "volume", 0.0) or 0.0) / n,
                )
            )
    return ticks


def write_sample_ohlc(path: str | Path, bars: int = 500, seed: int = 7) -> Path:
    """Generate a synthetic XAUUSD M1-like series for demos/tests."""
    rng = random.Random(seed)
    path = Path(path)
    t0 = 1_700_000_000.0
    price = 2650.0
    rows = []
    for i in range(bars):
        drift = rng.uniform(-0.35, 0.35)
        shock = rng.choice([0.0, 0.0, 0.0, rng.uniform(-1.2, 1.2)])
        o = price
        c = max(100.0, o + drift + shock)
        h = max(o, c) + abs(rng.uniform(0, 0.6))
        l = min(o, c) - abs(rng.uniform(0, 0.6))
        rows.append(
            {
                "time": t0 + i * 60,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": rng.randint(20, 200),
            }
        )
        price = c
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def iter_bars_from_ticks(ticks: Iterable[Tick], timeframe_seconds: float) -> list[dict]:
    """Aggregate ticks into OHLC bars (for strategies that use bars only)."""
    bars: list[dict] = []
    bucket: list[Tick] = []
    bucket_start: Optional[float] = None

    def flush() -> None:
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
        start = math.floor(tick.time / timeframe_seconds) * timeframe_seconds
        if bucket_start is None:
            bucket_start = start
        if start != bucket_start:
            flush()
            bucket_start = start
        bucket.append(tick)
    flush()
    return bars
