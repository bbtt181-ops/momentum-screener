"""
HTTPS mail relay for environments where outbound SMTP is blocked (GitHub
Actions runners drop connections to smtp.gmail.com on both 587 and 465).

The relay is a tiny Google Apps Script web app (gas/mail_relay.gs) running
under the owner's Google account: it receives the already-built MIME message
and sends it with the Gmail API, so the email looks exactly like the SMTP one
(HTML, inline header image, Hebrew subject).

Enabled only when both env vars are set (GitHub repo secrets):
    MAIL_RELAY_URL    -- the web app's /exec URL
    MAIL_RELAY_TOKEN  -- shared secret, same value as TOKEN in the script
"""

from __future__ import annotations

import base64
import os

import requests


def is_configured() -> bool:
    return bool(os.environ.get("MAIL_RELAY_URL") and os.environ.get("MAIL_RELAY_TOKEN"))


def send_raw(raw_message: str) -> None:
    """POST a full RFC 822 message to the relay. Raises on any failure."""
    payload = {
        "token": os.environ["MAIL_RELAY_TOKEN"],
        "raw": base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("ascii"),
    }
    resp = requests.post(os.environ["MAIL_RELAY_URL"], json=payload, timeout=60)
    resp.raise_for_status()
    if resp.text.strip() != "ok":
        raise RuntimeError(f"relay replied: {resp.text.strip()[:200]}")
