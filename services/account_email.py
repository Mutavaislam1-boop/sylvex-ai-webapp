"""Transactional email for SYLVEX website accounts (verification, password
reset, Telegram <-> website merge codes) via the Resend HTTPS Email API.

Railway's outbound SMTP is blocked/unreliable depending on plan (this is
what SMTP's own connection attempts were timing out on before), so this
sends over plain HTTPS instead: POST https://api.resend.com/emails,
Authorization: Bearer RESEND_API_KEY. No new dependency - `requests` is
already used elsewhere in this codebase (main.py).

Gated entirely by env vars: with RESEND_API_KEY unset it safely no-ops
(logs to stdout) instead of raising, so registration/login/merge never
fail just because mail delivery isn't configured yet - the token still
works via the verify/reset link itself once printed or delivered. A send
failure (HTTP error or network exception) is caught and logged the same
way - never the API key, never the token/code - and never raised, for the
same reason.
"""
from __future__ import annotations
import os
import requests

RESEND_API_URL = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10


def _website_base_url() -> str:
    return os.getenv("WEBSITE_URL", "").rstrip("/") or "https://sylvex.ai"


def _resend_config():
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return None
    return {
        "api_key": api_key,
        "from_addr": os.getenv("EMAIL_FROM", "").strip() or "SYLVEX <noreply@sylvex.ai>",
    }


def _send(to_addr: str, subject: str, body: str) -> bool:
    config = _resend_config()
    if not config:
        # Unconfigured: never block registration/reset/merge on missing mail setup.
        print(f"ACCOUNT EMAIL (Resend not configured, not sent): to={to_addr!r} subject={subject!r}")
        return False
    try:
        response = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "from": config["from_addr"],
                "to": [to_addr],
                "subject": subject,
                "text": body,
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        # Never leak the API key, or network/proxy detail beyond the
        # exception type, in this log line.
        print(f"ACCOUNT EMAIL SEND FAILED: to={to_addr!r} subject={subject!r} error={type(exc).__name__}")
        return False
    if not response.ok:
        # Resend's error body is JSON like {"message": "...", "name": "..."} -
        # safe to log (never contains the Authorization header/API key), and
        # far more actionable than the exception path above.
        detail = response.text[:300] if response.text else ""
        print(f"ACCOUNT EMAIL SEND FAILED: to={to_addr!r} subject={subject!r} status={response.status_code} detail={detail!r}")
        return False
    return True


def send_verification_email(to_addr: str, token: str) -> bool:
    # Points at the website's own verify-email.html (not the backend API
    # directly) - sylvex.ai is a separate static site from this API, so a
    # direct /api/web/... link 404s there. That page calls this API
    # cross-origin and renders the result.
    link = f"{_website_base_url()}/verify-email.html?token={token}"
    return _send(
        to_addr,
        "Confirm your SYLVEX email",
        f"Confirm your email address to finish setting up your SYLVEX account:\n\n{link}\n\n"
        "If you didn't create a SYLVEX account, you can ignore this email.",
    )


def send_merge_code_email(to_addr: str, code: str) -> bool:
    return _send(
        to_addr,
        "Your SYLVEX account connection code",
        f"Use this code in Telegram to connect this email's SYLVEX account:\n\n{code}\n\n"
        "This code expires in 10 minutes and can only be used once. "
        "If you didn't request this, you can safely ignore this email.",
    )


def send_password_reset_email(to_addr: str, token: str) -> bool:
    link = f"{_website_base_url()}/reset-password.html?token={token}"
    return _send(
        to_addr,
        "Reset your SYLVEX password",
        f"Reset your SYLVEX password using the link below. This link expires in 1 hour:\n\n{link}\n\n"
        "If you didn't request this, you can safely ignore this email - your password will not change.",
    )
