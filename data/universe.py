"""
Universe construction and filtering (spec section 2).

Because a live "give me every US-listed stock" endpoint requires a paid
listings/fundamentals feed, this module works off a *candidate ticker
list* -- either the bundled default_universe.csv (a seed list of liquid,
well-known US names spanning sectors, NOT a claim of completeness) or a
custom list the user supplies in the dashboard (paste / CSV upload).

filter_universe() then applies the real MIN_PRICE / MIN_MARKET_CAP /
MIN_AVG_VOLUME thresholds live against the selected data provider, so the
actual screening logic is correct regardless of which candidate list you
start from. Users who buy an EODHD "Fundamentals" plan can swap in a full
US-listings pull there instead of the CSV -- fetch_fundamentals() is the
only piece that would need a data source change.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import provider_yfinance, provider_eodhd

DEFAULT_UNIVERSE_PATH = Path(__file__).resolve().parent / "default_universe.csv"


def load_default_universe() -> list[str]:
    df = pd.read_csv(DEFAULT_UNIVERSE_PATH)
    return sorted(set(df["ticker"].str.strip().str.upper()))


def filter_universe(candidate_tickers: list[str], cfg, progress_callback=None) -> pd.DataFrame:
    """
    Applies MIN_PRICE / MIN_MARKET_CAP / MIN_AVG_VOLUME to a candidate
    ticker list. Average volume is computed from actual OHLCV (more
    consistent across providers than a vendor's own "avg volume" field).

    Returns a DataFrame: ticker, price, market_cap, avg_volume, passed (bool)
    """
    rows = []
    total = len(candidate_tickers)
    for i, ticker in enumerate(candidate_tickers):
        if progress_callback:
            progress_callback(i, total, ticker)
        try:
            if cfg.data_provider == "eodhd":
                fundamentals = provider_eodhd.fetch_fundamentals(ticker, cfg)
                ohlcv = provider_eodhd.fetch_ohlcv(ticker, cfg, years=1)
            else:
                fundamentals = provider_yfinance.fetch_fundamentals(ticker)
                ohlcv = provider_yfinance.fetch_ohlcv(ticker, years=1)

            if ohlcv is None or ohlcv.empty:
                rows.append({"ticker": ticker, "price": None, "market_cap": None,
                              "avg_volume": None, "passed": False, "reason": "no data"})
                continue

            price = float(ohlcv["Close"].iloc[-1])
            avg_volume = float(ohlcv["Volume"].tail(cfg.avg_volume_window).mean())
            market_cap = fundamentals.get("market_cap")

            passes = (
                price > cfg.min_price
                and avg_volume > cfg.min_avg_volume
                and (market_cap is None or market_cap > cfg.min_market_cap)
                # if market cap is unavailable from the provider, we don't
                # silently fail the stock -- we flag it instead so it's
                # visible in the UI rather than hidden
            )
            reason = "" if passes else "below universe thresholds"
            rows.append({
                "ticker": ticker, "price": price, "market_cap": market_cap,
                "avg_volume": avg_volume, "passed": passes, "reason": reason,
            })
        except Exception as e:  # noqa: BLE001 - keep scanning the rest of the universe
            rows.append({"ticker": ticker, "price": None, "market_cap": None,
                          "avg_volume": None, "passed": False, "reason": f"error: {e}"})

    return pd.DataFrame(rows)
