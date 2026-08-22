"""
Section 14 -- Breakout detection.

No-look-ahead by construction: every value used here (Body, Body_prev,
ATR, CLV, UpperWickPct, Close, resistance) is either the evaluated bar's
own OHLC or an already-computed backward-looking indicator / a resistance
level derived strictly from the consolidation window that ended before
this bar. Nothing here ever reads a future row.
"""

from __future__ import annotations

import pandas as pd


def evaluate_breakout(row: pd.Series, prev_row: pd.Series, resistance: float, cfg) -> dict:
    if resistance is None or pd.isna(resistance):
        return {"is_breakout": False, "quality": 0.0, "checks": {}}

    close_above = bool(row["Close"] > resistance)
    body_today = float(row["Body"])
    body_yesterday = float(prev_row["Body"]) if prev_row is not None else 0.0
    body_expanding = body_today > body_yesterday

    atr = float(row["ATR"]) if row["ATR"] and row["ATR"] > 0 else None
    breakout_range = float(row["High"] - row["Low"])
    atr_ok = (atr is not None) and (breakout_range <= cfg.max_breakout_atr * atr)
    atr_multiple = (breakout_range / atr) if atr else None

    clv_val = float(row["CLV"]) if pd.notna(row["CLV"]) else 0.0
    clv_ok = clv_val >= cfg.clv_threshold

    upper_wick = float(row["UpperWickPct"]) if pd.notna(row["UpperWickPct"]) else 1.0
    wick_ok = upper_wick <= cfg.upper_wick_max_pct

    checks = {
        "close_above_resistance": close_above,
        "body_expanding": body_expanding,
        "atr_range_ok": atr_ok,
        "clv_ok": clv_ok,
        "upper_wick_ok": wick_ok,
    }
    is_breakout = all(checks.values())

    # continuous quality score, so READY/near-breakout stocks aren't just pass/fail
    quality = 0.0
    quality += 30 if close_above else max(0, 30 - abs(resistance - row["Close"]) / resistance * 300)
    quality += 15 if body_expanding else 0
    quality += 20 * min(1.0, (cfg.max_breakout_atr / atr_multiple)) if atr_multiple and atr_multiple > 0 else 10
    quality += 20 * (clv_val / cfg.clv_threshold) if cfg.clv_threshold > 0 else 0
    quality += 15 * (1 - min(1.0, upper_wick / cfg.upper_wick_max_pct)) if cfg.upper_wick_max_pct > 0 else 0
    quality = max(0.0, min(100.0, quality))

    return {
        "is_breakout": is_breakout,
        "quality": round(quality, 1),
        "checks": checks,
        "atr_multiple": round(atr_multiple, 2) if atr_multiple else None,
        "clv": round(clv_val, 3),
        "upper_wick_pct": round(upper_wick, 3),
    }
