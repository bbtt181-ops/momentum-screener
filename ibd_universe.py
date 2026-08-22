"""
Pulls the current IBD50 ticker list live from your Google Sheet ("ibd50" tab,
column A in "סוחר עלPRO") at scan time, instead of a one-time paste -- since
that list updates weekly, a static paste would go stale after a week. Every
scan reads whatever is in the sheet right now, so a weekly update there is
picked up automatically on the next run, with zero manual work.

Reuses the SAME service account already set up for adam_log.py (see README
"Report to Adam") -- no separate credential needed. That service account
additionally needs to be shared as a **Viewer** on the "סוחר עלPRO" sheet
itself (Share -> paste the service account's email -> Viewer is enough,
read-only).

If the service account isn't set up yet, the sheet isn't shared with it, or
the "ibd50" tab/column layout doesn't match, this returns an empty list and
logs why -- it never blocks the rest of the scan, which still runs on the
seed universe.
"""

from __future__ import annotations

import re
from pathlib import Path

TRADING_JOURNAL_SHEET_ID = "1chNDv_NP7wUF4wAQGfuOQWGuATwQKBQkfxcPjYYrwak"  # "סוחר עלPRO"
IBD50_TAB_NAME = "ibd50"
SERVICE_ACCOUNT_PATH = Path(__file__).resolve().parent / "adam-service-account.json"

# Loose ticker shape: 1-5 letters, optionally with a .suffix or -suffix
# (e.g. BRK-B, BF.B). This is also what filters out a header cell like
# "Ticker" / "מניה" or a blank row, without needing to know in advance
# whether the sheet has a header row.
_TICKER_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,3})?$")


def load_ibd50_tickers() -> tuple[list[str], str]:
    """Returns (tickers, status_message)."""
    if not SERVICE_ACCOUNT_PATH.exists():
        return [], f"skipped -- {SERVICE_ACCOUNT_PATH.name} not found (see README 'Report to Adam')."

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_PATH), scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(TRADING_JOURNAL_SHEET_ID).worksheet(IBD50_TAB_NAME)
        column_a = sheet.col_values(1)

        tickers = sorted({
            v.strip().upper() for v in column_a
            if v and _TICKER_RE.match(v.strip().upper())
        })
        return tickers, f"loaded {len(tickers)} tickers from '{IBD50_TAB_NAME}' tab."
    except Exception as e:  # noqa: BLE001 - a broken IBD50 pull must never block the seed-list scan
        return [], f"failed: {e}"
