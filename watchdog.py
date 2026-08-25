"""
Watchdog for the daily scan -- a small, separate Windows Scheduled Task
("MomentumScreenerWatchdog") that runs a short while after the main
"MomentumScreenerDailyScan" task's start time, and checks whether that scan
actually ran (and successfully emailed) today. If it didn't, this sends its
OWN short alert email -- because if the problem is that the main task never
fired at all (PC off, task disabled, misconfigured) or crashed before
reaching the email step, there is otherwise no signal anywhere that anything
went wrong: silence just looks like "nothing to report" instead of
"something broke."

This checks daily_scan.log for evidence of today's run:
  - No "Daily scan starting" line for today at all     -> the main task
    never fired (or crashed before its very first log line).
  - "Daily scan starting" present, but no "Email sent:" -> the scan ran but
    never got as far as a successful send (crashed mid-scan, or the SMTP
    send itself failed -- see the "Email FAILED:" line if there is one).
  - Both present                                        -> everything's
    fine, exit quietly (no email -- the daily scan's own email already
    covers this case, no need to say it twice).

Deliberately kept simple and independent of notify.py/imagegen.py (plain
smtplib + MIMEText, no HTML, no header image, no external fetch) -- a
failure-detector that depends on the same moving parts it's supposed to
catch failures in isn't a reliable failure-detector. See the header-image
incident in the project's build-status notes for why "keep the critical
path simple" matters here.

Credentials are read from the same local .env file as daily_scan.py:
    GMAIL_SENDER_ADDRESS=youraccount@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
    ALERT_RECIPIENT_ADDRESS=where-alerts-should-go@example.com

Schedule this to run ~20-25 minutes after MomentumScreenerDailyScan's start
time (a full scan of ~280 tickers has historically taken 12-17 minutes) --
see README.md "Watchdog alert" for the exact schtasks command, or just run
setup_watchdog_task.bat once. If you ever change the main scan's scheduled
time, update this task's time to match (main time + ~25 minutes).

Run manually to test:
    python watchdog.py
"""

from __future__ import annotations

import datetime as dt
import os
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(SCRIPT_DIR / ".env")

LOG_PATH = SCRIPT_DIR / "daily_scan.log"
WATCHDOG_LOG_PATH = SCRIPT_DIR / "watchdog.log"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def log(message: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(WATCHDOG_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _todays_lines(today: str) -> list[str]:
    if not LOG_PATH.exists():
        return []
    prefix = f"[{today} "
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return [line for line in f if line.startswith(prefix)]


def _send_alert(sender: str, password: str, recipient: str, subject: str, body: str) -> tuple[bool, str]:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        return True, f"Alert sent to {recipient}."
    except Exception as e:  # noqa: BLE001 - the watchdog itself must never crash uncaught
        return False, f"Alert send failed: {e}"


def main() -> int:
    today = dt.date.today().strftime("%Y-%m-%d")
    lines = _todays_lines(today)
    started = any("Daily scan starting" in line for line in lines)
    email_sent = any("Email sent:" in line for line in lines)
    email_failed_line = next((line.strip() for line in lines if "Email FAILED:" in line), None)

    if started and email_sent:
        log("OK -- today's scan ran and the summary email was sent. Nothing to do.")
        return 0

    sender = os.environ.get("GMAIL_SENDER_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_RECIPIENT_ADDRESS")

    if not (sender and password and recipient):
        log("ERROR: missing GMAIL_SENDER_ADDRESS / GMAIL_APP_PASSWORD / ALERT_RECIPIENT_ADDRESS "
            "in .env -- cannot send a watchdog alert either. See README.")
        return 1

    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not started:
        subject = "⚠️ Momentum Screener: הסריקה האוטומטית לא רצה הלילה"
        body = (
            f"נכון לבדיקה הזו ({now_str}), אין שום רישום של תחילת סריקה היום ב-daily_scan.log.\n\n"
            "סיבות אפשריות: המחשב היה כבוי/במצב שינה בשעה המתוכננת, המשימה המתוזמנת "
            '"MomentumScreenerDailyScan" מושבתת או נמחקה, או שגיאה מנעה אפילו את השורה הראשונה '
            "בלוג.\n\n"
            "בדוק ב-Task Scheduler (חפש \"MomentumScreenerDailyScan\") את תוצאת הריצה האחרונה, "
            "או הרץ ידנית כדי לבדוק:\n"
            'schtasks /run /tn "MomentumScreenerDailyScan"'
        )
    else:
        subject = "⚠️ Momentum Screener: הסריקה רצה אך המייל לא נשלח"
        reason = email_failed_line or "לא נמצאה שורת \"Email sent\" בלוג להיום (יתכן קריסה באמצע הריצה)."
        body = (
            f"הסריקה של היום ({now_str}) התחילה, אבל לא נמצאה שורת \"Email sent\" ב-daily_scan.log.\n\n"
            f"פרט מהלוג: {reason}\n\n"
            "בדוק את daily_scan.log במלואו כדי להבין איפה זה נעצר."
        )

    ok, msg = _send_alert(sender, password, recipient, subject, body)
    log(("Watchdog alert sent: " if ok else "Watchdog alert FAILED: ") + msg)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
