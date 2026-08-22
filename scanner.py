"""
Orchestrates the full pipeline (sections 4-21 of the spec) for a single
ticker, and a thin wrapper to run it across a universe. This is the one
place that ties data -> indicators -> patterns -> scoring together, so the
Streamlit app and any future CLI/tests just call scan_ticker()/scan_universe().
"""

from __future__ import annotations

import datetime as dt
import traceback

import pandas as pd

from config import ScreenerConfig
from data import provider_yfinance, provider_eodhd
from indicators.core import add_core_indicators, resample_weekly
from patterns.first_leg import compute_first_leg, most_recent_first_leg_date
from patterns.ema_expansion import compute_ema_expansion
from patterns.cml_proxy import compute_cml_proxy
from patterns.consolidation import find_first_valid_consolidation, compute_consolidation_quality
from patterns.vcp import compute_vcp_score
from patterns.resistance import find_resistance, resistance_quality_score
from patterns.breakout import evaluate_breakout
from patterns.volume import compute_volume_score
from scoring.entry_stop import compute_ideal_entry, compute_recommended_stop, stop_quality_score
from scoring.status import determine_status
from scoring.setup_score import compute_entry_quality, compute_setup_score
from scoring.explain import build_explanation

MIN_BARS_REQUIRED = 80  # need enough history for EMA50 + lookback windows to be meaningful


def _fetch_daily(ticker: str, cfg: ScreenerConfig, as_of: dt.date | None) -> pd.DataFrame:
    if cfg.data_provider == "eodhd":
        return provider_eodhd.fetch_ohlcv(ticker, cfg, years=cfg.daily_history_years, interval="1d", as_of=as_of)
    return provider_yfinance.fetch_ohlcv(ticker, years=cfg.daily_history_years, interval="1d", as_of=as_of)


def scan_ticker(ticker: str, cfg: ScreenerConfig, as_of: dt.date | None = None) -> dict:
    """Fetches OHLCV for `ticker` via the configured provider, then runs the full pipeline."""
    daily = _fetch_daily(ticker, cfg, as_of)
    return scan_ticker_from_df(ticker, daily, cfg, as_of)


def scan_ticker_from_df(ticker: str, daily: pd.DataFrame, cfg: ScreenerConfig,
                         as_of: dt.date | None = None) -> dict:
    """
    Runs the full pipeline (indicators -> patterns -> scoring) against an
    already-fetched daily OHLCV DataFrame. Kept separate from scan_ticker()
    so tests can inject synthetic data without hitting a network provider.
    """
    result = {"ticker": ticker, "ok": False, "error": None}
    try:
        if daily is None or len(daily) < MIN_BARS_REQUIRED:
            result["error"] = f"insufficient history ({0 if daily is None else len(daily)} bars)"
            return result

        daily = add_core_indicators(daily, cfg)
        weekly = resample_weekly(daily)

        daily = compute_first_leg(daily, weekly, cfg)
        daily = compute_ema_expansion(daily, cfg)
        daily = compute_cml_proxy(daily, cfg)

        first_leg_date = most_recent_first_leg_date(daily)
        current_row = daily.iloc[-1]
        prev_row = daily.iloc[-2]

        consolidation = find_first_valid_consolidation(daily, first_leg_date, cfg)
        vcp_result = compute_vcp_score(daily, consolidation, cfg)
        resistance_result = find_resistance(daily, consolidation, cfg)
        breakout_result = evaluate_breakout(current_row, prev_row, resistance_result.get("resistance"), cfg)
        volume_result = compute_volume_score(daily, consolidation, current_row, cfg)

        atr_val = float(current_row["ATR"]) if pd.notna(current_row["ATR"]) else None
        entry_plan = compute_ideal_entry(resistance_result.get("resistance"), float(current_row["Close"]), atr_val, cfg)

        higher_low_price = consolidation.higher_low_price if consolidation.higher_low else None
        stop_plan = compute_recommended_stop(
            entry_plan.ideal_entry or float(current_row["Close"]),
            resistance_result.get("resistance"),
            consolidation.consolidation_low,
            higher_low_price,
            atr_val,
            cfg,
        )

        status = determine_status(
            first_leg_confirmed=bool(first_leg_date is not None),
            consolidation_found=consolidation.found,
            consolidation_invalidated=consolidation.invalidated,
            is_breakout_today=breakout_result["is_breakout"],
            extended=entry_plan.extended,
            stop_too_wide=stop_plan.too_wide,
            distance_to_entry_pct=entry_plan.distance_to_entry_pct,
            cfg=cfg,
        )

        consolidation_quality = compute_consolidation_quality(consolidation, cfg)
        resistance_quality = resistance_quality_score(resistance_result.get("strength", 0))
        ema_structure_ok = bool(current_row.get("EMAStructureOK", False))

        entry_quality = compute_entry_quality(
            distance_to_entry_pct=entry_plan.distance_to_entry_pct,
            close=float(current_row["Close"]),
            ema20=float(current_row["EMA_mid"]) if pd.notna(current_row["EMA_mid"]) else None,
            breakout_quality=breakout_result["quality"],
            atr=atr_val,
            current_price=float(current_row["Close"]),
            ideal_entry=entry_plan.ideal_entry,
            stop_pct=stop_plan.stop_pct,
            cfg=cfg,
        )
        stop_quality = stop_quality_score(stop_plan.stop_pct, cfg)

        components = {
            "first_leg": float(current_row["FirstLegScore"]),
            "weekly_alignment": float(current_row["WeeklyAlignmentScore"]),
            "ema_structure": 100.0 if ema_structure_ok else 30.0,
            "ema_expansion": float(current_row["EMAExpansionScore"]),
            "cml": float(current_row["CMLScore"]),
            "consolidation_quality": consolidation_quality,
            "vcp": vcp_result["VCPScore"],
            "higher_low": 100.0 if consolidation.higher_low else 0.0,
            "resistance_quality": resistance_quality,
            "breakout_quality": breakout_result["quality"],
            "volume": volume_result["VolumeScore"],
            "entry_quality": entry_quality,
            "stop_quality": stop_quality,
        }
        setup = compute_setup_score(components, cfg)

        if stop_plan.too_wide:
            setup["Grade"] = "REJECT"

        result.update({
            "ok": True,
            "as_of": (as_of or daily.index[-1].date()),
            "price": float(current_row["Close"]),
            "status": status,
            "setup_score": setup["SetupScore"],
            "grade": setup["Grade"],
            "components": components,
            "resistance": resistance_result.get("resistance"),
            "resistance_strength": resistance_result.get("strength"),
            "resistance_method": resistance_result.get("method"),
            "ideal_entry": entry_plan.ideal_entry,
            "distance_to_entry_pct": entry_plan.distance_to_entry_pct,
            "extended": entry_plan.extended,
            "stop": stop_plan.stop,
            "stop_pct": stop_plan.stop_pct,
            "stop_method": stop_plan.method,
            "risk_per_share": stop_plan.risk_per_share,
            "stop_too_wide": stop_plan.too_wide,
            "ema_structure_ok": ema_structure_ok,
            "ema_expansion_score": float(current_row["EMAExpansionScore"]),
            "cml_score": float(current_row["CMLScore"]),
            "cml_green": bool(current_row["CMLGreen"]),
            "atr": atr_val,
            "adr": float(current_row["ADR"]) if pd.notna(current_row["ADR"]) else None,
            "ema8": float(current_row["EMA_fast"]),
            "ema20": float(current_row["EMA_mid"]),
            "ema50": float(current_row["EMA_slow"]),
            "weekly_ema8": float(weekly["Close"].ewm(span=cfg.weekly_ema_fast, adjust=False).mean().iloc[-1]) if len(weekly) else None,
            "weekly_ema10": float(weekly["Close"].ewm(span=cfg.weekly_ema_slow, adjust=False).mean().iloc[-1]) if len(weekly) else None,
            "first_leg": {
                "confirmed": first_leg_date is not None,
                "date": first_leg_date,
                "score": float(current_row["FirstLegScore"]),
                "weekly_score": float(current_row["WeeklyAlignmentScore"]),
            },
            "consolidation": {
                "found": consolidation.found,
                "start_date": consolidation.start_date,
                "end_date": consolidation.end_date,
                "days": consolidation.days,
                "min_days": cfg.min_consolidation_days,
                "higher_low": consolidation.higher_low,
                "higher_low_price": consolidation.higher_low_price,
                "higher_low_date": consolidation.higher_low_date,
                "consolidation_low": consolidation.consolidation_low,
                "ema20_violation_days": consolidation.ema20_violation_days,
                "invalidated": consolidation.invalidated,
                "invalidation_reason": consolidation.invalidation_reason,
                "note": "; ".join(consolidation.notes) if consolidation.notes else None,
            },
            "vcp": vcp_result,
            "resistance_detail": resistance_result,
            "breakout": breakout_result,
            "volume": volume_result,
            "daily_df": daily,
            "weekly_df": weekly,
        })
        result["explanation"] = build_explanation(result)
        return result

    except Exception as e:  # noqa: BLE001 - keep scanning the rest of the universe on a single failure
        result["ok"] = False
        result["error"] = f"{e}\n{traceback.format_exc()}"
        return result


def scan_universe(tickers: list[str], cfg: ScreenerConfig, as_of: dt.date | None = None,
                   progress_callback=None) -> list[dict]:
    results = []
    total = len(tickers)
    for i, ticker in enumerate(tickers):
        if progress_callback:
            progress_callback(i, total, ticker)
        results.append(scan_ticker(ticker, cfg, as_of))
    return results
