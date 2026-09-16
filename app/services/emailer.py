"""Resend email delivery with safe no-op behavior when credentials are absent."""

import json
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


def _safe_resend_message(error: httpx.HTTPStatusError):
    try:
        data = error.response.json()
    except json.JSONDecodeError:
        data = {"message": error.response.text[:300]}
    # Resend error payloads normally contain name/message/statusCode. Keep only
    # those fields so logs do not accidentally include headers or request data.
    message = data.get("message") or data.get("error") or "Resend rejected the request"
    name = data.get("name") or data.get("type") or "resend_error"
    return f"status={error.response.status_code} name={name} message={message}"


def send_email_safely(*args, **kwargs):
    try:
        return send_email(*args, **kwargs)
    except httpx.HTTPStatusError as error:
        logger.warning("Email delivery failed: %s", _safe_resend_message(error))
        return {"skipped": True, "reason": "delivery_failed", "status_code": error.response.status_code}
    except Exception as error:
        logger.warning("Email delivery failed before provider response: %s", type(error).__name__)
        return {"skipped": True, "reason": "delivery_failed"}


def paragraph(value):
    return f"<p>{escape(str(value))}</p>"
