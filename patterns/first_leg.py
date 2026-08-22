"""
Section 4 -- FIRST LEG detection.

Design note on no-look-ahead (see spec section 28): every score below is
computed row-by-row using pandas rolling/ewm windows that only reach
*backward* from each row. The one nuance is swing-high/low (fractal)
detection, which by definition needs a few bars of *confirmation* after a
pivot to know it was a pivot (standard technical-analysis practice, not
the forbidden kind of look-ahead). Because the caller always truncates the
OHLCV frame to `as_of` (today, by default) before indicators are computed,
the most recent `first_leg_swing_fractal` bars simply won't have a
confirmed swing yet -- which is the correct, honest behavior for a live
scan. The safety-critical signal (BREAKOUT on day T) never depends on
fractal confirmation; it only uses day T's own OHLC plus already-known
history (see patterns/breakout.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _score_price_vs_ema50(df: pd.DataFrame) -> pd.Series:
    dist = (df["Close"] - df["EMA_slow"]) / df["EMA_slow"]
    streak = (df["Close"] > df["EMA_slow"]).astype(int)
    streak = streak.groupby((streak != streak.shift()).cumsum()).cumsum() * streak

    dist_score = (dist / 0.10 * 60).clip(lower=0, upper=60)
    streak_score = (streak.clip(upper=10) / 10 * 40)
    score = (dist_score + streak_score).clip(0, 100)
    score[df["Close"] <= df["EMA_slow"]] = (dist_score[df["Close"] <= df["EMA_slow"]]).clip(lower=0)
    return score.fillna(0)


def _score_ema50_slope(df: pd.DataFrame, cfg) -> pd.Series:
    slope = df["EMA_slow_slope"]
    slope_min, slope_max = -0.5, 1.0  # % per bar, empirically reasonable bounds
    base_score = ((slope - slope_min) / (slope_max - slope_min) * 100).clip(0, 100)

    prior_slope = slope.shift(cfg.first_leg_slope_window)
    turning_up = (prior_slope < 0) & (slope > 0)
    score = base_score + turning_up.astype(int) * 15
    return score.clip(0, 100).fillna(0)


def _score_hh_hl_structure(df: pd.DataFrame, cfg) -> pd.Series:
    lookback = cfg.first_leg_momentum_window * 3
    highs = df["High"].where(df["SwingHigh3"])
    lows = df["Low"].where(df["SwingLow3"])

    def _structure_at(i: int) -> float:
        window_start = max(0, i - lookback)
        recent_highs = highs.iloc[window_start:i + 1].dropna()
        recent_lows = lows.iloc[window_start:i + 1].dropna()
        score = 0.0
        if len(recent_highs) >= 2 and recent_highs.iloc[-1] > recent_highs.iloc[-2]:
            score += 50
        if len(recent_lows) >= 2 and recent_lows.iloc[-1] > recent_lows.iloc[-2]:
            score += 50
        return score

    return pd.Series([_structure_at(i) for i in range(len(df))], index=df.index)


def _score_momentum(df: pd.DataFrame) -> pd.Series:
    roc_score = (df["ROC"] / 20 * 70).clip(0, 70)  # 20% move over window -> near-max
    fifty_two_wk_high = df["Close"].rolling(252, min_periods=20).max()
    fifty_two_wk_low = df["Close"].rolling(252, min_periods=20).min()
    rng = (fifty_two_wk_high - fifty_two_wk_low).replace(0, np.nan)
    position_in_range = ((df["Close"] - fifty_two_wk_low) / rng).clip(0, 1) * 30
    return (roc_score + position_in_range.fillna(15)).clip(0, 100)


def score_weekly_alignment(weekly_df: pd.DataFrame, cfg) -> pd.Series:
    """
    Weekly Trend Reset alignment: price near Weekly EMA8/EMA10 (within
    tolerance) with those EMAs no longer in a steep decline.
    Returns a weekly-indexed 0-100 series; caller reindexes onto daily bars.
    """
    from indicators.core import ema, linreg_slope

    w_ema_fast = ema(weekly_df["Close"], cfg.weekly_ema_fast)
    w_ema_slow = ema(weekly_df["Close"], cfg.weekly_ema_slow)
    w_slope = linreg_slope(w_ema_slow, 5)

    dist_fast = ((weekly_df["Close"] - w_ema_fast) / w_ema_fast).abs()
    dist_slow = ((weekly_df["Close"] - w_ema_slow) / w_ema_slow).abs()
    near_band = (dist_fast <= cfg.first_leg_weekly_tolerance_pct) | (dist_slow <= cfg.first_leg_weekly_tolerance_pct)

    proximity_score = (1 - np.minimum(dist_fast, dist_slow) / cfg.first_leg_weekly_tolerance_pct).clip(0, 1) * 60
    slope_score = ((w_slope + 0.5) / 1.5 * 40).clip(0, 40)  # reward flattening/rising weekly EMA

    score = proximity_score.fillna(0) + slope_score.fillna(0)
    score[~near_band.fillna(False) & (dist_fast > cfg.first_leg_weekly_tolerance_pct * 2)] *= 0.5
    return score.clip(0, 100)


def compute_first_leg(daily_df: pd.DataFrame, weekly_df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Adds First-Leg related columns to daily_df:
      PriceVsEMA50Score, EMA50SlopeScore, HHHLScore, MomentumScore,
      WeeklyAlignmentScore, FirstLegScore, FirstLegConfirmed
    """
    out = daily_df.copy()
    w = cfg.first_leg_weights

    out["PriceVsEMA50Score"] = _score_price_vs_ema50(out)
    out["EMA50SlopeScore"] = _score_ema50_slope(out, cfg)
    out["HHHLScore"] = _score_hh_hl_structure(out, cfg)
    out["MomentumScore"] = _score_momentum(out)

    weekly_score = score_weekly_alignment(weekly_df, cfg)
    out["WeeklyAlignmentScore"] = weekly_score.reindex(out.index, method="ffill").fillna(0)

    out["FirstLegScore"] = (
        out["PriceVsEMA50Score"] * w["price_vs_ema50"]
        + out["EMA50SlopeScore"] * w["ema50_slope"]
        + out["HHHLScore"] * w["hh_hl_structure"]
        + out["MomentumScore"] * w["momentum"]
        + out["WeeklyAlignmentScore"] * w["weekly_alignment"]
    ) / 100.0

    out["FirstLegConfirmed"] = out["FirstLegScore"] >= cfg.first_leg_score_threshold
    return out


def most_recent_first_leg_date(df_with_scores: pd.DataFrame) -> pd.Timestamp | None:
    """
    The First Leg 'anchor date' = the first day the FirstLegScore crosses
    the threshold within the most recent unbroken confirmed run (i.e. the
    start of the current qualifying leg, not every historical crossing).
    """
    confirmed = df_with_scores["FirstLegConfirmed"]
    if not confirmed.any():
        return None
    # walk backward from the end to find the start of the most recent True-run
    idx = confirmed[confirmed].index
    last_true = idx[-1]
    pos = df_with_scores.index.get_loc(last_true)
    start_pos = pos
    while start_pos > 0 and confirmed.iloc[start_pos - 1]:
        start_pos -= 1
    return df_with_scores.index[start_pos]
