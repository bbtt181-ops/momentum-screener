"""Sections 20-21 -- Entry Quality Score, overall Setup Score, and A+/A/B/C/REJECT grading."""

from __future__ import annotations

import numpy as np


def compute_entry_quality(distance_to_entry_pct, close, ema20, breakout_quality,
                           atr, current_price, ideal_entry, stop_pct, cfg) -> float:
    w = cfg.entry_quality_weights

    dist_res_score = float(np.clip(100 - abs(distance_to_entry_pct or 0) * 1000, 0, 100)) if distance_to_entry_pct is not None else 50

    ema20_dist_pct = ((close - ema20) / ema20) if ema20 else 0
    ema20_score = float(np.clip(100 - abs(ema20_dist_pct) * 500, 0, 100))

    breakout_score = breakout_quality or 0

    atr_ext_score = 50
    if atr and current_price and ideal_entry:
        ext_in_atr = max(0, (current_price - ideal_entry)) / atr if atr > 0 else 0
        atr_ext_score = float(np.clip(100 - ext_in_atr * 40, 0, 100))

    stop_score = 50
    if stop_pct is not None:
        stop_score = float(np.clip((cfg.max_stop_percent - stop_pct) / cfg.max_stop_percent * 100, 0, 100))

    price_vs_entry_score = dist_res_score  # same underlying distance metric, separate weight slot per spec

    total = (
        dist_res_score * w["distance_from_resistance"]
        + ema20_score * w["distance_from_ema20"]
        + breakout_score * w["breakout_strength"]
        + atr_ext_score * w["atr_extension"]
        + stop_score * w["stop_distance"]
        + price_vs_entry_score * w["price_vs_ideal_entry"]
    ) / 100.0
    return round(float(np.clip(total, 0, 100)), 1)


def compute_setup_score(components: dict, cfg) -> dict:
    """
    components must contain (0-100 each, or None if not applicable):
      first_leg, weekly_alignment, ema_structure, ema_expansion, cml,
      consolidation_quality, vcp, higher_low, resistance_quality,
      breakout_quality, volume, entry_quality, stop_quality
    """
    w = cfg.setup_score_weights
    total_weight = 0.0
    total_score = 0.0
    for key, weight in w.items():
        val = components.get(key)
        if val is None:
            continue
        total_score += val * weight
        total_weight += weight

    setup_score = round(total_score / total_weight, 1) if total_weight > 0 else 0.0
    grade = grade_from_score(setup_score, cfg)
    return {"SetupScore": setup_score, "Grade": grade}


def grade_from_score(score: float, cfg) -> str:
    bands = cfg.grade_bands
    if score >= bands["A+"]:
        return "A+"
    if score >= bands["A"]:
        return "A"
    if score >= bands["B"]:
        return "B"
    if score >= bands["C"]:
        return "C"
    return "REJECT"
