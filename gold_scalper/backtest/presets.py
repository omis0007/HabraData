"""Asset presets for MR scalper + same-direction grid.

Distances are in price units of the symbol (USD for gold, index points for CFDs).
ATR multipliers are calibrated from the live XAU fingerprint (~ATR_M1 ≈ 4).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from typing import Dict, Tuple

# Shared oscillator defaults
_OSC = dict(
    stoch_period=14,
    stoch_k=3,
    stoch_oversold=10.0,
    stoch_overbought=90.0,
    use_demarker=False,
    demarker_period=14,
    demarker_oversold=0.30,
    demarker_overbought=0.70,
    ema_period=20,
    max_positions=5,
)

# ATR× multipliers (from gold: TP1.5 / grid6 / stretch14 / move3=5 / basket0.4 @ ATR≈4)
ATR_MULT = dict(
    solo_tp=0.375,
    basket_tp=0.10,
    grid_step=1.50,
    stretch_min=3.50,
    move3_against_min=1.25,
)

PRESETS: Dict[str, dict] = {
    "XAU": {
        **_OSC,
        "asset": "XAU",
        "use_atr": False,
        "stretch_min": 14.0,
        "move3_against_min": 5.0,
        "solo_tp": 1.5,
        "basket_tp": 0.40,
        "grid_step": 6.0,
        "lot": 0.05,
        "trade_hours": (2, 3, 4, 5, 6, 9, 10, 11, 15, 16, 17, 18),
        "point_value_per_lot": 100.0,
        "contract_size": 100.0,
        "note": "Gold / XAUUSD — matched to Equiti live fingerprint",
    },
    "NAS100": {
        **_OSC,
        "asset": "NAS100",
        "use_atr": False,
        "stretch_min": 55.0,
        "move3_against_min": 20.0,
        "solo_tp": 12.0,
        "basket_tp": 3.0,
        "grid_step": 40.0,
        "lot": 0.10,
        "trade_hours": (13, 14, 15, 16, 17, 18, 19, 20),
        "point_value_per_lot": 1.0,  # $1 / point / 1.0 lot (check your CFD)
        "contract_size": 1.0,
        "note": "NAS100 / USTEC / NAS100.cash — US cash session UTC",
    },
    "US30": {
        **_OSC,
        "asset": "US30",
        "use_atr": False,
        "stretch_min": 100.0,
        "move3_against_min": 35.0,
        "solo_tp": 20.0,
        "basket_tp": 5.0,
        "grid_step": 70.0,
        "lot": 0.10,
        "trade_hours": (13, 14, 15, 16, 17, 18, 19, 20),
        "point_value_per_lot": 1.0,
        "contract_size": 1.0,
        "note": "US30 / DJ30 / Wall Street — US cash session UTC",
    },
    "ATR_AUTO": {
        **_OSC,
        "asset": "ATR_AUTO",
        "use_atr": True,
        "atr_period": 14,
        "atr_solo_tp": ATR_MULT["solo_tp"],
        "atr_basket_tp": ATR_MULT["basket_tp"],
        "atr_grid_step": ATR_MULT["grid_step"],
        "atr_stretch_min": ATR_MULT["stretch_min"],
        "atr_move3_against_min": ATR_MULT["move3_against_min"],
        "stretch_min": 0.0,
        "move3_against_min": 0.0,
        "solo_tp": 0.0,
        "basket_tp": 0.0,
        "grid_step": 0.0,
        "lot": 0.10,
        "trade_hours": (13, 14, 15, 16, 17, 18, 19, 20),
        "point_value_per_lot": 1.0,
        "contract_size": 1.0,
        "note": "Any symbol — distances = ATR(M1)× multipliers (gold-calibrated)",
    },
}


def list_presets() -> Tuple[str, ...]:
    return tuple(PRESETS.keys())


def get_preset(name: str) -> dict:
    key = name.upper().replace(" ", "").replace("-", "")
    aliases = {
        "XAUUSD": "XAU",
        "GOLD": "XAU",
        "NAS": "NAS100",
        "USTEC": "NAS100",
        "NASDAQ": "NAS100",
        "US100": "NAS100",
        "DJ30": "US30",
        "DJIA": "US30",
        "WALLSTREET": "US30",
        "ATRAUTO": "ATR_AUTO",
        "AUTO": "ATR_AUTO",
    }
    key = aliases.get(key, key)
    if key not in PRESETS:
        raise KeyError(f"Unknown preset {name!r}. Available: {', '.join(PRESETS)}")
    return deepcopy(PRESETS[key])


def apply_preset_to_params(params, name: str):
    """Mutate a Params dataclass from preset name."""
    preset = get_preset(name)
    valid = {f.name for f in fields(type(params))}
    for k, v in preset.items():
        if k in ("note",):
            continue
        if k in valid:
            setattr(params, k, v)
    return params
