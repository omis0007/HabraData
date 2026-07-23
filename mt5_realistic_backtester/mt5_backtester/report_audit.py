"""Audit MT5 Strategy Tester HTML/HTM reports for common manipulation red flags."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditFinding:
    severity: str  # info | warn | critical
    code: str
    message: str


@dataclass
class ReportAudit:
    findings: list[AuditFinding] = field(default_factory=list)
    score: int = 100  # lower = more suspicious

    def add(self, severity: str, code: str, message: str, penalty: int = 0) -> None:
        self.findings.append(AuditFinding(severity, code, message))
        self.score = max(0, self.score - penalty)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "findings": [f.__dict__ for f in self.findings],
        }


def audit_mt5_report(text: str) -> ReportAudit:
    audit = ReportAudit()
    low = text.lower()

    # Modelling quality
    if "open prices only" in low or "solo prezzi open" in low:
        audit.add(
            "critical",
            "model_open_prices",
            "Modello 'Open prices only': spesso gonfia i risultati rispetto al tick reale.",
            35,
        )
    elif "1 minute ohic" in low or "1 minute ohlc" in low or "ohlc su M1" in low:
        audit.add(
            "warn",
            "model_m1_ohlc",
            "Modello M1 OHLC: meglio di Open prices, ma inferiore a Every tick based on real ticks.",
            15,
        )
    elif "every tick" in low or "ogni tick" in low:
        audit.add("info", "model_every_tick", "Usa Every tick / real ticks: buona base.")
    else:
        audit.add(
            "warn",
            "model_unknown",
            "Qualità del modello di tick non trovata nel report.",
            10,
        )

    if "spread" in low and re.search(r"spread[^0-9]{0,20}(0|1)\b", low):
        audit.add(
            "critical",
            "spread_zero",
            "Spread fisso 0/1 punti: poco realistico su FX retail.",
            25,
        )

    if "delay" in low and re.search(r"delay[^0-9]{0,12}0\b", low):
        audit.add(
            "warn",
            "zero_latency",
            "Delay 0: ignora latenza di rete/broker.",
            10,
        )

    # Unrealistic stats
    pf = re.search(r"profit\s*factor[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)", low)
    if pf and float(pf.group(1)) >= 5.0:
        audit.add(
            "warn",
            "extreme_pf",
            f"Profit factor molto alto ({pf.group(1)}): sospetto senza out-of-sample.",
            15,
        )

    dd = re.search(r"(?:equity\s*)?drawdown[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?)\s*%", low)
    wr = re.search(r"(?:win|profitable)[^%]{0,40}([0-9]+(?:\.[0-9]+)?)\s*%", low)
    if dd and float(dd.group(1)) < 1.0 and wr and float(wr.group(1)) > 90:
        audit.add(
            "critical",
            "too_smooth",
            "Winrate altissimo e drawdown quasi nullo: tipico di curve-fitting / tester ottimistico.",
            30,
        )

    if "genetic" in low or "ottimizz" in low or "optimization" in low:
        audit.add(
            "warn",
            "optimized",
            "Presenza di ottimizzazione: senza walk-forward i risultati sono spesso inaffidabili.",
            15,
        )

    if not audit.findings:
        audit.add("info", "no_flags", "Nessun red-flag ovvio nel testo analizzato.")

    return audit


def audit_mt5_report_file(path: str | Path) -> ReportAudit:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    return audit_mt5_report(text)
