"""MT5-style realistic backtester + Monte Carlo forward stress tests."""

from .engine import BacktestEngine
from .models import BrokerConfig
from .montecarlo import MonteCarloConfig, run_monte_carlo
from .random_paths import PathSpec
from .report_audit import audit_mt5_report, audit_mt5_report_file
from .strategies.base import MovingAverageCross, Strategy

__all__ = [
    "BacktestEngine",
    "BrokerConfig",
    "MonteCarloConfig",
    "MovingAverageCross",
    "PathSpec",
    "Strategy",
    "audit_mt5_report",
    "audit_mt5_report_file",
    "run_monte_carlo",
]
