"""Optional SMTP mailer (STARTTLS enforced). Returns False when not configured."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

import constants as C

log = logging.getLogger("infragov.mail")


def send(to: str, subject: str, body: str) -> bool:
    if not C.SMTP_ENABLED:
        return False
    msg = EmailMessage()
    msg["From"] = C.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    ctx = ssl.create_default_context()
    try:
        if C.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(C.SMTP_HOST, C.SMTP_PORT, context=ctx, timeout=15) as s:
                if C.SMTP_USERNAME:
                    s.login(C.SMTP_USERNAME, C.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(C.SMTP_HOST, C.SMTP_PORT, timeout=15) as s:
                s.starttls(context=ctx)
                if C.SMTP_USERNAME:
                    s.login(C.SMTP_USERNAME, C.SMTP_PASSWORD)
                s.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("SMTP send failed: %s", type(exc).__name__)
        return False
