#!/usr/bin/env python3
"""CLI: realistic backtest + Monte Carlo forward on random paths."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running without install
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mt5_backtester import (
    BacktestEngine,
    BrokerConfig,
    MonteCarloConfig,
    MovingAverageCross,
    PathSpec,
    audit_mt5_report_file,
    run_monte_carlo,
)
from mt5_backtester.data import load_ohlc_csv, load_ticks_csv, ohlc_to_ticks, write_sample_ohlc
from mt5_backtester.random_paths import generate_ohlc


def _strategy_factory(args: argparse.Namespace):
    def factory():
        return MovingAverageCross(
            fast=args.fast,
            slow=args.slow,
            timeframe_seconds=args.bar_seconds,
            lot=args.lot,
            sl_points=args.sl_points,
            tp_points=args.tp_points,
        )

    return factory


def cmd_montecarlo(args: argparse.Namespace) -> int:
    path = PathSpec(
        bars=args.bars,
        timeframe_seconds=args.bar_seconds,
        start_price=args.start_price,
        mu_per_year=args.mu,
        sigma_per_year=args.sigma,
        model=args.model,
        seed=args.seed,
        base_spread_points=args.spread_points,
    )
    broker = BrokerConfig(
        initial_balance=args.balance,
        commission_per_lot=args.commission,
        base_slippage_points=args.slippage,
        latency_ms=args.latency_ms,
        optimistic=False,
    )
    cfg = MonteCarloConfig(
        runs=args.runs,
        path=path,
        realistic=broker,
        compare_optimistic=not args.no_compare,
    )
    report = run_monte_carlo(_strategy_factory(args), cfg)
    payload = report.to_dict()
    print(json.dumps(payload, indent=2))
    print()
    print(f"VERDETTO: {report.realistic.verdict}")
    for note in report.realistic.notes:
        print(f"- {note}")
    if report.gap_note:
        print(f"- {report.gap_note}")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    if args.ticks:
        ticks = load_ticks_csv(args.ticks)
    elif args.ohlc:
        ohlc = load_ohlc_csv(args.ohlc)
        ticks = ohlc_to_ticks(ohlc, base_spread_points=args.spread_points)
    elif args.random:
        ohlc = generate_ohlc(
            PathSpec(
                bars=args.bars,
                timeframe_seconds=args.bar_seconds,
                start_price=args.start_price,
                mu_per_year=args.mu,
                sigma_per_year=args.sigma,
                model=args.model,
                seed=args.seed,
            )
        )
        ticks = ohlc_to_ticks(ohlc, base_spread_points=args.spread_points, seed=args.seed)
    else:
        sample = Path(__file__).parent / "sample_data" / "sample_m1.csv"
        sample.parent.mkdir(parents=True, exist_ok=True)
        if not sample.exists():
            write_sample_ohlc(sample, bars=800)
        ohlc = load_ohlc_csv(sample)
        ticks = ohlc_to_ticks(ohlc, base_spread_points=args.spread_points)

    cfg = BrokerConfig(
        initial_balance=args.balance,
        commission_per_lot=0.0 if args.optimistic else args.commission,
        base_slippage_points=0.0 if args.optimistic else args.slippage,
        latency_ms=0.0 if args.optimistic else args.latency_ms,
        optimistic=args.optimistic,
    )
    result = BacktestEngine(cfg).run(
        ticks, _strategy_factory(args)(), bar_seconds=args.bar_seconds
    )
    print(json.dumps({"metrics": result.metrics, "warnings": result.warnings[:20]}, indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    audit = audit_mt5_report_file(args.report)
    print(json.dumps(audit.to_dict(), indent=2))
    print(f"\nSuspicion score: {audit.score}/100 (più basso = più sospetto)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Backtester realistico stile MT5 + forward Monte Carlo su dati casuali "
            "per smascherare EA con backtest manipolati."
        )
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--fast", type=int, default=10)
        sp.add_argument("--slow", type=int, default=30)
        sp.add_argument("--lot", type=float, default=0.1)
        sp.add_argument("--sl-points", type=float, default=150.0)
        sp.add_argument("--tp-points", type=float, default=250.0)
        sp.add_argument("--bar-seconds", type=float, default=60.0)
        sp.add_argument("--balance", type=float, default=10_000.0)
        sp.add_argument("--commission", type=float, default=7.0)
        sp.add_argument("--slippage", type=float, default=2.0)
        sp.add_argument("--latency-ms", type=float, default=80.0)
        sp.add_argument("--spread-points", type=float, default=10.0)
        sp.add_argument("--bars", type=int, default=1500)
        sp.add_argument("--start-price", type=float, default=1.085)
        sp.add_argument("--mu", type=float, default=0.0, help="Drift annualizzato")
        sp.add_argument("--sigma", type=float, default=0.08, help="Vol annualizzata")
        sp.add_argument(
            "--model",
            choices=["gbm", "ou", "jump", "regime"],
            default="jump",
            help="Modello stocastico per path casuali",
        )
        sp.add_argument("--seed", type=int, default=42)

    mc = sub.add_parser("montecarlo", help="Forward stress-test su N percorsi casuali")
    add_common(mc)
    mc.add_argument("--runs", type=int, default=40)
    mc.add_argument("--no-compare", action="store_true", help="Non confrontare vs modo ottimistico")
    mc.set_defaults(func=cmd_montecarlo)

    bt = sub.add_parser("backtest", help="Singolo backtest (CSV o path casuale)")
    add_common(bt)
    bt.add_argument("--ticks", type=str, help="CSV tick: time,bid,ask")
    bt.add_argument("--ohlc", type=str, help="CSV OHLC: time,open,high,low,close")
    bt.add_argument("--random", action="store_true", help="Usa un path generato casualmente")
    bt.add_argument("--optimistic", action="store_true", help="Simula backtest 'da brochure'")
    bt.set_defaults(func=cmd_backtest)

    au = sub.add_parser("audit", help="Analizza un report HTML del Strategy Tester MT5")
    au.add_argument("report", type=str)
    au.set_defaults(func=cmd_audit)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
