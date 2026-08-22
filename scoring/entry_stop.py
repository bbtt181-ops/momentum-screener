"""Sections 17-19 -- Ideal Entry, Recommended Stop, and the MAX_STOP_PERCENT gate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EntryPlan:
    ideal_entry: float | None = None
    current_price: float | None = None
    distance_to_entry_pct: float | None = None
    extended: bool = False


@dataclass
class StopPlan:
    stop: float | None = None
    method: str = ""
    stop_pct: float | None = None
    risk_per_share: float | None = None
    too_wide: bool = False


def compute_ideal_entry(resistance: float, current_price: float, atr: float, cfg) -> EntryPlan:
    plan = EntryPlan(current_price=current_price)
    if resistance is None:
        return plan

    ideal_entry = resistance * (1 + cfg.entry_buffer_pct)
    plan.ideal_entry = ideal_entry
    plan.distance_to_entry_pct = (current_price - ideal_entry) / ideal_entry if ideal_entry else None

    if atr and current_price > ideal_entry + cfg.max_extension_atr * atr:
        plan.extended = True
    return plan


def compute_recommended_stop(entry_price: float, resistance: float, consolidation_low: float,
                              higher_low_price: float | None, atr: float, cfg) -> StopPlan:
    """
    Picks the structural stop level per the priority in the methodology doc:
    1. Higher Low (if identified) -- tightest defensible invalidation
    2. Consolidation Low -- if no clear Higher Low
    3. Resistance-based -- fallback only, for shallow consolidations
    Applies an ATR buffer below the chosen structural level, then checks
    MAX_STOP_PERCENT. The stop is never moved closer to price to make the
    trade "fit" -- if it's too wide, the setup is flagged, not adjusted.
    """
    plan = StopPlan()
    buffer = (atr or 0) * cfg.atr_stop_multiplier

    if higher_low_price is not None:
        structural_level = min(higher_low_price, consolidation_low) if consolidation_low else higher_low_price
        method = "Higher Low - ATR buffer"
    elif consolidation_low is not None:
        structural_level = consolidation_low
        method = "Consolidation Low - ATR buffer"
    elif resistance is not None:
        structural_level = resistance * 0.97  # fallback for very shallow/undefined lows
        method = "Resistance-based fallback - ATR buffer"
    else:
        return plan

    stop = structural_level - buffer
    plan.stop = stop
    plan.method = method

    if entry_price and stop:
        plan.stop_pct = (entry_price - stop) / entry_price * 100
        plan.risk_per_share = entry_price - stop
        plan.too_wide = plan.stop_pct > cfg.max_stop_percent

    return plan


def stop_quality_score(stop_pct: float | None, cfg) -> float:
    """Tighter, more defensible stops score higher; stops beyond MAX_STOP_PERCENT score near zero."""
    if stop_pct is None:
        return 50.0
    from numpy import clip
    return float(clip((cfg.max_stop_percent - stop_pct) / cfg.max_stop_percent * 100, 0, 100))
