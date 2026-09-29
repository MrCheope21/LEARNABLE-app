"""Outgoing email (password reset links). EMAIL_BACKEND picks the transport:

- console (default, development): the message is written to the server log. Anyone who can read
  the log can use the link, so this is for local development only.
- smtp: sent through an SMTP server (any provider, e.g. a Gmail account with an app password),
  with STARTTLS by default. Credentials come from the environment, never from the code.
"""

import logging
import smtplib
from email.message import EmailMessage
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.email")


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning("EMAIL_BACKEND=console. Email to %s: %s\n%s", to, subject, body)


class SmtpEmailSender:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        starttls: bool = True,
        timeout: float = 20,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._starttls = starttls
        self._timeout = timeout

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._starttls:
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            # Runs in a background task: the request already answered. Never log the body
            # (it holds the reset link), only that delivery failed.
            logger.exception("Email delivery failed (subject: %s)", subject)


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "smtp":
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value(),
            sender=settings.smtp_from,
            starttls=settings.smtp_starttls,
        )
    return ConsoleEmailSender()


@lru_cache
def _configured_sender() -> EmailSender:
    return build_email_sender(get_settings())


def get_email_sender() -> EmailSender:
    """FastAPI dependency (tests override it to capture messages)."""
    return _configured_sender()
