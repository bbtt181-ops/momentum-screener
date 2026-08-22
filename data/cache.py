"""
Lightweight SQLite cache for OHLCV bars so repeated scans (and Streamlit
reruns) don't re-hit the data provider's rate limits every time a slider
in the sidebar moves.

Cache key = (ticker, interval). We store the full bar history we've seen
and merge in new rows on each fetch; the provider layer decides how far
back to ask for.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "cache" / "ohlcv_cache.sqlite"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv (
            ticker TEXT NOT NULL,
            interval TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (ticker, interval, date)
        )
    """)
    return conn


def load(ticker: str, interval: str) -> pd.DataFrame | None:
    conn = _connect()
    try:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM ohlcv "
            "WHERE ticker = ? AND interval = ? ORDER BY date",
            conn, params=(ticker, interval), parse_dates=["date"],
        )
    finally:
        conn.close()
    if df.empty:
        return None
    df = df.set_index("date")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    df.index.name = "Date"
    return df


def save(ticker: str, interval: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    conn = _connect()
    try:
        rows = [
            (ticker, interval, idx.strftime("%Y-%m-%d %H:%M:%S"),
             float(r["Open"]), float(r["High"]), float(r["Low"]),
             float(r["Close"]), float(r["Volume"]))
            for idx, r in df.iterrows()
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO ohlcv "
            "(ticker, interval, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows,
        )
        conn.commit()
    finally:
        conn.close()


def last_cached_date(ticker: str, interval: str) -> pd.Timestamp | None:
    df = load(ticker, interval)
    if df is None or df.empty:
        return None
    return df.index.max()
