"""
Email alerts -- builds and sends the scan-result email.

Two callers use this module, with two different sending policies:
  - app.py (the Streamlit dashboard): pulls credentials from st.secrets,
    and only sends when a manual SCAN click finds a qualifying (A+/A)
    result -- clicking SCAN repeatedly while testing in the dashboard
    should not spam the inbox.
  - daily_scan.py (standalone script, run by a local Windows Scheduled
    Task): pulls credentials from a local .env file, and sends a summary
    email after EVERY scheduled run, whether or not a qualifying setup was
    found -- so a "no setups today" email still confirms the scan actually
    ran (see send_grade_alert_email()'s `scan_stats` argument).

Neither caller ever hard-codes a password here -- send_grade_alert_email()
takes sender/password/recipient as plain arguments so this module has no
opinion about where they came from, and no credential ever gets logged or
embedded in a committed file.

The email includes one background image (embedded inline via Content-ID,
not hot-linked -- so it always renders regardless of whether the GitHub
repo is public/private and without depending on any external image host
staying online). The image is freshly generated for every single send by
imagegen.py (randomized gradient + growth motif) -- an effectively
infinite pool rather than a fixed set of files -- plus a random Hebrew
motivational line. Neither depends on the internet, so a scheduled run
never depends on a third-party image service being up.
"""

from __future__ import annotations

import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText

import imagegen

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

MOTIVATIONAL_QUOTES = [
    "המשמעת שלך היום היא התוצאה שלך מחר.",
    "לא כל יום צריך להיות פריצה -- גם יום של סבלנות הוא יום מוצלח.",
    "הסטופ הוא לא כישלון, הוא המחיר של להישאר במשחק.",
    "מגמה טובה נבנית לאט -- תן לה מקום לנשום.",
    "הקונסיסטנטיות מנצחת את ההתלהבות, כל פעם מחדש.",
    "הכי חשוב זה לא לצדוק -- הכי חשוב זה לנהל סיכון נכון.",
    "כל Setup טוב מתחיל בסבלנות, לא בלחץ להיכנס.",
    "השוק תמיד יהיה כאן מחר -- אין צורך לרדוף אחרי כל תנועה.",
    "תן לתהליך לעבוד -- התוצאות מגיעות למי שממשיך להופיע.",
    "המטרה היא לא לתפוס כל פריצה, אלא לתפוס את הפריצות הנכונות.",
]


def _format_results_rows_html(results: list[dict]) -> str:
    rows = []
    for r in results:
        rows.append(f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid #2a2a3d;font-weight:700;color:#f5f5f7;">{r['ticker']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #2a2a3d;color:#f5f5f7;">{r['grade']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #2a2a3d;color:#f5f5f7;">{r['setup_score']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #2a2a3d;color:#f5f5f7;">{r['status']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #2a2a3d;color:#f5f5f7;">${r['ideal_entry']:.2f}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #2a2a3d;color:#f5f5f7;">${r['stop']:.2f}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #2a2a3d;color:#f5f5f7;">{r['stop_pct']:.2f}%</td>
        </tr>""")
    return "".join(rows)


def _scan_stats_line(scan_stats: dict | None) -> str:
    if not scan_stats:
        return ""
    return (f"נסרקו {scan_stats.get('total', '?')} מניות "
            f"({scan_stats.get('scored', '?')} עם ציון, {scan_stats.get('skipped', '?')} דולגו).")


def build_html_email(qualifying_results: list[dict], quote: str, image_cid: str | None,
                      scan_stats: dict | None = None) -> str:
    image_html = (
        f'<img src="cid:{image_cid}" width="100%" '
        f'style="display:block;border-radius:14px;max-height:260px;object-fit:cover;" />'
        if image_cid else ""
    )
    stats_line = _scan_stats_line(scan_stats)

    if qualifying_results:
        rows_html = _format_results_rows_html(qualifying_results)
        tickers_summary = ", ".join(r["ticker"] for r in qualifying_results)
        headline = f"🚀 {len(qualifying_results)} Setup(s) בדירוג גבוה נמצאו היום"
        body_block = f"""
                <p style="margin:0 0 18px 0;color:#a8a8bd;font-size:14px;">{tickers_summary}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 26px 26px 26px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                       style="border-collapse:collapse;background-color:#1f1f30;border-radius:10px;overflow:hidden;">
                  <tr style="background-color:#2a2a40;">
                    <th style="padding:10px 14px;text-align:right;color:#c9c9e0;font-size:13px;">Ticker</th>
                    <th style="padding:10px 14px;text-align:right;color:#c9c9e0;font-size:13px;">Grade</th>
                    <th style="padding:10px 14px;text-align:right;color:#c9c9e0;font-size:13px;">Score</th>
                    <th style="padding:10px 14px;text-align:right;color:#c9c9e0;font-size:13px;">Status</th>
                    <th style="padding:10px 14px;text-align:right;color:#c9c9e0;font-size:13px;">Ideal Entry</th>
                    <th style="padding:10px 14px;text-align:right;color:#c9c9e0;font-size:13px;">Stop</th>
                    <th style="padding:10px 14px;text-align:right;color:#c9c9e0;font-size:13px;">Risk %</th>
                  </tr>
                  {rows_html}
                </table>"""
    else:
        headline = "🔍 לא נמצאו היום סטאפים בדירוג A+/A"
        body_block = f"""
                <p style="margin:0 0 4px 0;color:#a8a8bd;font-size:14px;">{stats_line or "הסריקה היומית הסתיימה."}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 26px 26px 26px;">
                <p style="margin:0;color:#c9c9e0;font-size:14px;">זה בסדר גמור -- לא כל יום צריך להיות יום פריצה. הסריקה תרוץ שוב מחר באותה שעה.</p>"""

    return f"""
<html dir="rtl" lang="he">
  <body style="margin:0;padding:0;background-color:#0f0f17;font-family:Arial, Helvetica, sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f17;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0"
                 style="background-color:#181826;border-radius:18px;overflow:hidden;">
            <tr><td style="padding:0;">{image_html}</td></tr>
            <tr>
              <td style="padding:22px 26px 6px 26px;">
                <p style="margin:0 0 18px 0;font-size:17px;line-height:1.6;color:#e8e8f0;font-style:italic;text-align:center;">
                  "{quote}"
                </p>
                <h2 style="margin:0 0 4px 0;color:#ffffff;font-size:20px;">
                  {headline}
                </h2>{body_block}
              </td>
            </tr>
            <tr>
              <td style="padding:0 26px 24px 26px;">
                <p style="margin:0;color:#6b6b80;font-size:12px;text-align:center;">
                  Momentum First-Leg Breakout Screener -- זה כלי לסינון, לא ייעוץ השקעות. תמיד תבדוק בעצמך לפני כניסה.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def build_plain_text_email(qualifying_results: list[dict], quote: str, scan_stats: dict | None = None) -> str:
    if not qualifying_results:
        stats_line = _scan_stats_line(scan_stats)
        return (f'"{quote}"\n\nלא נמצאו היום סטאפים בדירוג A+/A. {stats_line}\n'
                f'הסריקה תרוץ שוב מחר.')
    lines = [
        f"{r['ticker']} -- Grade {r['grade']} -- Score {r['setup_score']} -- Status {r['status']} "
        f"-- Ideal Entry ${r['ideal_entry']:.2f} -- Stop ${r['stop']:.2f} ({r['stop_pct']:.2f}%)"
        for r in qualifying_results
    ]
    return f'"{quote}"\n\n{len(qualifying_results)} setup(s) matched your alert grades today:\n\n' + "\n".join(lines)


def send_grade_alert_email(sender: str, password: str, recipient: str,
                            qualifying_results: list[dict],
                            scan_stats: dict | None = None) -> tuple[bool, str]:
    """
    Sends one HTML email (with a plain-text fallback part) about a scan run.

    If `qualifying_results` is non-empty, the email lists every matching
    result. If it's empty, the email still sends (as a "ran successfully,
    nothing matched today" summary) PROVIDED `scan_stats` is passed --
    that's the signal this call is a daily-summary send (daily_scan.py)
    rather than an interactive dashboard alert (app.py), which should stay
    silent on an empty result to avoid spamming the inbox on every manual
    SCAN click while testing.

    `scan_stats` is an optional dict like {"total": N, "scored": N,
    "skipped": N} shown in the "nothing today" email so it's clear the scan
    actually ran the full universe.

    Returns (success, message) for display in the sidebar or scheduled-run
    logs.
    """
    if not qualifying_results and scan_stats is None:
        return False, "Nothing to send."

    quote = random.choice(MOTIVATIONAL_QUOTES)
    try:
        image_bytes = imagegen.generate_image_bytes()
    except Exception:  # noqa: BLE001 - a broken image generator should never block the alert email
        image_bytes = None
    image_cid = "header_image" if image_bytes else None

    msg = MIMEMultipart("related")
    if qualifying_results:
        msg["Subject"] = f"🚀 Momentum Screener: {len(qualifying_results)} setup(s) -- " + \
                          ", ".join(r["ticker"] for r in qualifying_results)
    else:
        msg["Subject"] = "🔍 Momentum Screener: Daily scan complete -- no A+/A setups today"
    msg["From"] = sender
    msg["To"] = recipient

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(build_plain_text_email(qualifying_results, quote, scan_stats), "plain", "utf-8"))
    alt.attach(MIMEText(build_html_email(qualifying_results, quote, image_cid, scan_stats), "html", "utf-8"))
    msg.attach(alt)

    if image_bytes:
        img = MIMEImage(image_bytes, _subtype="jpeg")
        img.add_header("Content-ID", f"<{image_cid}>")
        img.add_header("Content-Disposition", "inline", filename="header.jpg")
        msg.attach(img)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        return True, f"Email sent to {recipient}."
    except Exception as e:  # noqa: BLE001
        return False, f"Email failed: {e}"
