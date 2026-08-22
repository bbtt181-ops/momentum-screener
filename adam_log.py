"""
Reports each daily_scan.py run to the shared "ADAM Performance Log" Google
Sheet that your other automations (adam-brain.gs, discord-agent-gas, etc.)
already write to -- so Adam can see whether the momentum screener ran today
and whether an alert email went out, WITHOUT moving the actual scan
execution off this machine (it keeps running locally via Windows Task
Scheduler, exactly as set up).

One-time setup required before this does anything (see README.md
"Report to Adam" section):
  1. Create a Google Cloud service account and download its JSON key to
     `adam-service-account.json`, next to this script.
  2. Share the "ADAM Performance Log" sheet with that service account's
     email address (found inside the JSON key) as an Editor.
  3. `pip install -r requirements.txt` (adds gspread + google-auth).

Until that's done, report_to_adam() just logs "skipped" and returns --
it never blocks or breaks the actual scan or the alert email, since a
broken logging integration should never take down the thing it's logging.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

ADAM_SHEET_ID = "1xuq7Cau1ElcB0t_Y2iU4WAKFX03Dnm_MpNlWTy1lYqM"  # "ADAM Performance Log"
SERVICE_ACCOUNT_PATH = Path(__file__).resolve().parent / "adam-service-account.json"

# Matches the exact header row already used by the other Adam sub-agents,
# so momentum-screener's rows sit consistently alongside theirs:
#   date, run_type, agent, emails_scanned, proposals, approved, rejected,
#   pending, protected_skipped, errors, notes
#
# Most of those columns don't naturally apply to a stock screener (they're
# shaped around an email-approval workflow) -- rather than force a
# misleading number into a column that doesn't fit, unrelated columns are
# left at 0 and the real detail goes in `notes`, which is what a human (or
# Adam) actually reads.


def report_to_adam(scan_stats: dict, qualifying: list[dict],
                    email_sent: bool, email_message: str) -> tuple[bool, str]:
    if not SERVICE_ACCOUNT_PATH.exists():
        return False, f"skipped -- {SERVICE_ACCOUNT_PATH.name} not found (see README 'Report to Adam')."

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_PATH), scopes=scopes)
        client = gspread.authorize(creds)
        # .sheet1 grabs the first/only worksheet regardless of its exact tab
        # name, so this doesn't depend on guessing what that tab is called.
        sheet = client.open_by_key(ADAM_SHEET_ID).sheet1

        tickers_summary = ", ".join(r["ticker"] for r in qualifying) if qualifying else "none"
        notes = (f"momentum-screener daily scan ran. Scanned {scan_stats.get('total', '?')} tickers "
                 f"({scan_stats.get('scored', '?')} scored, {scan_stats.get('skipped', '?')} skipped). "
                 f"{len(qualifying)} setup(s) matched: {tickers_summary}. "
                 f"Email sent: {'yes' if email_sent else 'no'} ({email_message}).")

        row = [
            dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "daily-scan",
            "momentum-screener",
            0,                              # emails_scanned -- n/a for this agent
            len(qualifying),                # proposals -- setups found today
            0,                              # approved -- n/a, no approval workflow here
            0,                              # rejected -- n/a
            0,                              # pending -- n/a
            scan_stats.get("skipped", 0),   # protected_skipped -- tickers skipped/errored
            0 if email_sent else 1,         # errors
            notes,
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return True, "Logged to Adam."
    except Exception as e:  # noqa: BLE001 - a broken Adam log must never break the actual scan
        return False, f"Adam log failed: {e}"
