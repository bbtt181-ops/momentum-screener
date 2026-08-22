"""
Vectorized technical-indicator building blocks shared by every pattern
module. Everything here is computed with pandas rolling/ewm operations so
a full history can be scored in one pass — and, critically, every value at
row i uses only data from rows <= i (no look-ahead).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, window: int) -> pd.Series:
    tr = true_range(df)
    return tr.ewm(span=window, adjust=False).mean()


def adr(df: pd.DataFrame, window: int) -> pd.Series:
    """Average Daily Range %, a common momentum-trader volatility gauge."""
    daily_range_pct = (df["High"] / df["Low"] - 1.0) * 100.0
    return daily_range_pct.rolling(window).mean()


def roc(series: pd.Series, window: int) -> pd.Series:
    return series.pct_change(periods=window) * 100.0


def linreg_slope(series: pd.Series, window: int) -> pd.Series:
    """
    Rolling linear-regression slope, normalized as %-per-bar relative to
    the window's mean price so it's comparable across tickers/price levels.
    """
    def _slope(y):
        if np.any(np.isnan(y)):
            return np.nan
        x = np.arange(len(y))
        slope = np.polyfit(x, y, 1)[0]
        mean_y = np.mean(y) if np.mean(y) != 0 else 1e-9
        return (slope / mean_y) * 100.0

    return series.rolling(window).apply(_slope, raw=True)


def linreg_r2(series: pd.Series, window: int) -> pd.Series:
    """Rolling R^2 of a linear fit -- used as a 'trend consistency' proxy."""
    def _r2(y):
        if np.any(np.isnan(y)):
            return np.nan
        x = np.arange(len(y))
        coeffs = np.polyfit(x, y, 1)
        fit = np.polyval(coeffs, x)
        ss_res = np.sum((y - fit) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        if ss_tot == 0:
            return 0.0
        return 1.0 - ss_res / ss_tot

    return series.rolling(window).apply(_r2, raw=True)


def candle_body(df: pd.DataFrame) -> pd.Series:
    return (df["Close"] - df["Open"]).abs()


def candle_range(df: pd.DataFrame) -> pd.Series:
    return (df["High"] - df["Low"]).replace(0, np.nan)


def clv(df: pd.DataFrame) -> pd.Series:
    """Close Location Value: 0 = closed at the low, 1 = closed at the high."""
    rng = candle_range(df)
    return ((df["Close"] - df["Low"]) / rng).clip(0, 1)


def upper_wick_pct(df: pd.DataFrame) -> pd.Series:
    rng = candle_range(df)
    body_top = df[["Open", "Close"]].max(axis=1)
    return ((df["High"] - body_top) / rng).clip(0, 1)


def candle_overlap(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Average overlap between consecutive candle ranges over a window --
    high overlap (choppy/whipsaw) hurts the CML proxy; low overlap
    (clean directional bars) helps it.
    """
    high, low = df["High"], df["Low"]
    prev_high, prev_low = high.shift(1), low.shift(1)
    overlap = (np.minimum(high, prev_high) - np.maximum(low, prev_low)).clip(lower=0)
    union = (np.maximum(high, prev_high) - np.minimum(low, prev_low)).replace(0, np.nan)
    overlap_ratio = (overlap / union).clip(0, 1)
    return overlap_ratio.rolling(window).mean()


def directional_efficiency(series: pd.Series, window: int) -> pd.Series:
    """
    Kaufman-style efficiency ratio: net displacement / total path length
    over the window. 1.0 = perfectly straight move, ~0 = pure chop.
    """
    net_change = (series - series.shift(window)).abs()
    path_length = series.diff().abs().rolling(window).sum()
    return (net_change / path_length.replace(0, np.nan)).clip(0, 1)


def relative_volume(volume: pd.Series, window: int) -> pd.Series:
    avg = volume.rolling(window).mean()
    return volume / avg.replace(0, np.nan)


def find_fractal_highs(df: pd.DataFrame, n: int) -> pd.Series:
    """Boolean mask: True where High[i] is a local max within +/- n bars."""
    high = df["High"]
    is_max = pd.Series(True, index=df.index)
    for shift in list(range(-n, 0)) + list(range(1, n + 1)):
        is_max &= high >= high.shift(-shift)
    return is_max.fillna(False)


def find_fractal_lows(df: pd.DataFrame, n: int) -> pd.Series:
    low = df["Low"]
    is_min = pd.Series(True, index=df.index)
    for shift in list(range(-n, 0)) + list(range(1, n + 1)):
        is_min &= low <= low.shift(-shift)
    return is_min.fillna(False)


def add_core_indicators(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Attach every reusable indicator column the pattern modules need."""
    out = df.copy()
    out["EMA_fast"] = ema(out["Close"], cfg.ema_fast)
    out["EMA_mid"] = ema(out["Close"], cfg.ema_mid)
    out["EMA_slow"] = ema(out["Close"], cfg.ema_slow)
    out["ATR"] = atr(out, cfg.atr_window)
    out["ADR"] = adr(out, cfg.atr_window)
    out["RelVolume"] = relative_volume(out["Volume"], cfg.volume_avg_window)
    out["Body"] = candle_body(out)
    out["Range"] = candle_range(out)
    out["CLV"] = clv(out)
    out["UpperWickPct"] = upper_wick_pct(out)
    out["EMA_slow_slope"] = linreg_slope(out["EMA_slow"], cfg.first_leg_slope_window)
    out["ROC"] = roc(out["Close"], cfg.first_leg_momentum_window)
    out["Spread8_20"] = (out["EMA_fast"] - out["EMA_mid"]) / out["Close"]
    out["Spread20_50"] = (out["EMA_mid"] - out["EMA_slow"]) / out["Close"]
    out["FractalHigh"] = find_fractal_highs(out, cfg.resistance_fractal)
    out["FractalLow"] = find_fractal_lows(out, cfg.resistance_fractal)
    out["SwingHigh3"] = find_fractal_highs(out, cfg.first_leg_swing_fractal)
    out["SwingLow3"] = find_fractal_lows(out, cfg.first_leg_swing_fractal)
    return out


def resample_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate a daily OHLCV frame into weekly bars (week ending Friday).
    Uses only completed information — the current, still-forming week is
    dropped by the caller when scoring "as of" a specific date to avoid
    look-ahead from a partial week.
    """
    agg = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
    weekly = daily_df.resample("W-FRI").agg(agg).dropna(how="all")
    return weekly
