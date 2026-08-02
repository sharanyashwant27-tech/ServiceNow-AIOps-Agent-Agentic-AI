from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class NotificationChannels:
    """SMTP + Slack + Microsoft Teams notification fan-out."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def send_all(self, subject: str, message: str, recipients: list[str]) -> dict[str, Any]:
        results = {
            "smtp": self.send_smtp(subject, message, recipients),
            "slack": await self.send_slack(subject, message),
            "teams": await self.send_teams(subject, message),
            "sms": await self.send_sms(subject, message, recipients),
        }
        return results

    def send_smtp(self, subject: str, message: str, recipients: list[str]) -> dict[str, Any]:
        if not self.settings.smtp_host or not recipients:
            return {"sent": False, "reason": "smtp_not_configured_or_no_recipients", "mocked": True}
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self.settings.smtp_from
            msg["To"] = ", ".join(recipients)
            msg.set_content(message)
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
                if self.settings.smtp_use_tls:
                    smtp.starttls()
                if self.settings.smtp_username:
                    smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(msg)
            return {"sent": True, "recipients": recipients, "channel": "smtp"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("SMTP send failed: %s", exc)
            return {"sent": False, "error": str(exc), "channel": "smtp"}

    async def send_slack(self, subject: str, message: str) -> dict[str, Any]:
        url = self.settings.slack_webhook_url
        if not url:
            return {"sent": False, "reason": "slack_not_configured", "mocked": True}
        payload = {"text": f"*{subject}*\n{message}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
            return {"sent": resp.is_success, "status_code": resp.status_code, "channel": "slack"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Slack send failed: %s", exc)
            return {"sent": False, "error": str(exc), "channel": "slack"}

    async def send_teams(self, subject: str, message: str) -> dict[str, Any]:
        url = self.settings.teams_webhook_url
        if not url:
            return {"sent": False, "reason": "teams_not_configured", "mocked": True}
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": subject,
            "themeColor": "0076D7",
            "title": subject,
            "text": message,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
            return {"sent": resp.is_success, "status_code": resp.status_code, "channel": "teams"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Teams send failed: %s", exc)
            return {"sent": False, "error": str(exc), "channel": "teams"}

    async def send_sms(self, subject: str, message: str, recipients: list[str]) -> dict[str, Any]:
        url = self.settings.sms_webhook_url
        if not url:
            return {"sent": False, "reason": "sms_not_configured", "mocked": True, "channel": "sms"}
        payload = {
            "from": self.settings.sms_from or "AIOPS",
            "to": recipients,
            "body": f"{subject}: {message}"[:480],
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
            return {"sent": resp.is_success, "status_code": resp.status_code, "channel": "sms"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("SMS send failed: %s", exc)
            return {"sent": False, "error": str(exc), "channel": "sms"}


notification_channels = NotificationChannels()
