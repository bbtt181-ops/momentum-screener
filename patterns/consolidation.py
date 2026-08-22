"""
Section 7-10 -- FIRST VALID CONSOLIDATION, pullback-to-EMA, EMA20 rule,
and Higher Low.

Runs *after* a First Leg date is known (patterns/first_leg.py). Walks
forward day by day from the first confirmed swing-high pivot following the
leg, and returns the first window that satisfies every structural rule --
mirroring the "first one that qualifies wins, don't keep searching"
behavior requested in the spec. If that window later breaks down
(meaningful close below EMA20 too many times, or a break of the
consolidation low), it is marked invalidated and no replacement
consolidation is searched for the same leg.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ConsolidationResult:
    found: bool = False
    start_date: pd.Timestamp | None = None
    end_date: pd.Timestamp | None = None          # last bar considered part of the window (as of scan date)
    days: int = 0
    pivot_high_price: float | None = None
    consolidation_low: float | None = None
    higher_low: bool = False
    higher_low_price: float | None = None
    higher_low_date: pd.Timestamp | None = None
    touched_ema: bool = False
    ema20_violation_days: int = 0
    invalidated: bool = False
    invalidation_reason: str = ""
    range_contraction_ratio: float | None = None
    notes: list = field(default_factory=list)


def _prior_leg_range(df: pd.DataFrame, first_leg_date: pd.Timestamp, pivot_idx: int) -> float:
    leg_slice = df.loc[first_leg_date:df.index[pivot_idx]]
    if leg_slice.empty:
        return np.nan
    return float(leg_slice["High"].max() - leg_slice["Low"].min())


def compute_consolidation_quality(result: "ConsolidationResult", cfg) -> float:
    """0-100 quality score for the consolidation structure itself (length,
    EMA discipline, range contraction) -- feeds into the overall Setup Score."""
    if not result.start_date:
        return 0.0

    days_score = min(100.0, (result.days / max(1, cfg.min_consolidation_days)) * 60)
    days_score = min(days_score, 100.0)

    violation_score = max(0.0, 100.0 - result.ema20_violation_days * 35.0)

    contraction_score = 50.0
    if result.range_contraction_ratio is not None and not np.isnan(result.range_contraction_ratio):
        contraction_score = float(np.clip((1.0 - result.range_contraction_ratio) / (1.0 - 0.4) * 100, 0, 100))

    higher_low_bonus = 15.0 if result.higher_low else 0.0

    score = 0.35 * days_score + 0.25 * violation_score + 0.25 * contraction_score + 0.15 * (higher_low_bonus / 15 * 100)
    return round(float(np.clip(score, 0, 100)), 1)


def find_first_valid_consolidation(df: pd.DataFrame, first_leg_date: pd.Timestamp, cfg) -> ConsolidationResult:
    result = ConsolidationResult()
    if first_leg_date is None or first_leg_date not in df.index:
        return result

    start_pos = df.index.get_loc(first_leg_date)
    search_end_pos = min(len(df) - 1, start_pos + cfg.max_consolidation_search_days)
    window_df = df.iloc[start_pos:search_end_pos + 1]

    # candidate pivot high = first confirmed swing high after the leg starts
    swing_highs = window_df.index[window_df["SwingHigh3"]]
    if len(swing_highs) == 0:
        result.notes.append("no confirmed swing high yet after First Leg -- leg may still be extending")
        return result

    pivot_date = swing_highs[0]
    pivot_pos = df.index.get_loc(pivot_date)
    pivot_price = float(df.loc[pivot_date, "High"])

    # reference low = the swing low the leg launched from (used for Higher Low comparison)
    pre_leg_slice = df.iloc[max(0, start_pos - 20):start_pos + 1]
    pre_leg_low = float(pre_leg_slice["Low"].min()) if not pre_leg_slice.empty else np.nan

    tol = cfg.ema_pullback_tolerance_pct
    close_violation_pct = cfg.ema20_close_violation_pct

    consolidation_slice = df.iloc[pivot_pos:search_end_pos + 1]
    if consolidation_slice.empty:
        return result

    running_low = np.inf
    ema20_violations = 0
    touched_ema = False
    invalidated = False
    invalidation_reason = ""
    valid_from_day = None

    for offset, (date, row) in enumerate(consolidation_slice.iterrows(), start=1):
        running_low = min(running_low, row["Low"])

        if row["Low"] <= row["EMA_fast"] * (1 + tol) or row["Low"] <= row["EMA_mid"] * (1 + tol):
            touched_ema = True

        meaningful_violation = row["Close"] < row["EMA_mid"] * (1 - close_violation_pct)
        if meaningful_violation:
            ema20_violations += 1

        if ema20_violations > cfg.ema20_max_violation_days:
            invalidated = True
            invalidation_reason = f"close below EMA20 by >{close_violation_pct:.1%} on {ema20_violations} occasions"
            break

        if running_low < pre_leg_low:
            invalidated = True
            invalidation_reason = "price broke below the level the First Leg launched from -- leg structure invalidated"
            break

        if offset >= cfg.min_consolidation_days and touched_ema and valid_from_day is None:
            valid_from_day = offset  # structural minimum satisfied as of this bar

    days_covered = len(consolidation_slice)
    range_contraction = None
    prior_range = _prior_leg_range(df, first_leg_date, pivot_pos)
    if prior_range and prior_range > 0:
        cons_range = float(consolidation_slice["High"].max() - consolidation_slice["Low"].min())
        range_contraction = cons_range / prior_range

    # Higher Low: lowest low reached during (the valid portion of) the consolidation vs. the pre-leg low
    cons_low_price = float(consolidation_slice["Low"].min())
    cons_low_date = consolidation_slice["Low"].idxmin()
    higher_low = cons_low_price > pre_leg_low * (1 + cfg.higher_low_min_gap_pct)

    result.pivot_high_price = pivot_price
    result.start_date = pivot_date
    result.end_date = consolidation_slice.index[-1]
    result.days = days_covered
    result.consolidation_low = cons_low_price
    result.higher_low = bool(higher_low)
    result.higher_low_price = cons_low_price
    result.higher_low_date = cons_low_date
    result.touched_ema = bool(touched_ema)
    result.ema20_violation_days = int(ema20_violations)
    result.invalidated = bool(invalidated)
    result.invalidation_reason = invalidation_reason
    result.range_contraction_ratio = range_contraction
    result.found = (
        not invalidated
        and days_covered >= cfg.min_consolidation_days
        and touched_ema
    )
    if not result.found and not invalidated:
        result.notes.append(
            f"consolidation still building: {days_covered}/{cfg.min_consolidation_days} days, "
            f"EMA pullback touched={touched_ema}"
        )
    return result
