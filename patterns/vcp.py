"""Section 11 -- Volatility Contraction Pattern score (approximate, weighted, non-binary)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _ratio_to_score(ratio: float, good_at: float = 0.6, bad_at: float = 1.1) -> float:
    """Smaller ratio (more contraction) => higher score. Linear map, clipped."""
    if ratio is None or np.isnan(ratio):
        return 0.0
    if ratio <= good_at:
        return 100.0
    if ratio >= bad_at:
        return 0.0
    return float((bad_at - ratio) / (bad_at - good_at) * 100.0)


def compute_vcp_score(df: pd.DataFrame, consolidation, cfg) -> dict:
    if not consolidation.start_date:
        return {"VCPScore": 0.0, "components": {}}

    window = df.loc[consolidation.start_date:consolidation.end_date]
    if len(window) < 3:
        return {"VCPScore": 0.0, "components": {}}

    half = max(1, len(window) // 2)
    third = max(1, len(window) // 3)

    # ATR contraction: end-of-window ATR vs start-of-window ATR
    atr_start = window["ATR"].iloc[:third].mean()
    atr_end = window["ATR"].iloc[-third:].mean()
    atr_ratio = atr_end / atr_start if atr_start and not np.isnan(atr_start) and atr_start > 0 else np.nan
    atr_score = _ratio_to_score(atr_ratio)

    # Range contraction: daily range, second half vs first half
    range_first = (window["High"] - window["Low"]).iloc[:half].mean()
    range_second = (window["High"] - window["Low"]).iloc[half:].mean()
    range_ratio = range_second / range_first if range_first and range_first > 0 else np.nan
    range_score = _ratio_to_score(range_ratio)

    # Swing contraction: amplitude of successive swings (using High-Low of rolling 3-bar windows) shrinking
    swing_amp = (window["High"].rolling(3).max() - window["Low"].rolling(3).min()).dropna()
    if len(swing_amp) >= 4:
        swing_ratio = swing_amp.iloc[-len(swing_amp)//2:].mean() / swing_amp.iloc[:len(swing_amp)//2].mean()
    else:
        swing_ratio = np.nan
    swing_score = _ratio_to_score(swing_ratio)

    # Tightening: std of closes, second half vs first half
    std_first = window["Close"].iloc[:half].std()
    std_second = window["Close"].iloc[half:].std()
    tighten_ratio = std_second / std_first if std_first and std_first > 0 else np.nan
    tighten_score = _ratio_to_score(tighten_ratio)

    # Volume contraction: last third vs first third average volume
    vol_first = window["Volume"].iloc[:third].mean()
    vol_last = window["Volume"].iloc[-third:].mean()
    vol_ratio = vol_last / vol_first if vol_first and vol_first > 0 else np.nan
    vol_score = _ratio_to_score(vol_ratio, good_at=0.7, bad_at=1.3)

    components = {
        "atr_contraction": atr_score,
        "range_contraction": range_score,
        "swing_contraction": swing_score,
        "tightening": tighten_score,
        "volume_contraction": vol_score,
    }
    w = cfg.vcp_weights
    total = sum(components[k] * w[k] for k in components) / 100.0
    return {"VCPScore": round(total, 1), "components": components}
