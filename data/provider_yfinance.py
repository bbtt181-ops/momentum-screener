"""
yfinance-backed data provider.

yfinance is unofficial (it scrapes Yahoo Finance) and can be rate-limited
or change shape without notice -- that's why it's the *default/prototype*
provider per the methodology doc, with EODHD recommended as the paid,
higher-reliability option for regular/production use (see
provider_eodhd.py, same interface).

No look-ahead: fetch_ohlcv never returns rows beyond `as_of` (defaults to
"today"), and the caller is responsible for only scoring rows that existed
at scan time.
"""

from __future__ import annotations

import datetime as dt
import random
import time

import pandas as pd
import yfinance as yf

from . import cache

# Yahoo throttles/blocks bursts of rapid, back-to-back requests (each ticker
# in a scan is otherwise a brand-new request in well under a second). A
# small randomized delay before each call, plus one retry with a longer
# backoff if the first attempt comes back empty, makes a 200+ ticker scan
# behave like a human clicking around rather than a bot -- this is the fix
# for scans where every single ticker fails with "insufficient history"
# even though a single one-off yf.download() call works fine.
REQUEST_DELAY_RANGE = (0.35, 0.75)
RETRY_BACKOFF_SEC = 2.5


def _throttled_download(ticker: str, **kwargs) -> pd.DataFrame:
    time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    raw = yf.download(ticker, **kwargs)
    if raw is None or raw.empty:
        time.sleep(RETRY_BACKOFF_SEC)
        raw = yf.download(ticker, **kwargs)
    return raw


def fetch_ohlcv(ticker: str, years: int = 3, interval: str = "1d",
                 as_of: dt.date | None = None, use_cache: bool = True) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by Date with Open/High/Low/Close/Volume,
    split/dividend-adjusted (yfinance's auto_adjust=True), truncated to
    `as_of` if given so back-tests / historical scans can't see the future.
    """
    cache_key = interval
    cached = cache.load(ticker, cache_key) if use_cache else None

    start = None
    if cached is not None and not cached.empty:
        start = cached.index.max() - pd.Timedelta(days=5)  # small overlap for adj-close revisions

    period = None if start is not None else f"{years}y"

    raw = _throttled_download(
        ticker,
        start=start.strftime("%Y-%m-%d") if start is not None else None,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
        multi_level_index=False,
    )
    if raw is not None and not raw.empty:
        raw = raw[["Open", "High", "Low", "Close", "Volume"]]
        raw.index.name = "Date"
        if use_cache:
            cache.save(ticker, cache_key, raw)

    merged = raw
    if cached is not None:
        merged = pd.concat([cached, raw]) if raw is not None else cached
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()

    if merged is None or merged.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    if as_of is not None:
        merged = merged[merged.index.date <= as_of]

    return merged


def fetch_fundamentals(ticker: str) -> dict:
    """Returns {'price', 'market_cap', 'avg_volume'} using yfinance's fast_info where possible."""
    time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    t = yf.Ticker(ticker)
    try:
        fi = t.fast_info
        price = float(fi.get("lastPrice", float("nan")))
        market_cap = float(fi.get("marketCap", float("nan")))
        avg_volume = float(fi.get("threeMonthAverageVolume", float("nan")))
    except Exception:
        price = market_cap = avg_volume = float("nan")
    return {"ticker": ticker, "price": price, "market_cap": market_cap, "avg_volume": avg_volume}
