"""Section 13 -- Resistance identification (pivot cluster within the consolidation window)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def resistance_quality_score(strength: int) -> float:
    """More touches confirming the level = stronger, more reliable resistance."""
    return float(np.clip(strength / 4 * 100, 20, 100))


def find_resistance(df: pd.DataFrame, consolidation, cfg) -> dict:
    if not consolidation.start_date:
        return {"resistance": None, "strength": 0, "method": "none"}

    window = df.loc[consolidation.start_date:consolidation.end_date]
    pivots = window.loc[window["FractalHigh"], "High"]

    if pivots.empty:
        # fallback: the window's own high
        return {
            "resistance": float(window["High"].max()),
            "strength": 1,
            "method": "consolidation high (no clear pivot cluster)",
        }

    tol = cfg.resistance_cluster_tolerance_pct
    pivot_values = sorted(pivots.values)

    # cluster nearby pivots together
    clusters = []
    current_cluster = [pivot_values[0]]
    for v in pivot_values[1:]:
        if v <= current_cluster[-1] * (1 + tol):
            current_cluster.append(v)
        else:
            clusters.append(current_cluster)
            current_cluster = [v]
    clusters.append(current_cluster)

    best_cluster = max(clusters, key=len)
    resistance_level = float(np.mean(best_cluster))
    strength = len(best_cluster)

    return {
        "resistance": resistance_level,
        "strength": strength,
        "method": f"pivot cluster ({strength} touch{'es' if strength != 1 else ''})",
    }
