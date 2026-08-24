"""
Persists the results of the most recent scan to a local file, so reopening
the dashboard -- a new browser tab, a page refresh, or the Streamlit Cloud
app waking back up after going idle -- shows the last known scan instead of
an empty "click SCAN" screen.

Streamlit's `st.session_state` only lives for one running app session; it
does not survive a page reload in a NEW session, a new device, or the app
process restarting. This module is the fix: a plain pickle file next to the
script, written after every successful scan and read back on startup if the
current session doesn't already have results in memory.

Both app.py (manual SCAN button) and daily_scan.py (the nightly automated
run) write to the SAME cache file, so on a local run the dashboard also
picks up whatever the last automated run found overnight -- not just
manual scans clicked in the browser.

This is intentionally a local file, not a database: it survives a page
refresh or a new tab on the same machine/container, but not a full
redeploy or container rebuild (Streamlit Cloud wipes its ephemeral disk on
redeploy, and a from-scratch clone obviously starts with none). That's an
acceptable trade-off here -- a cached scan is always shown with its
original timestamp and source, never presented as a live/current one, so
it's never misleading, only occasionally missing.
"""

from __future__ import annotations

import datetime as dt
import pickle
from pathlib import Path
from typing import Any

CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "last_scan.pkl"


def save_last_scan(results: list[dict], scan_time: dt.datetime, source: str) -> None:
    """
    source: "manual" (dashboard SCAN button) or "daily" (scheduled
    daily_scan.py run). Never raises -- a caching failure (e.g. read-only
    filesystem, disk full) must never break or block a real scan.
    """
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"results": results, "scan_time": scan_time, "source": source}
        tmp_path = CACHE_PATH.with_suffix(".pkl.tmp")
        with open(tmp_path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp_path.replace(CACHE_PATH)  # atomic on both POSIX and Windows -- no half-written cache
    except Exception:  # noqa: BLE001 - caching is a convenience, never a hard dependency
        pass


def load_last_scan() -> dict[str, Any] | None:
    """
    Returns {"results": [...], "scan_time": datetime, "source": "manual"|"daily"}
    or None if there's no cache yet, or it can't be read (corrupt file, an
    old format from a previous version of this module, etc.) -- callers
    should treat None exactly like "no prior scan", not as an error.
    """
    try:
        if not CACHE_PATH.exists():
            return None
        with open(CACHE_PATH, "rb") as f:
            payload = pickle.load(f)
        if not isinstance(payload, dict) or "results" not in payload:
            return None
        return payload
    except Exception:  # noqa: BLE001 - a corrupt/old-format cache should never crash the app
        return None
