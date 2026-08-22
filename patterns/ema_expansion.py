"""Section 5 -- EMA Structure & Expansion Score."""

from __future__ import annotations

import pandas as pd


def compute_ema_expansion(df: pd.DataFrame, cfg) -> pd.DataFrame:
    out = df.copy()

    structure_ok = (out["EMA_fast"] > out["EMA_mid"]) & (out["EMA_mid"] > out["EMA_slow"])
    out["EMAStructureOK"] = structure_ok

    spread8_20_growth = out["Spread8_20"] - out["Spread8_20"].shift(cfg.ema_expansion_lookback)
    spread20_50_growth = out["Spread20_50"] - out["Spread20_50"].shift(cfg.ema_expansion_lookback)

    # normalize growth (as a fraction of price) into 0-100; >2% spread growth over
    # the lookback window is treated as strong expansion
    g1_score = (spread8_20_growth / 0.02 * 50).clip(0, 50)
    g2_score = (spread20_50_growth / 0.02 * 50).clip(0, 50)

    structure_bonus = structure_ok.astype(int) * 0  # structure gates via EMAStructureOK, not double-counted here
    expansion_score = (g1_score.fillna(0) + g2_score.fillna(0)).clip(0, 100)

    # if EMAs aren't in the required order at all, cap the score hard --
    # expansion without the right stacking isn't the momentum setup we want
    expansion_score = expansion_score.where(structure_ok, expansion_score * 0.3)

    out["EMAExpansionScore"] = expansion_score
    return out
