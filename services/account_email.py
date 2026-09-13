"""Transactional email for SYLVEX website accounts (verification, password reset).

No email-sending infrastructure exists elsewhere in this codebase (Telegram
delivery is unrelated and untouched). This is a small, stdlib-only SMTP
sender gated entirely by env vars: with none set it safely no-ops (logs to
stdout) instead of raising, so registration/login never fail because mail
delivery isn't configured yet - the token still works via the verify/reset
link itself once printed or wired to a real SMTP provider.
"""
from __future__ import annotations
import os
import smtplib
import ssl
from email.message import EmailMessage


def _website_base_url() -> str:
    return os.getenv("WEBSITE_URL", "").rstrip("/") or "https://sylvex.ai"


def _smtp_config():
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_addr": os.getenv("SMTP_FROM", "").strip() or os.getenv("SMTP_USER", "no-reply@sylvex.ai").strip(),
        "use_tls": os.getenv("SMTP_USE_TLS", "1") != "0",
    }


def _send(to_addr: str, subject: str, body: str) -> bool:
    config = _smtp_config()
    if not config:
        # Unconfigured: never block registration/reset on missing mail setup.
        print(f"ACCOUNT EMAIL (SMTP not configured, not sent): to={to_addr!r} subject={subject!r}")
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["from_addr"]
    message["To"] = to_addr
    message.set_content(body)
    try:
        if config["use_tls"]:
            with smtplib.SMTP(config["host"], config["port"], timeout=10) as server:
                server.starttls(context=ssl.create_default_context())
                if config["user"]:
                    server.login(config["user"], config["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP_SSL(config["host"], config["port"], timeout=10) as server:
                if config["user"]:
                    server.login(config["user"], config["password"])
                server.send_message(message)
        return True
    except Exception as exc:
        # Never leak SMTP/network detail to the API caller; never include the
        # token or password anywhere in this log line.
        print(f"ACCOUNT EMAIL SEND FAILED: to={to_addr!r} subject={subject!r} error={type(exc).__name__}")
        return False


def send_verification_email(to_addr: str, token: str) -> bool:
    link = f"{_website_base_url()}/api/web/auth/verify-email?token={token}"
    return _send(
        to_addr,
        "Confirm your SYLVEX email",
        f"Confirm your email address to finish setting up your SYLVEX account:\n\n{link}\n\n"
        "If you didn't create a SYLVEX account, you can ignore this email.",
    )


def send_password_reset_email(to_addr: str, token: str) -> bool:
    link = f"{_website_base_url()}/reset-password.html?token={token}"
    return _send(
        to_addr,
        "Reset your SYLVEX password",
        f"Reset your SYLVEX password using the link below. This link expires in 1 hour:\n\n{link}\n\n"
        "If you didn't request this, you can safely ignore this email - your password will not change.",
    )
