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

Each message is sent as real branded HTML (SYLVEX logo, styled button,
clear copy) with a plain-text fallback in the same request, not a bare
link - see _html_wrapper below.
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


# ---------------------------------------------------------------------------
# HTML template - one shared wrapper (logo header, card, footer) around a
# per-message body, styled inline throughout (email clients don't load
# external stylesheets). Colors match the website's light theme
# (css/tokens.css: --sx-text #0b0b0d, --sx-text-dim #55565f, --sx-border
# #e4e4e9) so the email looks like the same product, not a generic notice.
# ---------------------------------------------------------------------------

def _html_wrapper(
    preheader: str, heading: str, body_html: str,
    cta_text: str | None = None, cta_url: str | None = None, footer_note: str | None = None,
) -> str:
    logo_url = f"{_website_base_url()}/assets/logo.png"
    cta_html = ""
    if cta_text and cta_url:
        cta_html = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0 8px">
          <tr><td style="border-radius:10px;background:#0b0b0d">
            <a href="{cta_url}" target="_blank" style="display:inline-block;padding:13px 28px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">{cta_text}</a>
          </td></tr>
        </table>
        <p style="margin:0 0 4px;font-size:12.5px;color:#8b8c96;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
          Or paste this link into your browser:<br>
          <a href="{cta_url}" target="_blank" style="color:#2f6bff;word-break:break-all">{cta_url}</a>
        </p>
        """
    note_html = f'<p style="margin:18px 0 0;font-size:13px;color:#8b8c96">{footer_note}</p>' if footer_note else ""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SYLVEX</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f6;padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border-radius:16px;border:1px solid #e4e4e9;overflow:hidden">
        <tr><td style="padding:32px 32px 0;text-align:center">
          <img src="{logo_url}" width="40" height="40" alt="SYLVEX" style="display:block;margin:0 auto 10px;border-radius:9px">
          <div style="font-size:15px;font-weight:800;letter-spacing:.02em;color:#0b0b0d">SYLVEX</div>
        </td></tr>
        <tr><td style="padding:28px 32px 32px">
          <h1 style="margin:0 0 12px;font-size:20px;font-weight:800;color:#0b0b0d;letter-spacing:-.01em">{heading}</h1>
          <div style="font-size:14.5px;line-height:1.65;color:#55565f">{body_html}</div>
          {cta_html}
          {note_html}
        </td></tr>
        <tr><td style="padding:20px 32px;border-top:1px solid #e4e4e9;text-align:center">
          <p style="margin:0;font-size:12px;color:#8b8c96">SYLVEX &middot; <a href="{_website_base_url()}" style="color:#8b8c96" target="_blank">{_website_base_url().replace('https://', '').replace('http://', '')}</a></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _send(to_addr: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    config = _resend_config()
    if not config:
        # Unconfigured: never block registration/reset/merge on missing mail setup.
        print(f"ACCOUNT EMAIL (Resend not configured, not sent): to={to_addr!r} subject={subject!r}")
        return False
    payload = {
        "from": config["from_addr"],
        "to": [to_addr],
        "subject": subject,
        "text": text_body,
    }
    if html_body:
        payload["html"] = html_body
    try:
        response = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json=payload,
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
    html_body = _html_wrapper(
        preheader="Confirm your email to finish setting up your SYLVEX account.",
        heading="Confirm your email",
        body_html=(
            "<p style=\"margin:0 0 4px\">Thanks for creating a SYLVEX account. Confirm your email address "
            "to finish setting things up.</p>"
        ),
        cta_text="Confirm Email",
        cta_url=link,
        footer_note="If you didn't create a SYLVEX account, you can ignore this email.",
    )
    return _send(
        to_addr,
        "Confirm your SYLVEX email",
        f"Confirm your email address to finish setting up your SYLVEX account:\n\n{link}\n\n"
        "If you didn't create a SYLVEX account, you can ignore this email.",
        html_body,
    )


def send_merge_code_email(to_addr: str, code: str) -> bool:
    html_body = _html_wrapper(
        preheader=f"Your SYLVEX connection code is {code}.",
        heading="Your connection code",
        body_html=(
            "<p style=\"margin:0 0 18px\">Enter this code in Telegram to connect this email's SYLVEX account:</p>"
            f"<div style=\"text-align:center;margin:0 0 6px\"><span style=\"display:inline-block;padding:14px 26px;"
            f"font-size:28px;font-weight:800;letter-spacing:.12em;color:#0b0b0d;background:#f4f4f6;"
            f"border-radius:10px;border:1px solid #e4e4e9\">{code}</span></div>"
        ),
        footer_note="This code expires in 10 minutes and can only be used once. If you didn't request this, "
                    "you can safely ignore this email.",
    )
    return _send(
        to_addr,
        "Your SYLVEX account connection code",
        f"Use this code in Telegram to connect this email's SYLVEX account:\n\n{code}\n\n"
        "This code expires in 10 minutes and can only be used once. "
        "If you didn't request this, you can safely ignore this email.",
        html_body,
    )


def send_password_reset_email(to_addr: str, token: str) -> bool:
    link = f"{_website_base_url()}/reset-password.html?token={token}"
    html_body = _html_wrapper(
        preheader="Reset your SYLVEX password. This link expires in 1 hour.",
        heading="Reset your password",
        body_html=(
            "<p style=\"margin:0 0 4px\">We received a request to reset your SYLVEX account password. "
            "This link expires in 1 hour.</p>"
        ),
        cta_text="Reset Password",
        cta_url=link,
        footer_note="If you didn't request this, you can safely ignore this email - your password will not change.",
    )
    return _send(
        to_addr,
        "Reset your SYLVEX password",
        f"Reset your SYLVEX password using the link below. This link expires in 1 hour:\n\n{link}\n\n"
        "If you didn't request this, you can safely ignore this email - your password will not change.",
        html_body,
    )
