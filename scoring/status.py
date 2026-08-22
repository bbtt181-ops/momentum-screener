"""Section 16 -- Stock Status classification."""

from __future__ import annotations


def determine_status(first_leg_confirmed: bool, consolidation_found: bool, consolidation_invalidated: bool,
                      is_breakout_today: bool, extended: bool, stop_too_wide: bool,
                      distance_to_entry_pct: float | None, cfg) -> str:
    """
    Returns one of: BREAKOUT, EXTENDED, READY, WATCH, REJECTED.
    Overlay flags (DO NOT CHASE / DO NOT TRADE - STOP TOO WIDE) are
    reported alongside status by the caller, not folded into this string,
    so the UI can show both the state and the reason clearly.
    """
    if not first_leg_confirmed or consolidation_invalidated:
        return "REJECTED"

    if not consolidation_found:
        return "REJECTED"

    if is_breakout_today and not extended:
        return "BREAKOUT"

    if extended:
        return "EXTENDED"

    if distance_to_entry_pct is not None and distance_to_entry_pct >= -cfg.ready_proximity_pct:
        return "READY"

    return "WATCH"
