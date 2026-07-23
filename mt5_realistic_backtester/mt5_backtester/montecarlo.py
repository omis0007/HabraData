"""Monte Carlo forward stress-test on randomly generated paths."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Optional

from .engine import BacktestEngine
from .metrics import MonteCarloSummary, summarize_monte_carlo
from .models import BacktestResult, BrokerConfig
from .random_paths import PathSpec, generate_ticks
from .strategies.base import Strategy


StrategyFactory = Callable[[], Strategy]


@dataclass
class MonteCarloConfig:
    runs: int = 50
    path: PathSpec = None  # type: ignore[assignment]
    realistic: BrokerConfig = None  # type: ignore[assignment]
    optimistic: Optional[BrokerConfig] = None
    compare_optimistic: bool = True

    def __post_init__(self) -> None:
        if self.path is None:
            self.path = PathSpec()
        if self.realistic is None:
            self.realistic = BrokerConfig(optimistic=False)
        if self.compare_optimistic and self.optimistic is None:
            self.optimistic = BrokerConfig(
                optimistic=True,
                commission_per_lot=0.0,
                base_slippage_points=0.0,
                latency_ms=0.0,
                min_spread_points=0.0,
            )


@dataclass
class MonteCarloReport:
    realistic: MonteCarloSummary
    optimistic: Optional[MonteCarloSummary]
    sample_results: list[BacktestResult]
    gap_note: str

    def to_dict(self) -> dict:
        return {
            "realistic": self.realistic.to_dict(),
            "optimistic": self.optimistic.to_dict() if self.optimistic else None,
            "gap_note": self.gap_note,
        }


def run_monte_carlo(
    strategy_factory: StrategyFactory,
    cfg: Optional[MonteCarloConfig] = None,
) -> MonteCarloReport:
    """
    Forward-like stress test:
    for each random path, instantiate a fresh strategy and backtest as-if-live.
    """
    cfg = cfg or MonteCarloConfig()
    realistic_results: list[BacktestResult] = []
    optimistic_results: list[BacktestResult] = []

    for i in range(cfg.runs):
        path_spec = deepcopy(cfg.path)
        path_spec.seed = cfg.path.seed + i * 9973
        ticks = generate_ticks(path_spec)

        eng = BacktestEngine(deepcopy(cfg.realistic))
        realistic_results.append(
            eng.run(ticks, strategy_factory(), bar_seconds=path_spec.timeframe_seconds)
        )

        if cfg.compare_optimistic and cfg.optimistic is not None:
            eng_o = BacktestEngine(deepcopy(cfg.optimistic))
            optimistic_results.append(
                eng_o.run(ticks, strategy_factory(), bar_seconds=path_spec.timeframe_seconds)
            )

    real_sum = summarize_monte_carlo(realistic_results, cfg.realistic.initial_balance)
    opt_sum = (
        summarize_monte_carlo(optimistic_results, cfg.optimistic.initial_balance)
        if optimistic_results and cfg.optimistic
        else None
    )

    gap_note = ""
    if opt_sum is not None:
        gap = opt_sum.median_return_pct - real_sum.median_return_pct
        if gap > 0.1:
            gap_note = (
                f"Il modo 'ottimistico' (tipico dei backtest truccati) mostra "
                f"+{gap:.1%} di ritorno mediano rispetto al modo realistico. "
                f"Diffida di report senza slippage/spread/commissioni/latenza."
            )
        else:
            gap_note = (
                "Gap ottimistico vs realistico contenuto: i costi di esecuzione "
                "non spiegano da soli la performance."
            )

    return MonteCarloReport(
        realistic=real_sum,
        optimistic=opt_sum,
        sample_results=realistic_results[:5],
        gap_note=gap_note,
    )
