from __future__ import annotations

import unittest
from pathlib import Path

from mt5_backtester.engine import BacktestEngine
from mt5_backtester.metrics import summarize_monte_carlo
from mt5_backtester.models import BrokerConfig
from mt5_backtester.montecarlo import MonteCarloConfig, run_monte_carlo
from mt5_backtester.random_paths import PathSpec, generate_ohlc, generate_ticks
from mt5_backtester.report_audit import audit_mt5_report
from mt5_backtester.strategies import MovingAverageCross


ROOT = Path(__file__).resolve().parents[1]


class TestRandomForward(unittest.TestCase):
    def test_generate_ticks_nonempty(self):
        ticks = generate_ticks(PathSpec(bars=100, seed=1))
        self.assertGreater(len(ticks), 100)
        self.assertLess(ticks[0].bid, ticks[0].ask)

    def test_ohlc_monotonic_time(self):
        df = generate_ohlc(PathSpec(bars=50, seed=2))
        self.assertTrue((df["time"].diff().dropna() > 0).all())

    def test_single_backtest_runs(self):
        ticks = generate_ticks(PathSpec(bars=400, seed=3, model="gbm"))
        eng = BacktestEngine(BrokerConfig(initial_balance=10_000, optimistic=False))
        res = eng.run(ticks, MovingAverageCross(fast=5, slow=15), bar_seconds=60)
        self.assertIn("trades", res.metrics)
        self.assertGreater(len(res.balance_curve), 0)

    def test_montecarlo_smoke(self):
        cfg = MonteCarloConfig(
            runs=5,
            path=PathSpec(bars=300, seed=10, model="jump"),
            realistic=BrokerConfig(initial_balance=10_000),
            compare_optimistic=True,
        )
        report = run_monte_carlo(lambda: MovingAverageCross(fast=5, slow=20, lot=0.1), cfg)
        self.assertEqual(report.realistic.runs, 5)
        self.assertIn(report.realistic.verdict, {"FRAGILE", "RISCHIOSA", "ROBUSTA", "INCONCLUSIVA"})
        self.assertIsNotNone(report.optimistic)

    def test_audit_flags_open_prices(self):
        html = """
        <html>Modelling quality: Open prices only
        Spread 0
        Delay 0
        Profit Factor 8.2
        </html>
        """
        audit = audit_mt5_report(html)
        codes = {f.code for f in audit.findings}
        self.assertIn("model_open_prices", codes)
        self.assertLess(audit.score, 70)


if __name__ == "__main__":
    unittest.main()
