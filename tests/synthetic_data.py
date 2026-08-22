"""
Builds a synthetic daily OHLCV series with a deliberately engineered:
  flat/declining base -> First Leg up-move -> pullback consolidation with
  a Higher Low and EMA8/20 touches -> tight VCP-style contraction ->
  a clean breakout day.

This lets the pipeline be tested end-to-end without any network access,
which this sandbox doesn't have to Yahoo/EODHD. It is NOT meant to
validate the *market* accuracy of the setup definitions -- only that the
code correctly detects the pattern it was explicitly built to contain, and
doesn't crash on real-shaped data (proper OHLC relationships, volume,
weekends excluded, etc).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_synthetic_series(seed: int = 7, tail_days: int = 0) -> pd.DataFrame:
    """
    tail_days: extra random-walk bars appended after the engineered breakout,
    useful for testing "days later" states (EXTENDED, drift, etc). 0 by
    default so the last bar of the returned frame IS the engineered
    breakout+follow-through, matching what the assertions in
    test_pipeline.py expect.
    """
    rng = np.random.default_rng(seed)

    closes = []
    price = 40.0

    # 1) Declining/basing phase (~100 days) so EMA50 starts flat/down
    for i in range(100):
        price += rng.normal(-0.02, 0.35)
        price = max(price, 25)
        closes.append(price)

    # 2) First Leg: a real, momentum-y up move over ~25 days
    for i in range(25):
        price *= 1 + rng.normal(0.018, 0.012)
        closes.append(price)

    # 3) Consolidation: ~14 days, gentle pullback toward EMA8/20, tightening range,
    #    with a Higher Low relative to the base before the leg
    for i in range(14):
        pullback_factor = -0.006 if i < 7 else 0.001
        price *= 1 + rng.normal(pullback_factor, 0.006)
        closes.append(price)

    # 4) Tight final squeeze (last few bars of consolidation, VCP-style contraction)
    for i in range(4):
        price *= 1 + rng.normal(0.001, 0.003)
        closes.append(price)

    # 5) Breakout day: strong expansion candle closing near the high
    breakout_close = max(closes[-5:]) * 1.045
    closes.append(breakout_close)

    # 6) A couple of follow-through days
    for i in range(2):
        price = closes[-1] * (1 + rng.normal(0.01, 0.01))
        closes.append(price)

    # 7) optional extra tail (random walk) for testing later-day states
    for i in range(tail_days):
        price = closes[-1] * (1 + rng.normal(0.0, 0.015))
        closes.append(price)

    dates = pd.bdate_range("2024-01-02", periods=len(closes))
    closes = np.array(closes)

    opens = np.empty_like(closes)
    opens[0] = closes[0]
    opens[1:] = closes[:-1] * (1 + rng.normal(0, 0.003, size=len(closes) - 1))

    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0.004, 0.003, size=len(closes))))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0.004, 0.003, size=len(closes))))

    base_volume = 1_500_000
    volumes = base_volume * (1 + np.abs(rng.normal(0, 0.3, size=len(closes))))
    # volume contraction into the consolidation, expansion on breakout
    cons_start = 125
    breakout_idx = 143
    if breakout_idx < len(volumes):
        volumes[cons_start:breakout_idx] *= np.linspace(1.0, 0.55, breakout_idx - cons_start)
        volumes[breakout_idx] *= 2.8

    df = pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes,
    }, index=dates[:len(closes)])
    df.index.name = "Date"
    return df
