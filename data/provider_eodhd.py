"""
EODHD-backed data provider (https://eodhd.com) -- the recommended provider
for regular/production use once you're past prototyping with yfinance.
Requires an API key (cfg.eodhd_api_key), set via the Streamlit sidebar or
the EODHD_API_KEY environment variable.

Same interface as provider_yfinance.py (fetch_ohlcv / fetch_fundamentals)
so scanner.py can swap providers via cfg.data_provider without any other
code changes.
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import requests

from . import cache

BASE_URL = "https://eodhd.com/api"


def _api_key(cfg) -> str:
    return cfg.eodhd_api_key or os.environ.get("EODHD_API_KEY", "")


def fetch_ohlcv(ticker: str, cfg, years: int = 3, interval: str = "1d",
                 as_of: dt.date | None = None, use_cache: bool = True) -> pd.DataFrame:
    key = _api_key(cfg)
    if not key:
        raise RuntimeError(
            "EODHD selected as data_provider but no API key is set "
            "(config.eodhd_api_key or EODHD_API_KEY env var)."
        )

    cache_key = f"eodhd_{interval}"
    cached = cache.load(ticker, cache_key) if use_cache else None

    from_date = (dt.date.today() - dt.timedelta(days=365 * years)).strftime("%Y-%m-%d")
    if cached is not None and not cached.empty:
        from_date = (cached.index.max() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")

    symbol = ticker if "." in ticker else f"{ticker}.US"
    resp = requests.get(
        f"{BASE_URL}/eod/{symbol}",
        params={"api_token": key, "period": "d" if interval == "1d" else "w",
                "from": from_date, "fmt": "json"},
        timeout=20,
    )
    resp.raise_for_status()
    rows = resp.json()

    raw = pd.DataFrame(rows)
    if not raw.empty:
        raw["date"] = pd.to_datetime(raw["date"])
        raw = raw.set_index("date").sort_index()
        raw = raw.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })[["Open", "High", "Low", "Close", "Volume"]]
        raw.index.name = "Date"
        if use_cache:
            cache.save(ticker, cache_key, raw)

    merged = raw
    if cached is not None:
        merged = pd.concat([cached, raw]) if not raw.empty else cached
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()

    if merged is None or merged.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    if as_of is not None:
        merged = merged[merged.index.date <= as_of]
    return merged


def fetch_fundamentals(ticker: str, cfg) -> dict:
    key = _api_key(cfg)
    if not key:
        raise RuntimeError("EODHD selected as data_provider but no API key is set.")
    symbol = ticker if "." in ticker else f"{ticker}.US"
    resp = requests.get(
        f"{BASE_URL}/fundamentals/{symbol}",
        params={"api_token": key, "fmt": "json"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    highlights = data.get("Highlights", {}) or {}
    quote = data.get("SharesStats", {}) or {}
    market_cap = highlights.get("MarketCapitalization")
    avg_volume = quote.get("SharesFloat")  # fallback; real avg vol pulled from OHLCV in universe.py
    price = None  # EODHD fundamentals endpoint doesn't include live price; pulled from OHLCV
    return {"ticker": ticker, "price": price, "market_cap": market_cap, "avg_volume": avg_volume}
