#!/usr/bin/env python3
"""CLI: realistic XAUUSD backtest + Monte Carlo forward on random paths."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
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
from mt5_backtester.symbols import get_symbol


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


def _apply_symbol_defaults(args: argparse.Namespace) -> None:
    """Fill unset-looking CLI values from XAUUSD (or chosen) symbol preset."""
    sym = get_symbol(
        args.symbol,
        initial_balance=args.balance,
        seed=args.seed,
        bars=args.bars,
        model=args.model,
    )
    # Always stamp symbol metadata onto generated configs via args helpers
    args._symbol = sym  # noqa: SLF001


def cmd_montecarlo(args: argparse.Namespace) -> int:
    _apply_symbol_defaults(args)
    sym = args._symbol
    path = deepcopy(sym.path)
    path.bars = args.bars
    path.timeframe_seconds = args.bar_seconds
    path.start_price = args.start_price
    path.mu_per_year = args.mu
    path.sigma_per_year = args.sigma
    path.model = args.model
    path.seed = args.seed
    path.base_spread_points = args.spread_points

    broker = deepcopy(sym.broker)
    broker.initial_balance = args.balance
    broker.commission_per_lot = args.commission
    broker.base_slippage_points = args.slippage
    broker.latency_ms = args.latency_ms
    broker.optimistic = False

    cfg = MonteCarloConfig(
        runs=args.runs,
        path=path,
        realistic=broker,
        compare_optimistic=not args.no_compare,
    )
    report = run_monte_carlo(_strategy_factory(args), cfg)
    payload = report.to_dict()
    payload["symbol"] = sym.name
    print(json.dumps(payload, indent=2))
    print()
    print(f"SYMBOL: {sym.name}")
    print(f"VERDETTO: {report.realistic.verdict}")
    for note in report.realistic.notes:
        print(f"- {note}")
    if report.gap_note:
        print(f"- {report.gap_note}")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    _apply_symbol_defaults(args)
    sym = args._symbol

    if args.ticks:
        ticks = load_ticks_csv(args.ticks)
    elif args.ohlc:
        ohlc = load_ohlc_csv(args.ohlc)
        ticks = ohlc_to_ticks(
            ohlc,
            point=sym.path.point,
            base_spread_points=args.spread_points,
        )
    elif args.random:
        path = deepcopy(sym.path)
        path.bars = args.bars
        path.timeframe_seconds = args.bar_seconds
        path.start_price = args.start_price
        path.mu_per_year = args.mu
        path.sigma_per_year = args.sigma
        path.model = args.model
        path.seed = args.seed
        path.base_spread_points = args.spread_points
        ohlc = generate_ohlc(path)
        ticks = ohlc_to_ticks(
            ohlc,
            point=path.point,
            base_spread_points=path.base_spread_points,
            seed=path.seed,
        )
    else:
        sample = Path(__file__).parent / "sample_data" / "sample_xauusd_m1.csv"
        sample.parent.mkdir(parents=True, exist_ok=True)
        if not sample.exists():
            write_sample_ohlc(sample, bars=800)
        ohlc = load_ohlc_csv(sample)
        ticks = ohlc_to_ticks(
            ohlc,
            point=sym.path.point,
            base_spread_points=args.spread_points,
        )

    cfg = deepcopy(sym.broker)
    cfg.initial_balance = args.balance
    cfg.commission_per_lot = 0.0 if args.optimistic else args.commission
    cfg.base_slippage_points = 0.0 if args.optimistic else args.slippage
    cfg.latency_ms = 0.0 if args.optimistic else args.latency_ms
    cfg.optimistic = args.optimistic

    result = BacktestEngine(cfg).run(
        ticks, _strategy_factory(args)(), bar_seconds=args.bar_seconds
    )
    print(
        json.dumps(
            {
                "symbol": sym.name,
                "metrics": result.metrics,
                "warnings": result.warnings[:20],
            },
            indent=2,
        )
    )
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    audit = audit_mt5_report_file(args.report)
    print(json.dumps(audit.to_dict(), indent=2))
    print(f"\nSuspicion score: {audit.score}/100 (più basso = più sospetto)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    # Defaults from XAUUSD preset
    xau = get_symbol("XAUUSD")
    p = argparse.ArgumentParser(
        description=(
            "Backtester realistico stile MT5 su XAUUSD + forward Monte Carlo "
            "su dati casuali per smascherare EA con backtest manipolati."
        )
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--symbol", type=str, default="XAUUSD", help="Simbolo (default: XAUUSD)")
        sp.add_argument("--fast", type=int, default=10)
        sp.add_argument("--slow", type=int, default=30)
        sp.add_argument("--lot", type=float, default=xau.lot)
        sp.add_argument("--sl-points", type=float, default=xau.sl_points)
        sp.add_argument("--tp-points", type=float, default=xau.tp_points)
        sp.add_argument("--bar-seconds", type=float, default=xau.bar_seconds)
        sp.add_argument("--balance", type=float, default=xau.broker.initial_balance)
        sp.add_argument("--commission", type=float, default=xau.broker.commission_per_lot)
        sp.add_argument("--slippage", type=float, default=xau.broker.base_slippage_points)
        sp.add_argument("--latency-ms", type=float, default=xau.broker.latency_ms)
        sp.add_argument("--spread-points", type=float, default=xau.path.base_spread_points)
        sp.add_argument("--bars", type=int, default=1500)
        sp.add_argument("--start-price", type=float, default=xau.path.start_price)
        sp.add_argument("--mu", type=float, default=0.0, help="Drift annualizzato")
        sp.add_argument(
            "--sigma",
            type=float,
            default=xau.path.sigma_per_year,
            help="Vol annualizzata (XAUUSD ~0.16)",
        )
        sp.add_argument(
            "--model",
            choices=["gbm", "ou", "jump", "regime"],
            default="jump",
            help="Modello stocastico per path casuali",
        )
        sp.add_argument("--seed", type=int, default=42)

    mc = sub.add_parser("montecarlo", help="Forward stress-test XAUUSD su N percorsi casuali")
    add_common(mc)
    mc.add_argument("--runs", type=int, default=40)
    mc.add_argument("--no-compare", action="store_true", help="Non confrontare vs modo ottimistico")
    mc.set_defaults(func=cmd_montecarlo)

    bt = sub.add_parser("backtest", help="Singolo backtest XAUUSD (CSV o path casuale)")
    add_common(bt)
    bt.add_argument("--ticks", type=str, help="CSV tick: time,bid,ask")
    bt.add_argument("--ohlc", type=str, help="CSV OHLC: time,open,high,low,close")
    bt.add_argument("--random", action="store_true", help="Usa un path XAUUSD generato casualmente")
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
