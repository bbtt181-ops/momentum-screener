"""
Section 6 -- CML Green Proxy.

This is explicitly NOT a reconstruction of any proprietary "CML Green"
indicator -- it's a transparent proxy built from momentum, linear-regression
slope, trend consistency (R^2), candle overlap, and directional efficiency,
as requested. Every weight is configurable (cfg.cml_weights).
"""

from __future__ import annotations

from indicators.core import linreg_slope, linreg_r2, candle_overlap, directional_efficiency, roc


def compute_cml_proxy(df, cfg):
    out = df.copy()
    w = cfg.cml_weights
    n = cfg.cml_lookback

    momentum_raw = roc(out["Close"], n)
    momentum_score = (momentum_raw / 15 * 100).clip(0, 100)  # 15% move over window -> full score

    slope_raw = linreg_slope(out["Close"], n)
    slope_score = ((slope_raw + 0.2) / 1.0 * 100).clip(0, 100)

    r2 = linreg_r2(out["Close"], n)
    consistency_score = (r2 * 100).clip(0, 100)

    overlap = candle_overlap(out, n)
    overlap_score = ((1 - overlap) * 100).clip(0, 100)  # low overlap = clean directional bars = good

    efficiency = directional_efficiency(out["Close"], n)
    efficiency_score = (efficiency * 100).clip(0, 100)

    cml_score = (
        momentum_score.fillna(0) * w["momentum"]
        + slope_score.fillna(0) * w["linreg_slope"]
        + consistency_score.fillna(0) * w["trend_consistency"]
        + overlap_score.fillna(0) * w["candle_overlap"]
        + efficiency_score.fillna(0) * w["directional_efficiency"]
    ) / 100.0

    out["CMLScore"] = cml_score
    out["CMLGreen"] = cml_score >= cfg.cml_green_threshold
    return out
