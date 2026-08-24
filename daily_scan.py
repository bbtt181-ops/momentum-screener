"""
Standalone daily scan -- run once per day by a local Windows Scheduled Task
(no Streamlit dependency, so it works headless from schtasks).

What it does:
  1. Builds the default ScreenerConfig (same thresholds as the dashboard
     unless you edit config.py or this file's OVERRIDES section below).
  2. Loads the default seed ticker universe (same list the dashboard uses
     by default -- data/default_universe.csv), and ADDS the current IBD50
     list pulled live from your Google Sheet's "ibd50" tab via
     ibd_universe.load_ibd50_tickers() -- read fresh every run (not a
     one-time paste), so a weekly update to that sheet is picked up
     automatically. No-ops quietly (falls back to just the seed list) until
     the one-time service-account setup is done (see README "Report to
     Adam" -- same service account, also needs Viewer access on the
     "סוחר עלPRO" sheet).
  3. Scans every ticker with scanner.scan_universe() (identical pipeline
     the dashboard's SCAN button calls).
  4. Filters for results whose grade is in cfg.email_alert_grades
     (default: A+ and A).
  5. Sends one summary email via notify.send_grade_alert_email() -- EVERY
     run, whether or not anything qualified today, so a "0 setups" email
     still confirms the scan actually ran (unlike the dashboard's SCAN
     button, which only emails on a qualifying result).
  6. Reports the run to Adam's shared "ADAM Performance Log" Google Sheet
     via adam_log.report_to_adam() -- whether the scan ran and whether the
     email was sent, alongside your other GAS-based agents' log entries.
     No-ops quietly until the one-time service-account setup is done (see
     README "Report to Adam").

Credentials are read from a local .env file next to this script (never
committed -- see .gitignore) using the same three keys as the Streamlit
secrets.toml used by the dashboard:

    GMAIL_SENDER_ADDRESS=youraccount@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
    ALERT_RECIPIENT_ADDRESS=where-alerts-should-go@example.com

See README.md "Daily automatic scan (Windows Task Scheduler)" for how to
create the .env file and register this script with schtasks.

Run manually to test:
    python daily_scan.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Make sure local imports (config, scanner, notify, data/...) resolve
# regardless of the working directory Task Scheduler launches this from.
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(SCRIPT_DIR / ".env")

from config import ScreenerConfig  # noqa: E402
from data import universe as universe_mod  # noqa: E402
from scanner import scan_universe  # noqa: E402
import notify  # noqa: E402
import adam_log  # noqa: E402
import ibd_universe  # noqa: E402
import scan_cache  # noqa: E402

LOG_PATH = SCRIPT_DIR / "daily_scan.log"


def log(message: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    log("Daily scan starting.")

    cfg = ScreenerConfig()
    # OVERRIDES -- uncomment / edit if you want the scheduled scan to differ
    # from the dashboard's defaults, e.g.:
    # cfg.email_alert_grades = ["A+", "A", "B"]

    sender = os.environ.get("GMAIL_SENDER_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_RECIPIENT_ADDRESS")

    if not (sender and password and recipient):
        log("ERROR: missing GMAIL_SENDER_ADDRESS / GMAIL_APP_PASSWORD / "
            "ALERT_RECIPIENT_ADDRESS in .env -- see README. Aborting before scanning.")
        return 1

    seed_tickers = universe_mod.load_default_universe()
    ibd_tickers, ibd_msg = ibd_universe.load_ibd50_tickers()
    log(f"IBD50 pull: {ibd_msg}")

    tickers = sorted(set(seed_tickers) | set(ibd_tickers))
    log(f"Loaded {len(seed_tickers)} seed tickers + {len(ibd_tickers)} IBD50 tickers "
        f"-> {len(tickers)} unique tickers to scan.")

    def _progress(i, total, ticker):
        if i % 25 == 0 or i == total - 1:
            log(f"Scanning {i + 1}/{total} ({ticker})...")

    results = scan_universe(tickers, cfg, progress_callback=_progress)
    ok_results = [r for r in results if r.get("ok")]
    errored = [r for r in results if not r.get("ok")]
    log(f"Scan complete: {len(ok_results)} scored, {len(errored)} skipped/errored.")

    scan_time = dt.datetime.now()
    scan_cache.save_last_scan(results, scan_time, source="daily")

    qualifying = [r for r in ok_results if r.get("grade") in cfg.email_alert_grades]
    if qualifying:
        summary = ", ".join(f"{r['ticker']}({r['grade']})" for r in qualifying)
        log(f"{len(qualifying)} result(s) match alert grades {cfg.email_alert_grades}: {summary}")
    else:
        log(f"0 results match alert grades {cfg.email_alert_grades}.")

    # READY -- approaching Resistance but hasn't broken out yet, so it can't have earned an A+/A
    # grade yet (Setup Score needs an actual breakout candle to cross the grade threshold -- see
    # scoring/setup_score.py). Included as a separate "Watchlist" section in the same daily email
    # so a heads-up before the breakout doesn't require opening the dashboard every day.
    ready_watchlist = [r for r in ok_results if r.get("status") == "READY"]
    ready_watchlist.sort(key=lambda r: r.get("distance_to_entry_pct") if r.get("distance_to_entry_pct") is not None else -1,
                          reverse=True)
    if ready_watchlist:
        summary = ", ".join(r["ticker"] for r in ready_watchlist)
        log(f"{len(ready_watchlist)} result(s) in READY status (Watchlist): {summary}")

    scan_stats = {"total": len(tickers), "scored": len(ok_results), "skipped": len(errored)}
    sent, msg = notify.send_grade_alert_email(sender, password, recipient, qualifying, scan_stats=scan_stats,
                                                watchlist_results=ready_watchlist)
    log(("Email sent: " if sent else "Email FAILED: ") + msg)

    adam_ok, adam_msg = adam_log.report_to_adam(scan_stats, qualifying, sent, msg)
    log(("Adam log: " if adam_ok else "Adam log skipped/failed: ") + adam_msg)

    return 0 if sent else 2


if __name__ == "__main__":
    raise SystemExit(main())
