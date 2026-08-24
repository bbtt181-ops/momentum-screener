"""
One-off manual test for the email-alert pipeline -- sends a single email with
FAKE example results, so you can confirm SMTP login + the HTML template
(image, quote, results table, and the READY/Watchlist section) actually work
without waiting for a real A+/A or READY setup to show up in a live scan.

Run:
    python test_email.py

Reads the same .env file as daily_scan.py (GMAIL_SENDER_ADDRESS,
GMAIL_APP_PASSWORD, ALERT_RECIPIENT_ADDRESS). Safe to delete once you've
confirmed the email arrives and looks right.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(SCRIPT_DIR / ".env")

import notify  # noqa: E402

FAKE_RESULTS = [
    {
        "ticker": "TEST",
        "grade": "A+",
        "setup_score": 96,
        "status": "BREAKOUT",
        "ideal_entry": 100.25,
        "stop": 97.80,
        "stop_pct": 2.44,
    },
]

# READY setups (approaching Resistance, not broken out yet -- can't have an A+/A grade yet, see
# scoring/setup_score.py) go through the separate `watchlist_results` argument, rendered as their
# own section below the main A+/A table -- not through FAKE_RESULTS above.
FAKE_WATCHLIST = [
    {
        "ticker": "DEMO",
        "grade": "B",
        "setup_score": 74.0,
        "status": "READY",
        "price": 44.10,
        "resistance": 45.30,
        "ideal_entry": 45.39,
        "distance_to_entry_pct": -0.0284,
        "stop": 43.10,
        "stop_pct": 4.86,
    },
]


def main() -> int:
    sender = os.environ.get("GMAIL_SENDER_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_RECIPIENT_ADDRESS")

    if not (sender and password and recipient):
        print("ERROR: missing GMAIL_SENDER_ADDRESS / GMAIL_APP_PASSWORD / "
              "ALERT_RECIPIENT_ADDRESS in .env -- see README.")
        return 1

    all_tickers = [r["ticker"] for r in FAKE_RESULTS] + [r["ticker"] for r in FAKE_WATCHLIST]
    print(f"Sending a TEST email (fake data: {', '.join(all_tickers)}) "
          f"from {sender} to {recipient} ...")
    sent, msg = notify.send_grade_alert_email(sender, password, recipient, FAKE_RESULTS,
                                                watchlist_results=FAKE_WATCHLIST)
    print(("SUCCESS: " if sent else "FAILED: ") + msg)
    return 0 if sent else 1


if __name__ == "__main__":
    raise SystemExit(main())
