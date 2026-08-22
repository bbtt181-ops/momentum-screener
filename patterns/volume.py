"""Section 15 -- Volume: relative volume, contraction during consolidation, breakout volume.
Never disqualifies a stock on its own -- feeds a 0-100 score only."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_volume_score(df, consolidation, current_row, cfg) -> dict:
    rel_vol_today = float(current_row["RelVolume"]) if pd.notna(current_row["RelVolume"]) else 1.0

    contraction_score = 50.0  # neutral default if we don't have a consolidation window yet
    if consolidation.start_date:
        window = df.loc[consolidation.start_date:consolidation.end_date]
        if len(window) >= 4:
            third = max(1, len(window) // 3)
            vol_first = window["Volume"].iloc[:third].mean()
            vol_last = window["Volume"].iloc[-third:].mean()
            if vol_first and vol_first > 0:
                ratio = vol_last / vol_first
                contraction_score = float(np.clip((1.3 - ratio) / (1.3 - 0.6) * 100, 0, 100))

    # breakout volume: reward relative volume > 1, cap the reward so a single 10x print
    # doesn't dominate the score
    breakout_vol_score = float(np.clip((rel_vol_today - 1.0) / 1.5 * 100, 0, 100))

    volume_score = 0.4 * contraction_score + 0.6 * breakout_vol_score
    return {
        "VolumeScore": round(volume_score, 1),
        "RelativeVolume": round(rel_vol_today, 2),
        "VolumeContractionScore": round(contraction_score, 1),
        "BreakoutVolumeScore": round(breakout_vol_score, 1),
    }
