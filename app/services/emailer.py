"""Resend email delivery with safe no-op behavior when credentials are absent."""

import logging
import os
from html import escape
from typing import Iterable

import httpx

logger = logging.getLogger(__name__)


def configured():
    return bool(os.getenv("RESEND_API_KEY", "").strip() and os.getenv("RESEND_FROM_EMAIL", "").strip())


def send_email(to: str | Iterable[str], subject: str, html: str, text: str | None = None):
    recipients = [to] if isinstance(to, str) else list(dict.fromkeys(to))
    recipients = [addr.strip() for addr in recipients if addr and addr.strip()]
    if not recipients:
        return {"skipped": True, "reason": "no_recipients"}
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("RESEND_FROM_EMAIL", "").strip()
    if not api_key or not sender:
        logger.info("Email skipped because Resend is not configured: %s", subject)
        return {"skipped": True, "reason": "not_configured"}
    payload = {"from": sender, "to": recipients, "subject": subject, "html": html}
    if text:
        payload["text"] = text
    with httpx.Client(timeout=8) as client:
        response = client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def send_email_safely(*args, **kwargs):
    try:
        return send_email(*args, **kwargs)
    except Exception as error:
        logger.warning("Email delivery failed: %s", type(error).__name__)
        return {"skipped": True, "reason": "delivery_failed"}


def paragraph(value):
    return f"<p>{escape(str(value))}</p>"
