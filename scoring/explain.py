"""Section 25 -- WHY THIS STOCK PASSED / REJECTED."""

from __future__ import annotations


def build_explanation(result: dict) -> dict:
    """
    `result` is the full per-ticker scan result dict produced by scanner.py.
    Returns {"passed": bool, "reasons": [str, ...]} where each reason is
    already prefixed with a check/cross mark, ready to render.
    """
    reasons = []
    passed = result["status"] not in ("REJECTED",)

    fl = result.get("first_leg", {})
    cons = result.get("consolidation", {})
    vcp = result.get("vcp", {})
    res = result.get("resistance_detail", {})
    brk = result.get("breakout", {})
    vol = result.get("volume", {})

    def add(ok: bool, text: str):
        reasons.append(f"{'✓' if ok else '✗'} {text}")

    if not fl.get("confirmed"):
        add(False, f"First Leg not confirmed (score {fl.get('score', 0):.0f}/100, threshold required)")
        return {"passed": False, "reasons": reasons}

    add(True, f"First Leg confirmed on {fl.get('date')} (score {fl.get('score', 0):.0f}/100)")
    add(fl.get("weekly_score", 0) >= 50, f"Weekly alignment score {fl.get('weekly_score', 0):.0f}/100")
    add(result.get("ema_structure_ok", False), "EMA8 > EMA20 > EMA50" if result.get("ema_structure_ok") else "EMA structure not fully stacked")
    add(result.get("ema_expansion_score", 0) >= 50, f"EMA expansion score {result.get('ema_expansion_score', 0):.0f}/100")
    add(result.get("cml_green", False), f"CML {'GREEN' if result.get('cml_green') else 'NOT GREEN'} (score {result.get('cml_score', 0):.0f}/100)")

    if not cons.get("found"):
        reason = cons.get("invalidation_reason") or cons.get("note") or "consolidation does not yet meet the structural minimums"
        add(False, f"First valid consolidation not confirmed -- {reason}")
        return {"passed": False, "reasons": reasons}

    add(True, "First valid consolidation confirmed")
    add(cons.get("days", 0) >= cons.get("min_days", 7), f"{cons.get('days', 0)} consolidation days")
    add(cons.get("higher_low", False), f"Higher Low: {'YES' if cons.get('higher_low') else 'NO'}"
        + (f" at ${cons.get('higher_low_price'):.2f}" if cons.get("higher_low_price") else ""))
    add(cons.get("ema20_violation_days", 0) == 0, "No meaningful close below EMA20"
        if cons.get("ema20_violation_days", 0) == 0 else f"{cons.get('ema20_violation_days')} meaningful close(s) below EMA20")
    add(vcp.get("VCPScore", 0) >= 50, f"VCP Score: {vcp.get('VCPScore', 0):.0f}")
    add(res.get("resistance") is not None, f"Resistance: ${res.get('resistance'):.2f}" if res.get("resistance") else "Resistance not established")

    if brk.get("is_breakout"):
        add(True, "Breakout confirmed")
        add(brk["checks"].get("body_expanding", False), "Body > previous candle")
        atr_mult = brk.get("atr_multiple")
        add(brk["checks"].get("atr_range_ok", False), f"Range = {atr_mult:.1f} ATR" if atr_mult else "ATR range check")
        add(brk["checks"].get("clv_ok", False), f"CLV = {brk.get('clv', 0)*100:.0f}%")
        add(True, f"Relative Volume = {vol.get('RelativeVolume', 0):.1f}x")
    elif result["status"] == "EXTENDED":
        add(False, "Price already extended beyond Ideal Entry -- DO NOT CHASE")
    elif result["status"] == "READY":
        add(True, "Approaching resistance, not yet broken out (READY)")
    else:
        add(True, "In consolidation, not yet near resistance (WATCH)")

    if result.get("stop_too_wide"):
        add(False, f"Structural stop is {result.get('stop_pct', 0):.1f}% -- wider than MAX_STOP_PERCENT -> DO NOT TRADE")

    return {"passed": passed, "reasons": reasons}
