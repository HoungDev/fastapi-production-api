import smtplib
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import urlencode

from app.core.config import settings


class EmailSender(Protocol):
    def send_verification(self, recipient: str, token: str) -> None: ...


class SMTPEmailSender:
    def send_verification(self, recipient: str, token: str) -> None:
        query = urlencode({"token": token})
        verification_url = f"{settings.EMAIL_VERIFICATION_URL}?{query}"
        message = EmailMessage()
        message["Subject"] = "Verify your email address"
        message["From"] = settings.SMTP_FROM
        message["To"] = recipient
        message.set_content(
            "Verify your email address by opening this link:\n\n"
            f"{verification_url}\n\n"
            "If you did not request this, you can ignore this email."
        )

        with smtplib.SMTP(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(
                    settings.SMTP_USERNAME,
                    settings.SMTP_PASSWORD.get_secret_value(),
                )
            smtp.send_message(message)


def get_email_sender() -> EmailSender | None:
    if settings.EMAIL_DELIVERY_MODE == "smtp":
        return SMTPEmailSender()
    return None
