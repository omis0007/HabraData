"""Performance metrics and Monte Carlo summary stats."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .models import BacktestResult, Trade


def _pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def max_drawdown(equity: Sequence[tuple[float, float]]) -> tuple[float, float]:
    peak = float("-inf")
    max_dd = 0.0
    max_dd_pct = 0.0
    for _, eq in equity:
        peak = max(peak, eq)
        dd = peak - eq
        dd_pct = _pct(dd, peak) if peak else 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct
    return max_dd, max_dd_pct


def trade_stats(trades: Sequence[Trade], initial_balance: float) -> dict:
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_profit": 0.0,
            "avg_trade": 0.0,
            "expectancy": 0.0,
            "avg_slippage_points": 0.0,
        }

    nets = [t.net_pnl for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0)
    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "profit_factor": pf if math.isfinite(pf) else 999.0,
        "net_profit": sum(nets),
        "avg_trade": sum(nets) / len(nets),
        "expectancy": sum(nets) / len(nets),
        "avg_slippage_points": sum(t.slippage_points for t in trades) / len(trades),
        "return_pct": sum(nets) / initial_balance if initial_balance else 0.0,
    }


def enrich_result(result: BacktestResult, initial_balance: float) -> BacktestResult:
    dd, dd_pct = max_drawdown(result.balance_curve)
    result.max_drawdown = dd
    result.max_drawdown_pct = dd_pct
    result.metrics = trade_stats(result.trades, initial_balance)
    result.metrics["max_drawdown"] = dd
    result.metrics["max_drawdown_pct"] = dd_pct
    result.metrics["rejected_orders"] = result.rejected_orders
    return result


@dataclass
class MonteCarloSummary:
    runs: int
    profitable_runs: int
    survival_rate: float  # fraction with final equity > 0.5 * initial
    median_return_pct: float
    p05_return_pct: float
    p95_return_pct: float
    median_max_dd_pct: float
    p95_max_dd_pct: float
    median_profit_factor: float
    median_trades: float
    verdict: str
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "runs": self.runs,
            "profitable_runs": self.profitable_runs,
            "survival_rate": self.survival_rate,
            "median_return_pct": self.median_return_pct,
            "p05_return_pct": self.p05_return_pct,
            "p95_return_pct": self.p95_return_pct,
            "median_max_dd_pct": self.median_max_dd_pct,
            "p95_max_dd_pct": self.p95_max_dd_pct,
            "median_profit_factor": self.median_profit_factor,
            "median_trades": self.median_trades,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def summarize_monte_carlo(
    results: Sequence[BacktestResult],
    initial_balance: float,
) -> MonteCarloSummary:
    rets = [r.metrics.get("return_pct", 0.0) for r in results]
    dds = [r.metrics.get("max_drawdown_pct", 0.0) for r in results]
    pfs = [r.metrics.get("profit_factor", 0.0) for r in results]
    ntrades = [float(r.metrics.get("trades", 0)) for r in results]
    finals = [r.equity_final for r in results]

    def pctile(xs: list[float], p: float) -> float:
        if not xs:
            return 0.0
        ys = sorted(xs)
        idx = min(len(ys) - 1, max(0, int(round((len(ys) - 1) * p))))
        return ys[idx]

    profitable = sum(1 for r in rets if r > 0)
    survival = sum(1 for eq in finals if eq > 0.5 * initial_balance) / max(len(finals), 1)
    med_ret = pctile(rets, 0.5)
    p05 = pctile(rets, 0.05)
    p95 = pctile(rets, 0.95)
    med_dd = pctile(dds, 0.5)
    p95_dd = pctile(dds, 0.95)
    med_pf = pctile(pfs, 0.5)

    notes: list[str] = []
    # Heuristic verdict: curve-fit bots often collapse on random walks
    if profitable / max(len(rets), 1) < 0.35 and med_ret < 0:
        verdict = "FRAGILE"
        notes.append(
            "Su percorsi casuali la strategia perde nella maggioranza dei run: "
            "probabile overfit / edge inesistente sui dati storici usati nel marketing."
        )
    elif survival < 0.7 or p95_dd > 0.4:
        verdict = "RISCHIOSA"
        notes.append(
            "Sopravvive a tratti ma drawdown o survival rate non sono accettabili "
            "in condizioni forward sintetiche."
        )
    elif med_ret > 0 and p05 > -0.15 and med_pf >= 1.05:
        verdict = "ROBUSTA"
        notes.append(
            "Edge positivo anche su dati generati (random walk / jump). "
            "Non prova il futuro reale, ma esclude molti backtest trucati banali."
        )
    else:
        verdict = "INCONCLUSIVA"
        notes.append(
            "Risultati misti: aumenta i run, varia volatilità/drift, o confronta "
            "con un periodo out-of-sample reale."
        )

    notes.append(
        "I dati casuali non sostituiscono il mercato reale: servono a stress-testare "
        "la logica e a smascherare curve-fitting evidente."
    )

    return MonteCarloSummary(
        runs=len(results),
        profitable_runs=profitable,
        survival_rate=survival,
        median_return_pct=med_ret,
        p05_return_pct=p05,
        p95_return_pct=p95,
        median_max_dd_pct=med_dd,
        p95_max_dd_pct=p95_dd,
        median_profit_factor=med_pf,
        median_trades=pctile(ntrades, 0.5),
        verdict=verdict,
        notes=notes,
    )
