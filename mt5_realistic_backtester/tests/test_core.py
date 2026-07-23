from __future__ import annotations

import unittest
from pathlib import Path

from mt5_backtester.engine import BacktestEngine
from mt5_backtester.montecarlo import MonteCarloConfig, run_monte_carlo
from mt5_backtester.random_paths import generate_ohlc, generate_ticks
from mt5_backtester.report_audit import audit_mt5_report
from mt5_backtester.strategies import MovingAverageCross
from mt5_backtester.symbols import get_symbol, xauusd


ROOT = Path(__file__).resolve().parents[1]


class TestXAUUSDForward(unittest.TestCase):
    """All stress-tests run on XAUUSD specs (price, point, contract size)."""

    def setUp(self) -> None:
        self.sym = xauusd(seed=1, bars=100)

    def test_symbol_is_xauusd(self):
        self.assertEqual(self.sym.name, "XAUUSD")
        self.assertEqual(self.sym.broker.symbol, "XAUUSD")
        self.assertEqual(self.sym.broker.point, 0.01)
        self.assertEqual(self.sym.broker.contract_size, 100.0)
        self.assertAlmostEqual(self.sym.path.start_price, 2650.0)

    def test_generate_ticks_are_gold_priced(self):
        ticks = generate_ticks(self.sym.path)
        self.assertGreater(len(ticks), 100)
        self.assertLess(ticks[0].bid, ticks[0].ask)
        # XAUUSD trading range sanity (synthetic paths stay near gold levels)
        self.assertGreater(ticks[0].mid, 1000.0)
        self.assertLess(ticks[0].mid, 5000.0)
        # spread should be order of tens of cents, not FX pip fractions
        self.assertGreater(ticks[0].spread, 0.05)

    def test_ohlc_monotonic_time_xauusd(self):
        df = generate_ohlc(self.sym.path)
        self.assertTrue((df["time"].diff().dropna() > 0).all())
        self.assertGreater(df["close"].iloc[0], 1000.0)

    def test_single_backtest_xauusd(self):
        sym = xauusd(seed=3, bars=400, model="gbm")
        ticks = generate_ticks(sym.path)
        eng = BacktestEngine(sym.broker)
        strategy = MovingAverageCross(
            fast=5,
            slow=15,
            lot=sym.lot,
            sl_points=sym.sl_points,
            tp_points=sym.tp_points,
        )
        res = eng.run(ticks, strategy, bar_seconds=sym.bar_seconds)
        self.assertEqual(eng.config.symbol, "XAUUSD")
        self.assertIn("trades", res.metrics)
        self.assertGreater(len(res.balance_curve), 0)

    def test_montecarlo_xauusd_smoke(self):
        sym = xauusd(seed=10, bars=300, model="jump")
        cfg = MonteCarloConfig(
            runs=5,
            path=sym.path,
            realistic=sym.broker,
            compare_optimistic=True,
        )
        report = run_monte_carlo(
            lambda: MovingAverageCross(
                fast=5,
                slow=20,
                lot=sym.lot,
                sl_points=sym.sl_points,
                tp_points=sym.tp_points,
            ),
            cfg,
        )
        self.assertEqual(report.realistic.runs, 5)
        self.assertIn(
            report.realistic.verdict,
            {"FRAGILE", "RISCHIOSA", "ROBUSTA", "INCONCLUSIVA"},
        )
        self.assertIsNotNone(report.optimistic)
        # Paths used in MC should be gold-priced
        sample_eq = report.sample_results[0].balance_curve[0][1]
        self.assertGreater(sample_eq, 0)

    def test_get_symbol_aliases(self):
        self.assertEqual(get_symbol("gold").name, "XAUUSD")
        self.assertEqual(get_symbol("XAU").name, "XAUUSD")

    def test_audit_flags_open_prices_xauusd_report(self):
        html = """
        <html>Symbol: XAUUSD
        Modelling quality: Open prices only
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
